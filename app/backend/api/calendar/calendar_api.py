import base64
import hashlib
from datetime import datetime, timedelta, timezone

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
