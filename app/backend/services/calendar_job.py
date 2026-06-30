import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from app.backend.api.calendar.calendar_api import _get_access_token, _sync_daily_events
from app.backend.db.models import CalendarIntegration
from app.backend.db.session import SessionLocal

KST = ZoneInfo("Asia/Seoul")


async def sync_daily_calendar_events():
    """Google Calendar 연동 사용자의 오늘 알림 이벤트를 실제 캘린더에 동기화한다."""
    db = SessionLocal()
    try:
        today = datetime.now(KST).date()
        integrations = db.query(CalendarIntegration).filter(CalendarIntegration.provider == "google").all()

        async with httpx.AsyncClient(timeout=10.0) as client:
            for integration in integrations:
                try:
                    access_token = await _get_access_token(integration, db)
                    await _sync_daily_events(
                        client,
                        db,
                        integration.user_id,
                        integration.calendar_id,
                        access_token,
                        today,
                        "daily",
                    )
                except Exception as exc:
                    print(f"[CalendarJob] user_id={integration.user_id} failed: {exc}")
    finally:
        db.close()


async def daily_calendar_loop():
    """백엔드가 켜져 있는 동안 매일 오전 7시(KST)에 캘린더 동기화를 실행한다."""
    while True:
        now = datetime.now(KST)
        next_run = now.replace(hour=7, minute=0, second=0, microsecond=0)
        if now >= next_run:
            next_run += timedelta(days=1)

        await asyncio.sleep((next_run - now).total_seconds())
        await sync_daily_calendar_events()
