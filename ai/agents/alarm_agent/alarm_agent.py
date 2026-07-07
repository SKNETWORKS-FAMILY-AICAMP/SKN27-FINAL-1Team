from __future__ import annotations

import asyncio
import inspect
import re
from copy import deepcopy
from typing import Any, Callable


AGENT_NAME = "alarm"
ToolMap = dict[str, Callable[[dict[str, Any], dict[str, Any]], Any]]
REMINDER_TYPES = {"consume_reminder", "shopping_reminder", "calendar_event"}

MSG_CALENDAR_LIST = "\uce98\ub9b0\ub354 \uc77c\uc815\uc744 \uc870\ud68c\ud588\uc5b4\uc694."
MSG_CALENDAR_CREATE = "\uce98\ub9b0\ub354 \uc77c\uc815\uc744 \ub4f1\ub85d\ud588\uc5b4\uc694."
MSG_CALENDAR_DELETE = "\uce98\ub9b0\ub354 \uc77c\uc815\uc744 \uc0ad\uc81c\ud588\uc5b4\uc694."
MSG_CALENDAR_SYNC = "\uc624\ub298 \uc54c\ub9bc \uc77c\uc815\uc744 \ub3d9\uae30\ud654\ud588\uc5b4\uc694."
MSG_ALARM_LIST = "\uc54c\ub9bc \ubaa9\ub85d\uc744 \uc870\ud68c\ud588\uc5b4\uc694."
MSG_ALARM_READ = "\uc54c\ub9bc\uc744 \uc77d\uc74c \ucc98\ub9ac\ud588\uc5b4\uc694."
MSG_ALARM_DEVICE = "\uc54c\ub9bc \uc218\uc2e0 \uae30\uae30\ub97c \ub4f1\ub85d\ud588\uc5b4\uc694."
MSG_CLARIFY = "\uc5b4\ub5a4 \uc54c\ub9bc\uc778\uc9c0 \uc54c\ub824\uc8fc\uc138\uc694. \uba39\uae30/\uad6c\ub9e4/\uc77c\ubc18 \uc77c\uc815 \uc911 \ud558\ub098\ub85c \ub4f1\ub85d\ud560 \uc218 \uc788\uc5b4\uc694."
MSG_HANDLED = "\uc694\uccad\uc744 \ucc98\ub9ac\ud588\uc5b4\uc694."
MSG_UNKNOWN = "\uc54c\ub9bc/\uce98\ub9b0\ub354 agent\uac00 \ucc98\ub9ac\ud560 \uc218 \uc5c6\ub294 \uc694\uccad\uc774\uc5d0\uc694."
MSG_TOOL_MISSING = "\uc2e4\ud589\ud560 \ub3c4\uad6c\uac00 \uc5f0\uacb0\ub418\uc9c0 \uc54a\uc558\uc5b4\uc694."
MSG_TOOL_FAILED = "\ub3c4\uad6c \uc2e4\ud589\uc5d0 \uc2e4\ud328\ud588\uc5b4\uc694."
MSG_ASYNC_REQUIRED = "\ube44\ub3d9\uae30 \ud658\uacbd\uc5d0\uc11c\ub294 arun()\uc744 \ud638\ucd9c\ud574\uc8fc\uc138\uc694."
TITLE_CALENDAR_EVENT = "\uce98\ub9b0\ub354 \uc77c\uc815"
LABEL_CREATE = "\ub4f1\ub85d"
LABEL_DELETE = "\uc0ad\uc81c"
LABEL_SYNC = "\ub3d9\uae30\ud654"
LABEL_CANCEL = "\ucde8\uc18c"

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

_CREATE_WORDS = ("\ub4f1\ub85d", "\ucd94\uac00", "\uc0dd\uc131", "\uc608\uc57d", "\uc7a1\uc544", "\ub9cc\ub4e4", "\uc124\uc815")
_DELETE_WORDS = ("\uc0ad\uc81c", "\uc9c0\uc6cc", "\ucde8\uc18c", "\uc5c6\uc560")
_LIST_WORDS = ("\uc870\ud68c", "\ubaa9\ub85d", "\ubcf4\uc5ec", "\ud655\uc778", "\uc54c\ub824")
_SYNC_WORDS = ("\ub3d9\uae30\ud654", "\uc790\ub3d9", "\uc77c\uc77c", "\uc624\ub298\uc54c\ub9bc", "\uc544\uce68")
_CALENDAR_WORDS = ("\uce98\ub9b0\ub354", "\uc77c\uc815", "\uc54c\ub9bc", "\uc54c\ub78c", "\ub9ac\ub9c8\uc778\ub354")
_DATE_WORDS = ("\uc624\ub298", "\ub0b4\uc77c", "\ubaa8\ub808")
_CONSUME_WORDS = ("\uba39", "\uc0ac\uc6a9", "\uc18c\ube44", "\ucc98\ub9ac", "\uc694\ub9ac")
_SHOPPING_WORDS = ("\uc0ac", "\uad6c\ub9e4", "\uc7a5\ubcf4", "\uc7a5\ubcfc")
_GENERAL_EVENT_WORDS = ("\uc77c\uc815", "\ubbf8\ud305", "\uc57d\uc18d", "\uc608\uc57d")


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
        message=f"{title} {label}\ud560\uae4c\uc694?",
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
                {"type": "select", "label": "\uba39\uae30 \uc54c\ub9bc", "value": "consume_reminder"},
                {"type": "select", "label": "\uad6c\ub9e4 \uc54c\ub9bc", "value": "shopping_reminder"},
                {"type": "select", "label": "\uc77c\ubc18 \uc77c\uc815", "value": "calendar_event"},
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
    for pattern in (r"\d{4}-\d{1,2}-\d{1,2}", r"\d{1,2}/\d{1,2}", r"\d{1,2}\uc6d4\s*\d{1,2}\uc77c"):
        match = re.search(pattern, text)
        if match:
            return match.group(0)
    return next((word for word in _DATE_WORDS if word in text), None)


def _extract_title(text: str) -> str:
    title = re.sub(r"\d{4}-\d{1,2}-\d{1,2}|\d{1,2}/\d{1,2}|\d{1,2}\uc6d4\s*\d{1,2}\uc77c", " ", text)
    for word in (
        ("\uba39\uc73c\ub77c\uace0", "\uc0ac\uc57c\ud55c\ub2e4\uace0")
        + _CALENDAR_WORDS
        + _CREATE_WORDS
        + _DELETE_WORDS
        + _LIST_WORDS
        + _SYNC_WORDS
        + _DATE_WORDS
        + _CONSUME_WORDS
        + _SHOPPING_WORDS
        + ("\ub77c\uace0", "\uc57c\ud55c\ub2e4\uace0", "\ud558\ub77c\uace0")
    ):
        title = title.replace(word, " ")
    title = re.sub(r"(\ud574\uc918|\ud574\uc8fc\uc138\uc694|\ud560\ub798|\ud560\uac8c|\uc880)$", " ", title.strip())
    title = re.sub(r"\s+", " ", title).strip()
    return title or TITLE_CALENDAR_EVENT


def analyze_intent(text: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = deepcopy(payload or {})
    compact = re.sub(r"\s+", "", text or "")

    # ponytail: keyword routing is enough until the supervisor needs model-based intent ranking.
    if "\ub514\ubc14\uc774\uc2a4" in compact or "\uae30\uae30" in compact or "\ud478\uc2dc\ud1a0\ud070" in compact:
        intent = "alarm.register_device" if _contains_any(compact, _CREATE_WORDS) else "alarm.list"
    elif "\uc77d\uc74c" in compact or "\uc77d\uc5c8" in compact:
        intent = "alarm.read"
    elif ("\uc54c\ub9bc" in compact or "\uc54c\ub78c" in compact) and _contains_any(compact, _LIST_WORDS) and not ("\uce98\ub9b0\ub354" in compact or "\uc77c\uc815" in compact):
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
            elif _contains_any(compact, _GENERAL_EVENT_WORDS) or "\uce98\ub9b0\ub354" in compact:
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
