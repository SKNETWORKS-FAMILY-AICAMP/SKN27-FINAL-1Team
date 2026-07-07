from __future__ import annotations

import asyncio
import inspect
import re
from copy import deepcopy
from typing import Any, Callable


AGENT_NAME = "alarm"
ToolMap = dict[str, Callable[[dict[str, Any], dict[str, Any]], Any]]
REMINDER_TYPES = {"consume_reminder", "shopping_reminder", "calendar_event"}

MSG_CALENDAR_LIST = "캘린더 일정을 조회했어요."
MSG_CALENDAR_CREATE = "캘린더 일정을 등록했어요."
MSG_CALENDAR_DELETE = "캘린더 일정을 삭제했어요."
MSG_CALENDAR_SYNC = "오늘 알림 일정을 동기화했어요."
MSG_ALARM_LIST = "알림 목록을 조회했어요."
MSG_ALARM_READ = "알림을 읽음 처리했어요."
MSG_ALARM_DEVICE = "알림 수신 기기를 등록했어요."
MSG_CLARIFY = "어떤 알림인지 알려주세요. 먹기/구매/일반 일정 중 하나로 등록할 수 있어요."
MSG_HANDLED = "요청을 처리했어요."
MSG_UNKNOWN = "알림/캘린더 agent가 처리할 수 없는 요청이에요."
MSG_TOOL_MISSING = "실행할 도구가 연결되지 않았어요."
MSG_TOOL_FAILED = "도구 실행에 실패했어요."
MSG_ASYNC_REQUIRED = "비동기 환경에서는 arun()을 호출해주세요."
TITLE_CALENDAR_EVENT = "캘린더 일정"
LABEL_CREATE = "등록"
LABEL_DELETE = "삭제"
LABEL_SYNC = "동기화"
LABEL_CANCEL = "취소"

_INTENT_ACTIONS = {
    "calendar.list": ("list_events", MSG_CALENDAR_LIST),
    "calendar.create": ("create_event", MSG_CALENDAR_CREATE),
    "calendar.delete": ("delete_event", MSG_CALENDAR_DELETE),
    "calendar.sync_daily": ("sync_daily_events", MSG_CALENDAR_SYNC),
    "alarm.list": ("list_notifications", MSG_ALARM_LIST),
    "alarm.read": ("mark_notification_read", MSG_ALARM_READ),
    "alarm.register_device": ("register_device_token", MSG_ALARM_DEVICE),
    "alarm.clarify": ("clarify", MSG_CLARIFY),
    "mcp.calendar": ("create_event", MSG_CALENDAR_CREATE),
    "mcp.pending_calendar": ("create_event", MSG_CALENDAR_CREATE),
}
_ALLOWED_INTENTS = set(_INTENT_ACTIONS)

_CONFIRM_ACTIONS = {"create_event", "delete_event", "sync_daily_events", "mark_notification_read", "register_device_token"}

_CREATE_WORDS = ("등록", "추가", "생성", "예약", "잡아", "만들", "설정")
_DELETE_WORDS = ("삭제", "지워", "취소", "없애")
_LIST_WORDS = ("조회", "목록", "보여", "확인", "알려")
_SYNC_WORDS = ("동기화", "자동", "일일", "오늘알림", "아침")
_CALENDAR_WORDS = ("캘린더", "일정", "알림", "알람", "리마인더")
_DATE_WORDS = ("오늘", "내일", "모레")
_CONSUME_WORDS = ("먹", "사용", "소비", "처리", "요리")
_SHOPPING_WORDS = ("사", "구매", "장보", "장볼")
_GENERAL_EVENT_WORDS = ("일정", "미팅", "약속", "예약")


def _ui(ui: dict[str, Any] | None = None) -> dict[str, list[Any]]:
    base = {"actions": [], "cards": [], "sources": []}
    if not ui:
        return base
    return {key: list(ui.get(key) or []) for key in base}


def build_response(
    *,
    ok: bool,
    action: str,
    intent: str,
    message: str,
    data: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
    requires_confirmation: bool = False,
    ui: dict[str, Any] | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "ok": ok,
        "agent": AGENT_NAME,
        "action": action,
        "intent": intent,
        "message": message,
        "data": data or {},
        "error": error,
        "requires_confirmation": requires_confirmation,
        "ui": _ui(ui),
        "meta": meta or {},
    }


def _failure(intent: str, action: str, message: str, code: str = "ALARM_AGENT_ERROR") -> dict[str, Any]:
    return build_response(
        ok=False,
        action=action,
        intent=intent,
        message=message,
        error={"code": code, "message": message},
    )


def _unknown() -> dict[str, Any]:
    return _failure("unknown", "unknown", MSG_UNKNOWN, "UNKNOWN_INTENT")


def _confirmation(intent: str, action: str, payload: dict[str, Any]) -> dict[str, Any]:
    title = payload.get("title") or payload.get("summary") or payload.get("event_key") or TITLE_CALENDAR_EVENT
    label = LABEL_DELETE if action == "delete_event" else LABEL_SYNC if action == "sync_daily_events" else LABEL_CREATE
    return build_response(
        ok=True,
        action=action,
        intent=intent,
        message=f"{title} {label}할까요?",
        data={"payload": deepcopy(payload)},
        requires_confirmation=True,
        ui={
            "actions": [
                {"type": "confirm", "label": label, "value": {"intent": intent, "action": action, "payload": payload}},
                {"type": "cancel", "label": LABEL_CANCEL, "value": {"intent": intent, "action": "cancel"}},
            ]
        },
        meta={
            "human_in_the_loop": True,
            "stage": "confirmation",
            "reason": "confirm_before_tool",
            "pending_action": action,
        },
    )


def _clarification(payload: dict[str, Any]) -> dict[str, Any]:
    return build_response(
        ok=True,
        action="clarify",
        intent="alarm.clarify",
        message=MSG_CLARIFY,
        data={
            "title": payload.get("title") or TITLE_CALENDAR_EVENT,
            "date_text": payload.get("date_text"),
            "candidates": ["consume_reminder", "shopping_reminder", "calendar_event"],
        },
        requires_confirmation=True,
        ui={
            "actions": [
                {"type": "select", "label": "먹기 알림", "value": "consume_reminder"},
                {"type": "select", "label": "구매 알림", "value": "shopping_reminder"},
                {"type": "select", "label": "일반 일정", "value": "calendar_event"},
            ]
        },
        meta={
            "human_in_the_loop": True,
            "stage": "clarification",
            "reason": "ambiguous_alarm_intent",
        },
    )


def apply_human_choice(payload: dict[str, Any], choice: str) -> dict[str, Any]:
    if choice not in REMINDER_TYPES:
        return deepcopy(payload)
    next_payload = deepcopy(payload)
    next_payload["reminder_type"] = choice
    return next_payload


def _from_tool_result(intent: str, action: str, message: str, tool_result: dict[str, Any]) -> dict[str, Any]:
    if tool_result.get("ok") is False:
        error = tool_result.get("error") or {"code": "TOOL_FAILED", "message": tool_result.get("message") or MSG_TOOL_FAILED}
        return build_response(
            ok=False,
            action=action,
            intent=intent,
            message=error.get("message", MSG_TOOL_FAILED),
            data=tool_result.get("data") or {},
            error=error,
            ui=tool_result.get("ui"),
            meta=tool_result.get("meta"),
        )

    return build_response(
        ok=True,
        action=action,
        intent=intent,
        message=tool_result.get("message") or message,
        data=tool_result.get("data") if "data" in tool_result else tool_result,
        ui=tool_result.get("ui"),
        meta=tool_result.get("meta"),
    )


def _contains_any(text: str, words: tuple[str, ...]) -> bool:
    return any(word in text for word in words)


def _extract_date_text(text: str) -> str | None:
    for pattern in (r"\d{4}-\d{1,2}-\d{1,2}", r"\d{1,2}/\d{1,2}", r"\d{1,2}월\s*\d{1,2}일"):
        match = re.search(pattern, text)
        if match:
            return match.group(0)
    return next((word for word in _DATE_WORDS if word in text), None)


def _extract_title(text: str) -> str:
    title = re.sub(r"\d{4}-\d{1,2}-\d{1,2}|\d{1,2}/\d{1,2}|\d{1,2}월\s*\d{1,2}일", " ", text)
    for word in (
        ("먹으라고", "사야한다고")
        + _CALENDAR_WORDS
        + _CREATE_WORDS
        + _DELETE_WORDS
        + _LIST_WORDS
        + _SYNC_WORDS
        + _DATE_WORDS
        + _CONSUME_WORDS
        + _SHOPPING_WORDS
        + ("라고", "야한다고", "하라고")
    ):
        title = title.replace(word, " ")
    title = re.sub(r"(해줘|해주세요|할래|할게|좀)$", " ", title.strip())
    title = re.sub(r"\s+", " ", title).strip()
    return title or TITLE_CALENDAR_EVENT


def analyze_intent(text: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = deepcopy(payload or {})
    compact = re.sub(r"\s+", "", text or "")

    # ponytail: keyword routing is enough until the supervisor needs model-based intent ranking.
    if "디바이스" in compact or "기기" in compact or "푸시토큰" in compact:
        intent = "alarm.register_device" if _contains_any(compact, _CREATE_WORDS) else "alarm.list"
    elif "읽음" in compact or "읽었" in compact:
        intent = "alarm.read"
    elif ("알림" in compact or "알람" in compact) and _contains_any(compact, _LIST_WORDS) and not ("캘린더" in compact or "일정" in compact):
        intent = "alarm.list"
    elif _contains_any(compact, _CALENDAR_WORDS):
        if _contains_any(compact, _DELETE_WORDS):
            intent = "calendar.delete"
        elif _contains_any(compact, _SYNC_WORDS):
            intent = "calendar.sync_daily"
        elif _contains_any(compact, _LIST_WORDS) and not _contains_any(compact, _CREATE_WORDS):
            intent = "calendar.list"
        elif _contains_any(compact, _CREATE_WORDS):
            intent = "calendar.create"
        else:
            intent = "calendar.list"
    else:
        intent = "unknown"

    action, _ = _INTENT_ACTIONS.get(intent, ("unknown", MSG_HANDLED))
    if action in {"create_event", "delete_event"}:
        payload.setdefault("title", _extract_title(text))
        date_text = _extract_date_text(text)
        if date_text:
            payload.setdefault("date_text", date_text)
        if action == "create_event" and intent == "calendar.create":
            if _contains_any(compact, _CONSUME_WORDS):
                payload.setdefault("reminder_type", "consume_reminder")
            elif _contains_any(compact, _SHOPPING_WORDS):
                payload.setdefault("reminder_type", "shopping_reminder")
            elif _contains_any(compact, _GENERAL_EVENT_WORDS) or "캘린더" in compact:
                payload.setdefault("reminder_type", "calendar_event")
            elif not payload.get("reminder_type"):
                intent, action = "alarm.clarify", "clarify"

    return {"intent": intent, "action": action, "payload": payload}


def _resolve_request(
    text_or_intent: str | None,
    payload: dict[str, Any] | None,
    intent: str | None,
    action: str | None,
) -> tuple[str, str, dict[str, Any], str]:
    payload = deepcopy(payload or {})
    if intent is None and text_or_intent in _INTENT_ACTIONS:
        intent = text_or_intent
    if intent is None:
        analyzed = analyze_intent(text_or_intent or "", payload)
        return (
            analyzed["intent"],
            action or analyzed["action"],
            analyzed["payload"],
            _INTENT_ACTIONS.get(analyzed["intent"], ("unknown", MSG_HANDLED))[1],
        )

    if intent not in _ALLOWED_INTENTS:
        return "unknown", "unknown", {}, MSG_UNKNOWN

    inferred_action, message = _INTENT_ACTIONS.get(intent, (action or "unknown", MSG_HANDLED))
    return intent, action or inferred_action, payload, message


async def execute_tool(
    action: str,
    payload: dict[str, Any],
    tools: ToolMap | None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not tools or action not in tools:
        return _failure("tool.execute", action, MSG_TOOL_MISSING, "TOOL_NOT_FOUND")

    try:
        result = tools[action](payload, context or {})
        if inspect.isawaitable(result):
            result = await result
    except Exception as exc:
        return _failure("tool.execute", action, str(exc), "TOOL_EXCEPTION")

    return result if isinstance(result, dict) else {"result": result}


async def arun(
    text_or_intent: str | None = None,
    payload: dict[str, Any] | None = None,
    *,
    intent: str | None = None,
    action: str | None = None,
    confirmed: bool = False,
    tool_result: dict[str, Any] | None = None,
    tools: ToolMap | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    intent, action, payload, message = _resolve_request(text_or_intent, payload, intent, action)

    if action == "unknown":
        return _unknown()
    if action == "clarify":
        return _clarification(payload)

    if tool_result is not None:
        return _from_tool_result(intent, action, message, tool_result)

    if action in _CONFIRM_ACTIONS and not confirmed:
        return _confirmation(intent, action, payload)

    if tools:
        result = await execute_tool(action, payload, tools, context)
        if result.get("agent") == AGENT_NAME:
            return result
        if result.get("intent") == "tool.execute":
            result["intent"] = intent
        response = _from_tool_result(intent, action, message, result)
        if action in _CONFIRM_ACTIONS:
            response["meta"] = {
                **response["meta"],
                "human_in_the_loop": True,
                "stage": "executed",
                "confirmed": confirmed,
            }
        return response

    return build_response(ok=True, action=action, intent=intent, message=message, data=deepcopy(payload))


def run(
    text_or_intent: str | None = None,
    payload: dict[str, Any] | None = None,
    *,
    intent: str | None = None,
    action: str | None = None,
    confirmed: bool = False,
    tool_result: dict[str, Any] | None = None,
    tools: ToolMap | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(
            arun(
                text_or_intent,
                payload,
                intent=intent,
                action=action,
                confirmed=confirmed,
                tool_result=tool_result,
                tools=tools,
                context=context,
            )
        )

    if tools:
        return _failure(intent or text_or_intent or "unknown", action or "unknown", MSG_ASYNC_REQUIRED, "ASYNC_RUN_REQUIRED")
    return _resolve_without_tool(text_or_intent, payload, intent, action, confirmed, tool_result)


def _resolve_without_tool(
    text_or_intent: str | None,
    payload: dict[str, Any] | None,
    intent: str | None,
    action: str | None,
    confirmed: bool,
    tool_result: dict[str, Any] | None,
) -> dict[str, Any]:
    intent, action, payload, message = _resolve_request(text_or_intent, payload, intent, action)
    if action == "unknown":
        return _unknown()
    if action == "clarify":
        return _clarification(payload)
    if tool_result is not None:
        return _from_tool_result(intent, action, message, tool_result)
    if action in _CONFIRM_ACTIONS and not confirmed:
        return _confirmation(intent, action, payload)
    return build_response(ok=True, action=action, intent=intent, message=message, data=deepcopy(payload))
