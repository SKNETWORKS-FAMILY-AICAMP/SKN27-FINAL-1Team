from __future__ import annotations

import asyncio
import os
from typing import Any

import runpod

from ai.calendar.runpod_server import create_calendar_event, delete_calendar_event


TOOLS = {
    "create_calendar_event": create_calendar_event,
    "delete_calendar_event": delete_calendar_event,
}


def _failed(message: str) -> dict[str, Any]:
    return {"ok": False, "message": message}


def handler(job: dict[str, Any]) -> dict[str, Any]:
    payload = job.get("input") or {}
    expected_token = os.getenv("RUNPOD_INTERNAL_TOKEN")
    if not expected_token:
        return _failed("RUNPOD_INTERNAL_TOKEN is not configured")
    if payload.get("internal_token") != expected_token:
        return _failed("invalid internal token")

    tool = TOOLS.get(payload.get("tool"))
    if tool is None:
        return _failed("unknown tool")

    try:
        return asyncio.run(tool(**(payload.get("arguments") or {})))
    except Exception as exc:
        return _failed(str(exc))


runpod.serverless.start({"handler": handler})
