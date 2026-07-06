from __future__ import annotations

from typing import Any

import httpx

from app.backend.core.config import settings


def _runsync_url() -> str:
    base = settings.RUNPOD_CALENDAR_SERVERLESS_URL.rstrip("/")
    return base if base.endswith("/runsync") else f"{base}/runsync"


def _serverless_output(payload: dict[str, Any]) -> dict | None:
    if payload.get("status") != "COMPLETED":
        return None
    output = payload.get("output")
    return output if isinstance(output, dict) else None


async def _call_calendar_tool(tool_name: str, arguments: dict[str, Any]) -> dict | None:
    if not settings.RUNPOD_CALENDAR_SERVERLESS_URL:
        return None

    headers = {}
    if settings.RUNPOD_API_KEY:
        headers["Authorization"] = f"Bearer {settings.RUNPOD_API_KEY}"
    if settings.RUNPOD_INTERNAL_TOKEN:
        headers["X-Internal-Token"] = settings.RUNPOD_INTERNAL_TOKEN

    try:
        async with httpx.AsyncClient(timeout=settings.RUNPOD_TIMEOUT_SECONDS) as client:
            response = await client.post(
                _runsync_url(),
                headers=headers,
                json={
                    "input": {
                        "tool": tool_name,
                        "arguments": arguments,
                        "internal_token": settings.RUNPOD_INTERNAL_TOKEN,
                    }
                },
            )
            response.raise_for_status()
    except Exception as exc:
        print(f"[CalendarMCP] RunPod serverless call failed ({tool_name}): {exc}")
        return None

    return _serverless_output(response.json())


async def create_calendar_event_with_mcp(
    user_id: int | None,
    calendar_id: str,
    access_token: str,
    event_key: str,
    event: dict,
    source: str,
) -> dict | None:
    data = await _call_calendar_tool(
        "create_calendar_event",
        {
            "user_id": user_id,
            "calendar_id": calendar_id,
            "access_token": access_token,
            "event_key": event_key,
            "source": source,
            "event": event,
        },
    )
    return data if isinstance(data, dict) and data.get("event_id") else None


async def delete_calendar_event_with_mcp(
    user_id: int | None,
    calendar_id: str,
    access_token: str,
    event_key: str,
) -> dict | None:
    data = await _call_calendar_tool(
        "delete_calendar_event",
        {
            "user_id": user_id,
            "calendar_id": calendar_id,
            "access_token": access_token,
            "event_key": event_key,
        },
    )
    return data if isinstance(data, dict) and (data.get("deleted") or data.get("missing")) else None
