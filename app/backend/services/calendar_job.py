import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from app.backend.api.calendar.calendar_api import _get_access_token, _sync_daily_events
from app.backend.db.models import CalendarIntegration
from app.backend.db.session import SessionLocal


KST = ZoneInfo("Asia/Seoul")


async def sync_daily_calendar_events() -> None:
    """Synchronize one daily batch for every connected Google Calendar user."""
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


def main() -> None:
    """Run one batch; EventBridge or another deployment scheduler owns timing."""
    asyncio.run(sync_daily_calendar_events())


if __name__ == "__main__":
    main()
