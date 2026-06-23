import base64
import hashlib
from datetime import date, datetime, timedelta, timezone

import httpx
from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.backend.api.deps import get_current_user_required
from app.backend.core.config import settings
from app.backend.db.models import CalendarIntegration
from app.backend.db.session import get_db


router = APIRouter(prefix="/calendar", tags=["Calendar (캘린더 연동)"])


class GoogleCalendarConnectRequest(BaseModel):
    code: str


def _cipher() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.JWT_SECRET_KEY.encode()).digest())
    return Fernet(key)


def _encrypt(value: str) -> str:
    return _cipher().encrypt(value.encode()).decode()


def _decrypt(value: str) -> str:
    return _cipher().decrypt(value.encode()).decode()


def _get_google_integration(db: Session, user_id: int) -> CalendarIntegration:
    integration = (
        db.query(CalendarIntegration)
        .filter(
            CalendarIntegration.user_id == user_id,
            CalendarIntegration.provider == "google",
        )
        .first()
    )
    if not integration:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Google Calendar is not connected.")
    return integration


async def _get_access_token(integration: CalendarIntegration, db: Session) -> str:
    expires_at = integration.expires_at
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at and expires_at > datetime.now(timezone.utc) + timedelta(minutes=1):
        return _decrypt(integration.access_token)

    if not integration.refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Google Calendar reconnect is required.")

    async with httpx.AsyncClient(timeout=10.0) as client:
        token_res = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "grant_type": "refresh_token",
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "refresh_token": _decrypt(integration.refresh_token),
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    if token_res.status_code >= 400:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Google Calendar token refresh failed.")

    token_data = token_res.json()
    access_token = token_data["access_token"]
    integration.access_token = _encrypt(access_token)
    integration.expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(token_data.get("expires_in", 3600)))
    db.commit()
    return access_token


async def _create_event_once(client: httpx.AsyncClient, calendar_id: str, access_token: str, event_key: str, event: dict):
    url = f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    existing_res = await client.get(
        url,
        headers=headers,
        params={"privateExtendedProperty": f"bobbeoriKey={event_key}", "singleEvents": "true", "maxResults": 1},
    )
    if existing_res.status_code >= 400:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Google Calendar event lookup failed.")

    existing = existing_res.json().get("items", [])
    if existing:
        item = existing[0]
        return {"event_id": item.get("id"), "html_link": item.get("htmlLink"), "duplicate": True}

    event["extendedProperties"] = {"private": {"bobbeoriKey": event_key}}
    event_res = await client.post(url, headers=headers, json=event)
    if event_res.status_code >= 400:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Google Calendar event creation failed.")

    item = event_res.json()
    return {"event_id": item.get("id"), "html_link": item.get("htmlLink"), "duplicate": False}


@router.get("/google/status")
def google_calendar_status(
    current_user_id: int = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    integration = (
        db.query(CalendarIntegration)
        .filter(
            CalendarIntegration.user_id == current_user_id,
            CalendarIntegration.provider == "google",
        )
        .first()
    )

    return {
        "connected": integration is not None,
        "calendar_id": integration.calendar_id if integration else None,
    }


@router.post("/google/connect")
async def connect_google_calendar(
    request_data: GoogleCalendarConnectRequest,
    current_user_id: int = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Google OAuth 설정이 없습니다.",
        )

    async with httpx.AsyncClient(timeout=10.0) as client:
        token_res = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "grant_type": "authorization_code",
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": settings.GOOGLE_CALENDAR_REDIRECT_URI,
                "code": request_data.code,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    if token_res.status_code >= 400:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google Calendar 토큰 발급에 실패했습니다.",
        )

    token_data = token_res.json()
    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")
    expires_in = int(token_data.get("expires_in", 3600))

    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google Calendar access_token이 없습니다.",
        )

    integration = (
        db.query(CalendarIntegration)
        .filter(
            CalendarIntegration.user_id == current_user_id,
            CalendarIntegration.provider == "google",
        )
        .first()
    )

    if not integration:
        integration = CalendarIntegration(user_id=current_user_id, provider="google", calendar_id="primary")
        db.add(integration)

    if not refresh_token and not integration.refresh_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google Calendar refresh_token이 없습니다. 다시 동의해주세요.",
        )

    integration.access_token = _encrypt(access_token)
    if refresh_token:
        integration.refresh_token = _encrypt(refresh_token)
    integration.expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    integration.calendar_id = integration.calendar_id or "primary"

    db.commit()

    return {"connected": True, "calendar_id": integration.calendar_id}


@router.delete("/google/disconnect")
def disconnect_google_calendar(
    current_user_id: int = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    integration = (
        db.query(CalendarIntegration)
        .filter(
            CalendarIntegration.user_id == current_user_id,
            CalendarIntegration.provider == "google",
        )
        .first()
    )

    if integration:
        db.delete(integration)
        db.commit()

    return {"connected": False}


@router.post("/google/test-event")
async def create_google_calendar_test_event(
    current_user_id: int = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    integration = _get_google_integration(db, current_user_id)
    access_token = await _get_access_token(integration, db)
    today = date.today()
    recipe_expiry_date = today + timedelta(days=7)
    events = [
        (
            f"ingredient-expiry-{current_user_id}-{today.isoformat()}",
            {
                "summary": "대파 오늘까지 사용 추천",
                "description": "소비기한 임박 재료를 먼저 사용해보세요.",
                "start": {"date": today.isoformat()},
                "end": {"date": (today + timedelta(days=1)).isoformat()},
            },
        ),
        (
            f"today-menu-{current_user_id}-{today.isoformat()}",
            {
                "summary": "저녁 추천: 대파 두부 계란찌개",
                "description": "오늘의 추천 메뉴입니다.",
                "start": {"date": today.isoformat()},
                "end": {"date": (today + timedelta(days=1)).isoformat()},
            },
        ),
        (
            f"recipe-delete-{current_user_id}-{recipe_expiry_date.isoformat()}",
            {
                "summary": "저장 레시피 삭제 예정",
                "description": "등록해둔 레시피가 오늘 사라질 예정이에요.",
                "start": {"date": recipe_expiry_date.isoformat()},
                "end": {"date": (recipe_expiry_date + timedelta(days=1)).isoformat()},
            },
        ),
    ]

    async with httpx.AsyncClient(timeout=10.0) as client:
        created = [
            await _create_event_once(client, integration.calendar_id, access_token, event_key, event)
            for event_key, event in events
        ]

    return {"events": created}
