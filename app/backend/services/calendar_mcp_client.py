from __future__ import annotations

from datetime import timedelta
from typing import Any

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

    try:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client
    except ImportError as exc:
        print(f"[CalendarMCP] MCP SDK is not installed: {exc}")
        return None

    headers = {}
    if settings.RUNPOD_INTERNAL_TOKEN:
        headers["X-Internal-Token"] = settings.RUNPOD_INTERNAL_TOKEN

    try:
        async with streamablehttp_client(
            settings.RUNPOD_CALENDAR_MCP_URL,
            headers=headers,
            timeout=settings.RUNPOD_TIMEOUT_SECONDS,
            sse_read_timeout=timedelta(seconds=settings.RUNPOD_TIMEOUT_SECONDS),
        ) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "create_calendar_event",
                    arguments={
                        "user_id": user_id,
                        "calendar_id": calendar_id,
                        "access_token": access_token,
                        "event_key": event_key,
                        "source": source,
                        "event": event,
                    },
                )
    except Exception as exc:
        print(f"[CalendarMCP] MCP tool call failed: {exc}")
        return None

    data = _structured_result(result)
    return data if isinstance(data, dict) and data.get("event_id") else None


def _structured_result(result: Any) -> dict | None:
    data = getattr(result, "structuredContent", None)
    if isinstance(data, dict):
        return data

    for item in getattr(result, "content", []) or []:
        text = getattr(item, "text", None)
        if not text:
            continue
        try:
            import json

            parsed = json.loads(text)
        except ValueError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None
