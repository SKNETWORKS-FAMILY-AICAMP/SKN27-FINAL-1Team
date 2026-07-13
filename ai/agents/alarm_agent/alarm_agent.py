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
MSG_DELETE_NOT_FOUND = "밥벌이에서 등록한 일정을 찾을 수 없어요. 밥벌이에서 등록한 일정만 삭제할 수 있어요."
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
_LIST_WORDS = ("조회", "목록", "보여", "확인", "알려", "있어", "있나", "뭐")
_SYNC_WORDS = ("동기화", "자동 알림", "일일 알림", "오늘알림", "아침 알림")
_CALENDAR_WORDS = ("캘린더", "일정", "알림", "알람", "리마인더")
_DATE_WORDS = ("오늘", "어제", "내일", "모레", "지난주", "이번주", "다음주", "지난달", "이번달", "다음달", "방금", "최근")
_WEEKDAY_WORDS = ("월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일")
_CONSUME_WORDS = ("먹", "사용", "소비", "처리", "요리")
_SHOPPING_WORDS = ("사", "구매", "장보", "장볼")
_GENERAL_EVENT_WORDS = ("일정", "미팅", "약속", "예약")
_DATE_PATTERN = r"\d{4}년\s*\d{1,2}월\s*\d{1,2}일|\d{4}-\d{1,2}-\d{1,2}|\d{1,2}/\d{1,2}|\d{1,2}월\s*\d{1,2}일"
_TIME_PATTERN = r"(?:(오전|오후)\s*)?(\d{1,2})(?::(\d{1,2})|시(?:\s*(\d{1,2})분?)?)"
_PURPOSE_PHRASE_PATTERN = (
    r"(먹으라고|먹으라|먹기|먹어야한다고|먹어야 한다고|"
    r"사야한다고|사야 한다고|사기|구매하라고|구매해야한다고|구매하기|"
    r"사용하라고|사용하기|소비하라고|소비하기)"
)
_COMMAND_SUFFIX_PATTERN = (
    r"(?:\s*(?:일정|알림|알람|리마인더))?\s*"
    r"(?:등록|추가|생성|예약|잡아|만들|설정|삭제|지워|취소|없애|조회|목록|보여|확인|알려)"
    r"(?:\s*(?:해줘|해주세요|줘|줘요|해|해요|할래|할게|좀))?\??$"
)


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


def _calendar_subject(payload: dict[str, Any], fallback: str = "일정") -> str:
    reminder_type = payload.get("reminder_type")
    if reminder_type == "consume_reminder":
        return "먹기 알림"
    if reminder_type == "shopping_reminder":
        return "구매 알림"
    return fallback


def _confirmation(intent: str, action: str, payload: dict[str, Any]) -> dict[str, Any]:
    title = payload.get("title") or payload.get("summary") or payload.get("event_key") or TITLE_CALENDAR_EVENT
    if action == "mark_notification_read":
        return build_response(
            ok=True,
            action=action,
            intent=intent,
            message="알림을 읽음 처리할까요?",
            data={"payload": deepcopy(payload)},
            requires_confirmation=True,
            ui={
                "actions": [
                    {"type": "confirm", "label": "읽음 처리", "value": {"intent": intent, "action": action, "payload": payload}},
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
    if action == "register_device_token":
        title = "알림 수신 기기"
    label = LABEL_DELETE if action == "delete_event" else LABEL_SYNC if action == "sync_daily_events" else LABEL_CREATE
    subject = title
    if action in {"create_event", "delete_event"}:
        date_text = payload.get("date_text")
        subject = " ".join(part for part in (date_text, title, _calendar_subject(payload)) if part)
    return build_response(
        ok=True,
        action=action,
        intent=intent,
        message=f"{subject} {label}할까요?",
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
                {
                    "type": "select",
                    "label": "먹기 알림",
                    "value": {
                        "intent": "calendar.create",
                        "action": "create_event",
                        "payload": apply_human_choice(payload, "consume_reminder"),
                    },
                },
                {
                    "type": "select",
                    "label": "구매 알림",
                    "value": {
                        "intent": "calendar.create",
                        "action": "create_event",
                        "payload": apply_human_choice(payload, "shopping_reminder"),
                    },
                },
                {
                    "type": "select",
                    "label": "일반 일정",
                    "value": {
                        "intent": "calendar.create",
                        "action": "create_event",
                        "payload": apply_human_choice(payload, "calendar_event"),
                    },
                },
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


def _intent_message(intent: str, payload: dict[str, Any], default: str) -> str:
    if intent == "alarm.list" and payload.get("unread_only"):
        return "읽지 않은 알림을 조회했어요."
    return default


def _extract_date_text(text: str) -> str | None:
    for pattern in (
        _DATE_PATTERN,
    ):
        match = re.search(pattern, text)
        if match:
            return match.group(0)
    compact = re.sub(r"\s+", "", text or "")
    weekday_match = re.search(r"(지난주|이번주|다음주)?(월요일|화요일|수요일|목요일|금요일|토요일|일요일)", compact)
    if weekday_match:
        return "".join(part for part in weekday_match.groups() if part)
    return next((word for word in sorted(_DATE_WORDS, key=len, reverse=True) if word in compact), None)


def _strip_date_words(text: str) -> str:
    title = re.sub(_DATE_PATTERN, " ", text)
    for weekday in _WEEKDAY_WORDS:
        title = re.sub(r"\s*".join(map(re.escape, weekday)), " ", title)
    for word in sorted(_DATE_WORDS, key=len, reverse=True):
        title = re.sub(r"\s*".join(map(re.escape, word)), " ", title)
    return title


def _extract_time(text: str) -> tuple[int, int] | None:
    match = re.search(_TIME_PATTERN, text or "")
    if not match:
        return None
    meridiem, hour_text, colon_minute, korean_minute = match.groups()
    hour = int(hour_text)
    minute = int(colon_minute or korean_minute or 0)
    if meridiem == "오후" and hour < 12:
        hour += 12
    elif meridiem == "오전" and hour == 12:
        hour = 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour, minute


def _extract_title(text: str) -> str:
    title = _strip_date_words(text)
    title = re.sub(_TIME_PATTERN, " ", title)
    title = re.sub(_PURPOSE_PHRASE_PATTERN, " ", title)
    title = re.sub(_COMMAND_SUFFIX_PATTERN, " ", title.strip())
    title = re.sub(r"^(?:등록한|예약한|추가한)\s*", " ", title.strip())
    title = re.sub(r"(?:해줘|해주세요|줘|줘요|좀|\?)$", " ", title.strip())
    title = re.sub(r"(?:을|를|은|는|이|가)$", " ", title.strip())
    title = re.sub(r"\s+", " ", title).strip()
    return title or TITLE_CALENDAR_EVENT


def _is_unread_alarm_query(compact: str) -> bool:
    return any(word in compact for word in ("읽지않은", "안읽은", "미확인", "미읽음"))


def analyze_intent(text: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = deepcopy(payload or {})
    compact = re.sub(r"\s+", "", text or "")

    # ponytail: keyword routing is enough until the supervisor needs model-based intent ranking.
    if "디바이스" in compact or "기기" in compact or "푸시토큰" in compact:
        intent = "alarm.register_device" if _contains_any(compact, _CREATE_WORDS) else "alarm.list"
    elif _is_unread_alarm_query(compact):
        intent = "alarm.list"
        payload.setdefault("unread_only", True)
    elif "읽음" in compact or "읽었" in compact:
        intent = "alarm.read"
    elif ("알림" in compact or "알람" in compact) and _contains_any(compact, _LIST_WORDS) and not ("캘린더" in compact or "일정" in compact):
        intent = "alarm.list"
    elif _contains_any(compact, _CALENDAR_WORDS):
        if _contains_any(compact, _DELETE_WORDS):
            intent = "calendar.delete"
        elif _contains_any(text, _SYNC_WORDS):
            intent = "calendar.sync_daily"
        elif _contains_any(compact, _LIST_WORDS):
            intent = "calendar.list"
        elif _contains_any(compact, _CREATE_WORDS):
            intent = "calendar.create"
        else:
            intent = "calendar.list"
    else:
        intent = "unknown"

    action, _ = _INTENT_ACTIONS.get(intent, ("unknown", MSG_HANDLED))
    if action in {"list_events", "list_notifications", "sync_daily_events"}:
        date_text = _extract_date_text(text)
        if date_text:
            payload.setdefault("date_text", date_text)
    if action in {"create_event", "delete_event"}:
        payload.setdefault("title", _extract_title(text))
        date_text = _extract_date_text(text)
        if date_text:
            payload.setdefault("date_text", date_text)
        parsed_time = _extract_time(text)
        if parsed_time:
            payload.setdefault("hour", parsed_time[0])
            payload.setdefault("minute", parsed_time[1])
        if action == "create_event" and intent == "calendar.create":
            if _contains_any(compact, _GENERAL_EVENT_WORDS) or "캘린더" in compact:
                payload.setdefault("reminder_type", "calendar_event")
            elif _contains_any(compact, _CONSUME_WORDS):
                payload.setdefault("reminder_type", "consume_reminder")
            elif _contains_any(compact, _SHOPPING_WORDS):
                payload.setdefault("reminder_type", "shopping_reminder")
            elif not payload.get("reminder_type"):
                intent, action = "alarm.clarify", "clarify"

    return {"intent": intent, "action": action, "payload": payload}


def _candidate_matches_title(candidate: dict[str, Any], title: str | None) -> bool:
    if not title or title == TITLE_CALENDAR_EVENT:
        return True
    expected = re.sub(r"\s+", "", title)
    actual = re.sub(r"\s+", "", candidate.get("title") or candidate.get("summary") or "")
    return expected in actual or actual in expected


def _fill_calendar_payload(text: str | None, intent: str, action: str, payload: dict[str, Any]) -> dict[str, Any]:
    if text in _INTENT_ACTIONS:
        text = None
    if action in {"list_events", "create_event", "delete_event", "sync_daily_events"}:
        date_text = _extract_date_text(text or "")
        if date_text:
            payload.setdefault("date_text", date_text)
    if action in {"create_event", "delete_event"}:
        payload.setdefault("title", _extract_title(text or ""))
        parsed_time = _extract_time(text or "")
        if parsed_time:
            payload.setdefault("hour", parsed_time[0])
            payload.setdefault("minute", parsed_time[1])
    return payload


def _delete_candidate_response(intent: str, action: str, payload: dict[str, Any], tool_result: dict[str, Any]) -> dict[str, Any]:
    if tool_result.get("ok") is False:
        return _from_tool_result(intent, "list_events", MSG_CALENDAR_LIST, tool_result)

    events = (tool_result.get("data") or {}).get("events") or []
    title = payload.get("title")
    candidates = [event for event in events if event.get("eventKey") and _candidate_matches_title(event, title)]

    if not candidates:
        return build_response(ok=False, action=action, intent=intent, message=MSG_DELETE_NOT_FOUND, error={"code": "CALENDAR_EVENT_NOT_FOUND", "message": MSG_DELETE_NOT_FOUND})

    if len(candidates) == 1:
        event = candidates[0]
        next_payload = {
            **payload,
            "event_key": event["eventKey"],
            "title": event.get("title") or title or TITLE_CALENDAR_EVENT,
            "date_text": payload.get("date_text") or event.get("dateKey"),
        }
        return _confirmation(intent, action, next_payload)

    return build_response(
        ok=True,
        action=action,
        intent=intent,
        message="삭제할 일정을 선택해주세요.",
        data={"candidates": candidates},
        requires_confirmation=True,
        ui={
            "actions": [
                {
                    "type": "confirm",
                    "label": f"{event.get('dateKey') or ''} {event.get('title') or TITLE_CALENDAR_EVENT} 삭제",
                    "value": {
                        "intent": intent,
                        "action": action,
                        "payload": {
                            **payload,
                            "event_key": event["eventKey"],
                            "title": event.get("title") or title or TITLE_CALENDAR_EVENT,
                            "date_text": payload.get("date_text") or event.get("dateKey"),
                        },
                    },
                }
                for event in candidates[:5]
            ]
        },
        meta={"human_in_the_loop": True, "stage": "select_delete_candidate"},
    )


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
        default_message = _INTENT_ACTIONS.get(analyzed["intent"], ("unknown", MSG_HANDLED))[1]
        return (
            analyzed["intent"],
            action or analyzed["action"],
            analyzed["payload"],
            _intent_message(analyzed["intent"], analyzed["payload"], default_message),
        )

    if intent not in _ALLOWED_INTENTS:
        return "unknown", "unknown", {}, MSG_UNKNOWN

    inferred_action, message = _INTENT_ACTIONS.get(intent, (action or "unknown", MSG_HANDLED))
    resolved_action = action or inferred_action
    payload = _fill_calendar_payload(text_or_intent, intent, resolved_action, payload)
    return intent, resolved_action, payload, _intent_message(intent, payload, message)


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

    if action == "delete_event" and not payload.get("event_key"):
        if tools and "list_events" in tools:
            result = await execute_tool("list_events", payload, tools, context)
            return _delete_candidate_response(intent, action, payload, result)
        return build_response(ok=False, action=action, intent=intent, message=MSG_DELETE_NOT_FOUND, error={"code": "CALENDAR_EVENT_NOT_FOUND", "message": MSG_DELETE_NOT_FOUND})

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
