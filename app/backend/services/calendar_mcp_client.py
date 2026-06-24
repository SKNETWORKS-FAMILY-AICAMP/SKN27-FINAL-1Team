from __future__ import annotations

import httpx

from app.backend.core.config import settings


async def enrich_calendar_events(user_id: int, start_date, end_date, events: list[dict]) -> list[dict]:
    if not settings.RUNPOD_CALENDAR_MCP_URL:
        return events

    headers = {"Content-Type": "application/json"}
    if settings.RUNPOD_INTERNAL_TOKEN:
        headers["X-Internal-Token"] = settings.RUNPOD_INTERNAL_TOKEN

    try:
        async with httpx.AsyncClient(timeout=settings.RUNPOD_TIMEOUT_SECONDS) as client:
            response = await client.post(
                settings.RUNPOD_CALENDAR_MCP_URL,
                json={
                    "user_id": user_id,
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "events": events,
                },
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError):
        return events

    enriched = data.get("events") if isinstance(data, dict) else None
    return enriched if isinstance(enriched, list) else events
