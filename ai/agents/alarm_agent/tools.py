from __future__ import annotations

import hashlib
import re
import calendar
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

import httpx
from fastapi import HTTPException

from app.backend.api.calendar import calendar_api


KST = timezone(timedelta(hours=9))
WEEKDAYS = {"월요일": 0, "화요일": 1, "수요일": 2, "목요일": 3, "금요일": 4, "토요일": 5, "일요일": 6}
WEEK_OFFSETS = {"지난주": -7, "저번주": -7, "이번주": 0, "다음주": 7}


def _now() -> datetime:
    return datetime.now(KST)


def _today() -> date:
    return _now().date()


def _add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _month_range(value: date) -> tuple[date, date]:
    start = date(value.year, value.month, 1)
    return start, _add_months(start, 1)


def _target_date(value: str | None) -> date:
    today = _today()
    compact = re.sub(r"\s+", "", value or "")
    if compact == "어제":
        return today - timedelta(days=1)
    if compact == "내일":
        return today + timedelta(days=1)
    if compact == "모레":
        return today + timedelta(days=2)
    if compact in ("", "오늘"):
        return today
    if compact in WEEK_OFFSETS:
        return _target_range(compact)[0]
    if compact in ("지난달", "이번달", "다음달"):
        return _target_range(compact)[0]
    weekday_match = re.fullmatch(r"(지난주|저번주|이번주|다음주)?(월요일|화요일|수요일|목요일|금요일|토요일|일요일)", compact)
    if weekday_match:
        week_text, weekday = weekday_match.groups()
        week_offset = WEEK_OFFSETS.get(week_text, 0)
        start = today - timedelta(days=today.weekday()) + timedelta(days=week_offset)
        return start + timedelta(days=WEEKDAYS[weekday])
    full_match = re.fullmatch(r"\s*(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일\s*", value)
    if full_match:
        year, month, day = map(int, full_match.groups())
        return date(year, month, day)
    month_day_match = re.fullmatch(r"\s*(\d{1,2})월\s*(\d{1,2})일\s*", value)
    if month_day_match:
        month, day = map(int, month_day_match.groups())
        return date(today.year, month, day)
    if "월" in value and "일" in value:
        month, day = value.replace("일", "").split("월", 1)
        return date(today.year, int(month.strip()), int(day.strip()))
    if "/" in value:
        month, day = value.split("/", 1)
        return date(today.year, int(month), int(day))
    return date.fromisoformat(value)


def _target_range(value: str | None) -> tuple[date, date]:
    today = _today()
    compact = re.sub(r"\s+", "", value or "")
    if compact in WEEK_OFFSETS:
        week_offset = WEEK_OFFSETS[compact]
        start = today - timedelta(days=today.weekday()) + timedelta(days=week_offset)
        return start, start + timedelta(days=7)
    if compact in ("지난달", "이번달", "다음달"):
        month_offset = {"지난달": -1, "이번달": 0, "다음달": 1}[compact]
        return _month_range(_add_months(today, month_offset))
    if compact in ("방금", "최근"):
        return today, today + timedelta(days=30)
    start = _target_date(compact)
    return start, start + timedelta(days=1)


def _start_at(payload: dict[str, Any]) -> datetime:
    if payload.get("start_at"):
        value = datetime.fromisoformat(str(payload["start_at"]))
        return value if value.tzinfo else value.replace(tzinfo=KST)
    if payload.get("delay_minutes"):
        return _now() + timedelta(minutes=int(payload["delay_minutes"]))
    target = _target_date(payload.get("date_text") or payload.get("date"))
    hour = int(payload.get("hour", 9))
    minute = int(payload.get("minute", 0))
    return datetime.combine(target, time(hour, minute), KST)


def _subject_label(payload: dict[str, Any]) -> str:
    return {
        "consume_reminder": "먹기 알림",
        "shopping_reminder": "구매 알림",
    }.get(payload.get("reminder_type"), "일정")


def _join_subject(*parts: Any) -> str:
    return " ".join(str(part).strip() for part in parts if str(part or "").strip())


def _calendar_create_message(payload: dict[str, Any], title: str) -> str:
    subject = _join_subject(payload.get("date_text") or payload.get("date"), title, _subject_label(payload))
    return f"{subject}을 등록했어요." if subject else "캘린더 일정을 등록했어요."


def _calendar_list_message(payload: dict[str, Any]) -> str:
    date_text = payload.get("date_text") or payload.get("date") or payload.get("start_date")
    return f"{date_text} 등록된 일정이에요." if date_text else "등록된 일정이에요."


def _calendar_delete_message(payload: dict[str, Any]) -> str:
    subject = _join_subject(payload.get("date_text") or payload.get("date"), payload.get("title"), "일정")
    return f"{subject}을 삭제했어요." if subject else "캘린더 일정을 삭제했어요."


async def create_calendar_event_tool(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    db = context.get("db")
    user_id = context.get("user_id")
    if not db or not user_id:
        return {
            "ok": False,
            "error": {"code": "CALENDAR_CONTEXT_REQUIRED", "message": "db와 user_id가 필요해요."},
        }

    title = payload.get("title") or payload.get("summary") or "캘린더 일정"
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
            "description": payload.get("description") or "밥벌이 알림 agent가 등록한 일정입니다.",
            "start": {"dateTime": start_at.isoformat()},
            "end": {"dateTime": end_at.isoformat()},
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {
                        "method": "popup",
                        "minutes": int(payload.get("reminder_minutes_before", 0)),
                    }
                ],
            },
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
        "message": _calendar_create_message(payload, title),
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
            "error": {"code": "CALENDAR_DELETE_CONTEXT_REQUIRED", "message": "db, user_id, event_key가 필요해요."},
        }
    if not calendar_api._event_key_belongs_to_user(event_key, user_id):
        return {"ok": False, "error": {"code": "CALENDAR_EVENT_FORBIDDEN", "message": "삭제할 수 없는 일정이에요."}}

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

    if result.get("deleted") is not True:
        return {
            "ok": False,
            "error": {
                "code": "CALENDAR_EVENT_NOT_FOUND",
                "message": "밥벌이에서 등록한 일정을 찾을 수 없어요. 밥벌이에서 등록한 일정만 삭제할 수 있어요.",
            },
            "data": result,
        }

    return {"ok": True, "message": _calendar_delete_message(payload), "data": result}


async def list_calendar_events_tool(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    db = context.get("db")
    user_id = context.get("user_id")
    if not db or not user_id:
        return {
            "ok": False,
            "error": {"code": "CALENDAR_LIST_CONTEXT_REQUIRED", "message": "db와 user_id가 필요해요."},
        }

    if payload.get("start_date") or payload.get("end_date"):
        start_date = _target_date(payload.get("start_date") or payload.get("date_text") or payload.get("date"))
        end_date = _target_date(payload.get("end_date")) if payload.get("end_date") else start_date + timedelta(days=1)
    else:
        start_date, end_date = _target_range(payload.get("date_text") or payload.get("date"))
    try:
        result = await calendar_api.list_google_calendar_events(start_date=start_date, end_date=end_date, current_user_id=user_id, db=db)
    except HTTPException as exc:
        return {"ok": False, "error": {"code": f"HTTP_{exc.status_code}", "message": str(exc.detail)}}
    except Exception as exc:
        return {"ok": False, "error": {"code": "CALENDAR_LIST_FAILED", "message": str(exc)}}

    return {"ok": True, "message": _calendar_list_message(payload), "data": result}


async def sync_daily_events_tool(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    db = context.get("db")
    user_id = context.get("user_id")
    if not db or not user_id:
        return {
            "ok": False,
            "error": {"code": "CALENDAR_SYNC_CONTEXT_REQUIRED", "message": "db와 user_id가 필요해요."},
        }

    target_date = _target_date(payload.get("date_text") or payload.get("date"))
    try:
        integration = calendar_api._get_google_integration(db, user_id)
        access_token = await calendar_api._get_access_token(integration, db)
        async with httpx.AsyncClient(timeout=10.0) as client:
            created, deleted = await calendar_api._sync_daily_events(
                client,
                db,
                user_id,
                integration.calendar_id,
                access_token,
                target_date,
                "alarm-agent",
            )
    except HTTPException as exc:
        return {"ok": False, "error": {"code": f"HTTP_{exc.status_code}", "message": str(exc.detail)}}
    except Exception as exc:
        return {"ok": False, "error": {"code": "CALENDAR_SYNC_FAILED", "message": str(exc)}}

    return {"ok": True, "message": "오늘 알림 일정을 동기화했어요.", "data": {"events": created, "deleted": deleted}}


def list_notifications_tool(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    if not context.get("user_id"):
        return {"ok": False, "error": {"code": "ALARM_CONTEXT_REQUIRED", "message": "user_id가 필요해요."}}
    message = "읽지 않은 알림 목록이에요." if payload.get("unread_only") else "등록된 알림 목록이에요."
    return {
        "ok": True,
        "message": message,
        "data": {"notifications": [], "date_text": payload.get("date_text"), "unread_only": bool(payload.get("unread_only"))},
    }


def mark_notification_read_tool(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    if not context.get("user_id"):
        return {"ok": False, "error": {"code": "ALARM_CONTEXT_REQUIRED", "message": "user_id가 필요해요."}}
    return {"ok": True, "message": "알림을 읽음 처리했어요.", "data": {"notification_id": payload.get("notification_id")}}


def register_device_token_tool(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    if not context.get("user_id"):
        return {"ok": False, "error": {"code": "ALARM_CONTEXT_REQUIRED", "message": "user_id가 필요해요."}}
    return {"ok": True, "message": "알림 수신 기기를 등록했어요.", "data": {"device_token": payload.get("device_token")}}


ALARM_AGENT_TOOLS = {
    "create_event": create_calendar_event_tool,
    "delete_event": delete_calendar_event_tool,
    "list_events": list_calendar_events_tool,
    "sync_daily_events": sync_daily_events_tool,
    "list_notifications": list_notifications_tool,
    "mark_notification_read": mark_notification_read_tool,
    "register_device_token": register_device_token_tool,
}
