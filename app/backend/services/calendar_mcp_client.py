from __future__ import annotations

import httpx

from app.backend.core.config import settings


async def create_calendar_event_with_mcp(
    user_id: int | None,
    calendar_id: str,
    access_token: str,
    event_key: str,
    event: dict,
    source: str,
) -> dict | None:
    if not settings.RUNPOD_CALENDAR_MCP_URL:
        return None

    headers = {"Content-Type": "application/json"}
    if settings.RUNPOD_INTERNAL_TOKEN:
        headers["X-Internal-Token"] = settings.RUNPOD_INTERNAL_TOKEN

    try:
        async with httpx.AsyncClient(timeout=settings.RUNPOD_TIMEOUT_SECONDS) as client:
            response = await client.post(
                settings.RUNPOD_CALENDAR_MCP_URL,
                json={
                    "user_id": user_id,
                    "calendar_id": calendar_id,
                    "access_token": access_token,
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
        return None

    return data if isinstance(data, dict) and data.get("event_id") else None
