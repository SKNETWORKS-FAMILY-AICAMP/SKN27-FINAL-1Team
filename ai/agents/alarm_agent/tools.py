from __future__ import annotations

import hashlib
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

import httpx
from fastapi import HTTPException

from app.backend.api.calendar import calendar_api


KST = timezone(timedelta(hours=9))


def _target_date(value: str | None) -> date:
    today = date.today()
    if value == "\ub0b4\uc77c":
        return today + timedelta(days=1)
    if value == "\ubaa8\ub808":
        return today + timedelta(days=2)
    if value in (None, "", "\uc624\ub298"):
        return today
    if "\uc6d4" in value and "\uc77c" in value:
        month, day = value.replace("\uc77c", "").split("\uc6d4", 1)
        return date(today.year, int(month.strip()), int(day.strip()))
    if "/" in value:
        month, day = value.split("/", 1)
        return date(today.year, int(month), int(day))
    return date.fromisoformat(value)


def _start_at(payload: dict[str, Any]) -> datetime:
    if payload.get("start_at"):
        value = datetime.fromisoformat(str(payload["start_at"]))
        return value if value.tzinfo else value.replace(tzinfo=KST)
    target = _target_date(payload.get("date_text") or payload.get("date"))
    hour = int(payload.get("hour", 9))
    minute = int(payload.get("minute", 0))
    return datetime.combine(target, time(hour, minute), KST)


async def create_calendar_event_tool(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    db = context.get("db")
    user_id = context.get("user_id")
    if not db or not user_id:
        return {
            "ok": False,
            "error": {"code": "CALENDAR_CONTEXT_REQUIRED", "message": "db\uc640 user_id\uac00 \ud544\uc694\ud574\uc694."},
        }

    title = payload.get("title") or payload.get("summary") or "\uce98\ub9b0\ub354 \uc77c\uc815"
    try:
        integration = calendar_api._get_google_integration(db, user_id)
        access_token = await calendar_api._get_access_token(integration, db)
        start_at = _start_at(payload)
        end_at = start_at + timedelta(minutes=int(payload.get("duration_minutes", 30)))
        event_key = payload.get("event_key") or (
            f"calendar-agent-{user_id}-{start_at.isoformat()}-"
            f"{hashlib.sha1(title.encode()).hexdigest()[:8]}"
        )
        event = {
            "summary": title,
            "description": payload.get("description") or "\ubc25\ubc8c\uc774 \uc54c\ub9bc agent\uac00 \ub4f1\ub85d\ud55c \uc77c\uc815\uc785\ub2c8\ub2e4.",
            "start": {"dateTime": start_at.isoformat()},
            "end": {"dateTime": end_at.isoformat()},
            "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": 0}]},
            "colorId": payload.get("colorId") or "7",
            "extendedProperties": {"private": {"bobbeoriKey": event_key}},
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            result = await calendar_api._create_event_once(
                client,
                integration.calendar_id,
                access_token,
                event_key,
                event,
                db,
                user_id,
                "alarm-agent",
            )
    except HTTPException as exc:
        return {"ok": False, "error": {"code": f"HTTP_{exc.status_code}", "message": str(exc.detail)}}
    except Exception as exc:
        return {"ok": False, "error": {"code": "CALENDAR_CREATE_FAILED", "message": str(exc)}}

    return {
        "ok": True,
        "message": "\uce98\ub9b0\ub354 \uc77c\uc815\uc744 \ub4f1\ub85d\ud588\uc5b4\uc694.",
        "data": {
            **result,
            "event_key": event_key,
            "title": title,
            "start_at": start_at.isoformat(),
        },
    }


async def delete_calendar_event_tool(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    db = context.get("db")
    user_id = context.get("user_id")
    event_key = payload.get("event_key")
    if not db or not user_id or not event_key:
        return {
            "ok": False,
            "error": {"code": "CALENDAR_DELETE_CONTEXT_REQUIRED", "message": "db, user_id, event_key\uac00 \ud544\uc694\ud574\uc694."},
        }
    if not calendar_api._event_key_belongs_to_user(event_key, user_id):
        return {"ok": False, "error": {"code": "CALENDAR_EVENT_FORBIDDEN", "message": "\uc0ad\uc81c\ud560 \uc218 \uc5c6\ub294 \uc77c\uc815\uc774\uc5d0\uc694."}}

    try:
        integration = calendar_api._get_google_integration(db, user_id)
        access_token = await calendar_api._get_access_token(integration, db)
        async with httpx.AsyncClient(timeout=10.0) as client:
            result = await calendar_api._delete_event_once(
                client,
                integration.calendar_id,
                access_token,
                event_key,
                db,
                user_id,
                "alarm-agent",
            )
    except HTTPException as exc:
        return {"ok": False, "error": {"code": f"HTTP_{exc.status_code}", "message": str(exc.detail)}}
    except Exception as exc:
        return {"ok": False, "error": {"code": "CALENDAR_DELETE_FAILED", "message": str(exc)}}

    return {"ok": True, "message": "\uce98\ub9b0\ub354 \uc77c\uc815\uc744 \uc0ad\uc81c\ud588\uc5b4\uc694.", "data": result}


async def list_calendar_events_tool(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    db = context.get("db")
    user_id = context.get("user_id")
    if not db or not user_id:
        return {
            "ok": False,
            "error": {"code": "CALENDAR_LIST_CONTEXT_REQUIRED", "message": "db\uc640 user_id\uac00 \ud544\uc694\ud574\uc694."},
        }

    start_date = _target_date(payload.get("start_date") or payload.get("date_text") or payload.get("date"))
    end_date = _target_date(payload.get("end_date")) if payload.get("end_date") else start_date + timedelta(days=1)
    try:
        result = await calendar_api.list_google_calendar_events(start_date=start_date, end_date=end_date, current_user_id=user_id, db=db)
    except HTTPException as exc:
        return {"ok": False, "error": {"code": f"HTTP_{exc.status_code}", "message": str(exc.detail)}}
    except Exception as exc:
        return {"ok": False, "error": {"code": "CALENDAR_LIST_FAILED", "message": str(exc)}}

    return {"ok": True, "message": "\uce98\ub9b0\ub354 \uc77c\uc815\uc744 \uc870\ud68c\ud588\uc5b4\uc694.", "data": result}


ALARM_AGENT_TOOLS = {
    "create_event": create_calendar_event_tool,
    "delete_event": delete_calendar_event_tool,
    "list_events": list_calendar_events_tool,
}
