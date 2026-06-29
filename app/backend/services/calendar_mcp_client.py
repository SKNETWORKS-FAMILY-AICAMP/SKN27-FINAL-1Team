from __future__ import annotations

from typing import Any

import httpx

from app.backend.core.config import settings


async def _call_calendar_tool(
    tool_name: str,
    arguments: dict[str, Any],
) -> dict | None:
    if not settings.RUNPOD_CALENDAR_MCP_URL:
        return None

    try:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client
    except ImportError as exc:
        print(f"[CalendarMCP] MCP SDK is not installed: {exc}")
        return None

    headers = {}
    if settings.RUNPOD_INTERNAL_TOKEN:
        headers["X-Internal-Token"] = settings.RUNPOD_INTERNAL_TOKEN

    try:
        timeout = httpx.Timeout(settings.RUNPOD_TIMEOUT_SECONDS, read=settings.RUNPOD_TIMEOUT_SECONDS)
        async with httpx.AsyncClient(headers=headers, timeout=timeout) as http_client:
            async with streamable_http_client(
                settings.RUNPOD_CALENDAR_MCP_URL,
                http_client=http_client,
            ) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, arguments=arguments)
    except Exception as exc:
        print(f"[CalendarMCP] MCP tool call failed ({tool_name}): {exc}")
        return None

    return _structured_result(result)


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
