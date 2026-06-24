from __future__ import annotations

from copy import deepcopy

import httpx

from app.backend.core.config import settings


async def prepare_calendar_event(user_id: int | None, event_key: str, event: dict, source: str) -> dict:
    if not settings.RUNPOD_CALENDAR_MCP_URL:
        return event

    headers = {"Content-Type": "application/json"}
    if settings.RUNPOD_INTERNAL_TOKEN:
        headers["X-Internal-Token"] = settings.RUNPOD_INTERNAL_TOKEN

    try:
        async with httpx.AsyncClient(timeout=settings.RUNPOD_TIMEOUT_SECONDS) as client:
            response = await client.post(
                settings.RUNPOD_CALENDAR_MCP_URL,
                json={
                    "user_id": user_id,
                    "event_key": event_key,
                    "source": source,
                    "event": event,
                },
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        print(f"[CalendarMCP] Runpod request failed: {exc}")
        return event

    prepared = data.get("event") if isinstance(data, dict) else None
    return deepcopy(prepared) if isinstance(prepared, dict) else event
