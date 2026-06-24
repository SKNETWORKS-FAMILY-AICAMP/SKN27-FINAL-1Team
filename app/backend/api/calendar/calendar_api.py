import base64
import hashlib
from datetime import date, datetime, time, timedelta, timezone

import httpx
from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.backend.api.deps import get_current_user_required
from app.backend.core.config import settings
from app.backend.db.models import CalendarEventLog, CalendarIntegration, FridgeItem, RecommendationResult
from app.backend.db.session import get_db
from app.backend.services.calendar_mcp_client import create_calendar_event_with_mcp


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


def _event_type(event_key: str) -> str:
    return event_key.split("-", 1)[0]


def _event_target_date(event: dict):
    start = event.get("start", {})
    value = start.get("date") or start.get("dateTime", "")[:10]
    return date.fromisoformat(value) if value else None


def _alert_time(target_date: date, hour: int, minute: int):
    start = datetime.combine(target_date, time(hour, minute), timezone(timedelta(hours=9)))
    end = start + timedelta(minutes=10)
    return (
        {"dateTime": start.isoformat()},
        {"dateTime": end.isoformat()},
        {"useDefault": False, "overrides": [{"method": "popup", "minutes": 0}]},
    )


def _log_calendar_event(
    db: Session | None,
    user_id: int | None,
    event_key: str,
    event: dict,
    status_value: str,
    source: str,
    google_event_id: str | None = None,
    html_link: str | None = None,
    error_message: str | None = None,
):
    if not db or not user_id:
        return

    db.add(
        CalendarEventLog(
            user_id=user_id,
            event_key=event_key,
            event_type=_event_type(event_key),
            summary=event.get("summary"),
            target_date=_event_target_date(event),
            google_event_id=google_event_id,
            html_link=html_link,
            status=status_value,
            source=source,
            error_message=error_message,
        )
    )
    db.commit()


async def _create_event_once(
    client: httpx.AsyncClient,
    calendar_id: str,
    access_token: str,
    event_key: str,
    event: dict,
    db: Session | None = None,
    user_id: int | None = None,
    source: str = "manual",
):
    mcp_result = await create_calendar_event_with_mcp(user_id, calendar_id, access_token, event_key, event, source)
    if mcp_result:
        _log_calendar_event(
            db,
            user_id,
            event_key,
            mcp_result.get("event") or event,
            "updated" if mcp_result.get("updated") else "duplicate" if mcp_result.get("duplicate") else "created",
            source,
            google_event_id=mcp_result.get("event_id"),
            html_link=mcp_result.get("html_link"),
        )
        return mcp_result

    url = f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    existing_res = await client.get(
        url,
        headers=headers,
        params={"privateExtendedProperty": f"bobbeoriKey={event_key}", "singleEvents": "true", "maxResults": 1},
    )
    if existing_res.status_code >= 400:
        _log_calendar_event(db, user_id, event_key, event, "failed", source, error_message=existing_res.text[:500])
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Google Calendar event lookup failed.")

    existing = existing_res.json().get("items", [])
    if existing:
        item = existing[0]
        watched_fields = ("summary", "description", "start", "end", "colorId", "reminders")
        if any(item.get(field) != event.get(field) for field in watched_fields):
            event.setdefault("extendedProperties", {}).setdefault("private", {})
            event["extendedProperties"]["private"]["bobbeoriKey"] = event_key
            event_res = await client.patch(f"{url}/{item.get('id')}", headers=headers, json=event)
            if event_res.status_code >= 400:
                _log_calendar_event(db, user_id, event_key, event, "failed", source, error_message=event_res.text[:500])
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Google Calendar event update failed.")

            item = event_res.json()
            _log_calendar_event(
                db,
                user_id,
                event_key,
                event,
                "updated",
                source,
                google_event_id=item.get("id"),
                html_link=item.get("htmlLink"),
            )
            return {"event_id": item.get("id"), "html_link": item.get("htmlLink"), "duplicate": True, "updated": True}

        _log_calendar_event(
            db,
            user_id,
            event_key,
            event,
            "duplicate",
            source,
            google_event_id=item.get("id"),
            html_link=item.get("htmlLink"),
        )
        return {"event_id": item.get("id"), "html_link": item.get("htmlLink"), "duplicate": True}

    event.setdefault("extendedProperties", {}).setdefault("private", {})
    event["extendedProperties"]["private"]["bobbeoriKey"] = event_key
    event_res = await client.post(url, headers=headers, json=event)
    if event_res.status_code >= 400:
        _log_calendar_event(db, user_id, event_key, event, "failed", source, error_message=event_res.text[:500])
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Google Calendar event creation failed.")

    item = event_res.json()
    _log_calendar_event(
        db,
        user_id,
        event_key,
        event,
        "created",
        source,
        google_event_id=item.get("id"),
        html_link=item.get("htmlLink"),
    )
    return {"event_id": item.get("id"), "html_link": item.get("htmlLink"), "duplicate": False}


def _build_daily_events(db: Session, user_id: int, target_date: date):
    events = []
    expiring_until = target_date + timedelta(days=3)

    expiring_items = (
        db.query(FridgeItem)
        .filter(
            FridgeItem.user_id == user_id,
            FridgeItem.expiry_date.isnot(None),
            FridgeItem.expiry_date >= target_date,
            FridgeItem.expiry_date <= expiring_until,
            FridgeItem.status != "used",
        )
        .all()
    )
    if expiring_items:
        start_time, end_time, reminders = _alert_time(target_date, 8, 30)
        names = [item.display_name or item.ingredient.name for item in expiring_items[:3]]
        suffix = f" 외 {len(expiring_items) - 3}개" if len(expiring_items) > 3 else ""
        soonest_date = min(item.expiry_date for item in expiring_items)
        days_left = (soonest_date - target_date).days
        due_label = "오늘까지" if days_left <= 0 else f"{days_left}일 안에"
        events.append(
            (
                f"ingredient-expiry-{user_id}-{target_date.isoformat()}",
                {
                    "summary": f"{', '.join(names)}{suffix} {due_label} 사용 추천",
                    "description": "소비기한 임박 재료를 먼저 사용해보세요.",
                    "start": start_time,
                    "end": end_time,
                    "reminders": reminders,
                    "colorId": "11",
                },
            )
        )

    latest_recommendation = (
        db.query(RecommendationResult)
        .filter(RecommendationResult.user_id == user_id)
        .order_by(RecommendationResult.created_at.desc())
        .first()
    )
    if latest_recommendation and latest_recommendation.recipe:
        start_time, end_time, reminders = _alert_time(target_date, 17, 30)
        events.append(
            (
                f"today-menu-{user_id}-{target_date.isoformat()}",
                {
                    "summary": f"저녁 추천: {latest_recommendation.recipe.title}",
                    "description": "오늘의 추천 메뉴입니다.",
                    "start": start_time,
                    "end": end_time,
                    "reminders": reminders,
                    "colorId": "2",
                },
            )
        )

    expiring_recipe_date = target_date - timedelta(days=7)
    start_at = datetime.combine(expiring_recipe_date, time.min)
    end_at = datetime.combine(expiring_recipe_date + timedelta(days=1), time.min)
    expiring_recipes = (
        db.query(RecommendationResult)
        .filter(
            RecommendationResult.user_id == user_id,
            RecommendationResult.created_at >= start_at,
            RecommendationResult.created_at < end_at,
        )
        .all()
    )
    if expiring_recipes:
        start_time, end_time, reminders = _alert_time(target_date, 9, 0)
        title = expiring_recipes[0].recipe.title if expiring_recipes[0].recipe else "저장 레시피"
        suffix = f" 외 {len(expiring_recipes) - 1}개" if len(expiring_recipes) > 1 else ""
        events.append(
            (
                f"recipe-delete-{user_id}-{target_date.isoformat()}",
                {
                    "summary": f"{title}{suffix} 삭제 예정",
                    "description": "등록해둔 레시피가 오늘 사라질 예정이에요.",
                    "start": start_time,
                    "end": end_time,
                    "reminders": reminders,
                    "colorId": "5",
                },
            )
        )

    return events


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


@router.get("/google/events")
async def list_google_calendar_events(
    start_date: date = Query(...),
    end_date: date = Query(...),
    current_user_id: int = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    integration = _get_google_integration(db, current_user_id)
    access_token = await _get_access_token(integration, db)

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"https://www.googleapis.com/calendar/v3/calendars/{integration.calendar_id}/events",
            headers={"Authorization": f"Bearer {access_token}"},
            params={
                "timeMin": datetime.combine(start_date, time.min, timezone.utc).isoformat(),
                "timeMax": datetime.combine(end_date, time.min, timezone.utc).isoformat(),
                "singleEvents": "true",
                "orderBy": "startTime",
            },
        )

    if response.status_code >= 400:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Google Calendar event lookup failed.")

    events = []
    for item in response.json().get("items", []):
        if item.get("status") == "cancelled":
            continue
        start = item.get("start", {})
        date_key = start.get("date") or start.get("dateTime", "")[:10]
        if date_key:
            events.append(
                {
                    "id": item.get("id"),
                    "dateKey": date_key,
                    "title": item.get("summary") or "제목 없는 일정",
                    "colorId": item.get("colorId"),
                    "htmlLink": item.get("htmlLink"),
                }
            )

    return {"events": events}


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

    created = []
    try:
        events = _build_daily_events(db, current_user_id, date.today())
        async with httpx.AsyncClient(timeout=10.0) as client:
            created = [
                await _create_event_once(
                    client,
                    integration.calendar_id,
                    access_token,
                    event_key,
                    event,
                    db,
                    current_user_id,
                    "connect",
                )
                for event_key, event in events
            ]
    except Exception as exc:
        print(f"[CalendarConnect] user_id={current_user_id} initial sync failed: {exc}")

    return {"connected": True, "calendar_id": integration.calendar_id, "events": created}


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
    events = _build_daily_events(db, current_user_id, today)

    async with httpx.AsyncClient(timeout=10.0) as client:
        created = [
            await _create_event_once(
                client,
                integration.calendar_id,
                access_token,
                event_key,
                event,
                db,
                current_user_id,
                "manual",
            )
            for event_key, event in events
        ]

    return {"events": created}
