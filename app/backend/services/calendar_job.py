import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from app.backend.api.calendar.calendar_api import _build_daily_events, _create_event_once, _get_access_token
from app.backend.db.models import CalendarIntegration
from app.backend.db.session import SessionLocal

KST = ZoneInfo("Asia/Seoul")


async def sync_daily_calendar_events():
    db = SessionLocal()
    try:
        today = datetime.now(KST).date()
        integrations = db.query(CalendarIntegration).filter(CalendarIntegration.provider == "google").all()

        async with httpx.AsyncClient(timeout=10.0) as client:
            for integration in integrations:
                try:
                    access_token = await _get_access_token(integration, db)
                    events = _build_daily_events(db, integration.user_id, today)
                    for event_key, event in events:
                        await _create_event_once(
                            client,
                            integration.calendar_id,
                            access_token,
                            event_key,
                            event,
                            db,
                            integration.user_id,
                            "daily",
                        )
                except Exception as exc:
                    print(f"[CalendarJob] user_id={integration.user_id} failed: {exc}")
    finally:
        db.close()


async def daily_calendar_loop():
    while True:
        now = datetime.now(KST)
        next_run = now.replace(hour=7, minute=0, second=0, microsecond=0)
        if now >= next_run:
            next_run += timedelta(days=1)

        await asyncio.sleep((next_run - now).total_seconds())
        await sync_daily_calendar_events()
