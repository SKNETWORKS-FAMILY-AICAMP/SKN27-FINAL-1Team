import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from ai.agents.alarm_agent import ALARM_AGENT_TOOLS, apply_human_choice, analyze_intent, arun, build_response, run
from ai.agents.alarm_agent import tools as alarm_tools
from app.backend.api.calendar.calendar_api import _event_key_belongs_to_user


def test_alarm_agent_response_shape():
    result = build_response(
        ok=True,
        action="list_notifications",
        intent="alarm.list",
        message="ok",
    )

    assert result == {
        "ok": True,
        "agent": "alarm",
        "action": "list_notifications",
        "intent": "alarm.list",
        "message": "ok",
        "data": {},
        "error": None,
        "requires_confirmation": False,
        "ui": {"actions": [], "cards": [], "sources": []},
        "meta": {},
    }


def test_alarm_agent_clarifies_ambiguous_alarm_text():
    result = run("\ub0b4\uc77c \ub450\ubd80 \uc54c\ub9bc \ub4f1\ub85d\ud574\uc918")

    assert result["ok"] is True
    assert result["intent"] == "alarm.clarify"
    assert result["action"] == "clarify"
    assert result["requires_confirmation"] is True
    assert result["data"]["title"] == "\ub450\ubd80"
    assert result["data"]["candidates"] == ["consume_reminder", "shopping_reminder", "calendar_event"]
    assert result["meta"] == {
        "human_in_the_loop": True,
        "stage": "clarification",
        "reason": "ambiguous_alarm_intent",
    }


def test_alarm_agent_analyzes_consume_alarm_text():
    result = analyze_intent("\ub0b4\uc77c \ub450\ubd80 \uba39\uc73c\ub77c\uace0 \uc54c\ub9bc \ub4f1\ub85d\ud574\uc918")

    assert result["intent"] == "calendar.create"
    assert result["action"] == "create_event"
    assert result["payload"]["title"] == "\ub450\ubd80"
    assert result["payload"]["date_text"] == "\ub0b4\uc77c"
    assert result["payload"]["reminder_type"] == "consume_reminder"


def test_alarm_agent_analyzes_shopping_alarm_text():
    result = analyze_intent("\ub0b4\uc77c \ub450\ubd80 \uc0ac\uc57c\ud55c\ub2e4\uace0 \uc54c\ub9bc \ub4f1\ub85d\ud574\uc918")

    assert result["intent"] == "calendar.create"
    assert result["action"] == "create_event"
    assert result["payload"]["reminder_type"] == "shopping_reminder"


def test_alarm_agent_date_lookup_stays_calendar_list():
    cases = {
        "7\uc6d4 8\uc77c \uc77c\uc815 \uc870\ud68c\ud574\uc918": "7\uc6d4 8\uc77c",
        "2026\ub144 7\uc6d4 8\uc77c \uc77c\uc815 \uc54c\ub824\uc918": "2026\ub144 7\uc6d4 8\uc77c",
        "\ub0b4\uc77c \uc77c\uc815 \uc788\uc5b4?": "\ub0b4\uc77c",
        "\uc5b4\uc81c \uc77c\uc815 \ubb50\uc600\uc9c0?": "\uc5b4\uc81c",
        "\uc774\ubc88\uc8fc \uc77c\uc815 \uc870\ud68c": "\uc774\ubc88\uc8fc",
        "\ub2e4\uc74c\uc8fc \uc77c\uc815 \ubb50 \uc788\uc5b4?": "\ub2e4\uc74c\uc8fc",
    }

    for text, date_text in cases.items():
        result = analyze_intent(text)
        assert result["intent"] == "calendar.list"
        assert result["action"] == "list_events"
        assert result["payload"]["date_text"] == date_text


def test_alarm_agent_calendar_list_tool_receives_requested_date_text():
    calls = []

    def list_tool(payload, context):
        calls.append(payload)
        return {"ok": True, "data": {"events": []}}

    result = run("\uc5b4\uc81c \uc77c\uc815 \ubb50\uc600\uc9c0?", tools={"list_events": list_tool}, context={"db": MagicMock(), "user_id": 7})

    assert result["ok"] is True
    assert calls[0]["date_text"] == "\uc5b4\uc81c"


def test_alarm_agent_calendar_event_confirmation_includes_date_title_and_type():
    result = run("\ub0b4\uc77c \ud48b\uc0b4\ud558\uae30 \uc77c\uc815 \ub4f1\ub85d\ud574\uc918")

    assert result["message"] == "\ub0b4\uc77c \ud48b\uc0b4\ud558\uae30 \uc77c\uc815 \ub4f1\ub85d\ud560\uae4c\uc694?"
    assert result["data"]["payload"] == {
        "title": "\ud48b\uc0b4\ud558\uae30",
        "date_text": "\ub0b4\uc77c",
        "reminder_type": "calendar_event",
    }


def test_alarm_agent_shopping_schedule_keeps_shopping_title():
    result = run("\ub0b4\uc77c \uc7a5\ubcf4\uae30 \uc77c\uc815 \ub4f1\ub85d\ud574\uc918")

    assert result["message"] == "\ub0b4\uc77c \uc7a5\ubcf4\uae30 \uc77c\uc815 \ub4f1\ub85d\ud560\uae4c\uc694?"
    assert result["data"]["payload"]["title"] == "\uc7a5\ubcf4\uae30"
    assert result["data"]["payload"]["reminder_type"] == "calendar_event"


def test_alarm_agent_clarify_button_survives_legacy_supervisor_roundtrip():
    clarify = run("\ub0b4\uc77c \uc6d4\ub4dc\ucef5\uacbd\uae30 \uc54c\ub9bc \ub4f1\ub85d\ud574\uc918")
    general_action = clarify["ui"]["actions"][2]
    legacy_payload = general_action["value"]["payload"]
    calls = []

    def create_tool(payload, context):
        calls.append(payload)
        return {"ok": True, "data": {"event_id": "google-event", "title": payload["title"]}}

    result = run(
        "\ud655\uc778:add_calendar_event:\uc6d4\ub4dc\ucef5\uacbd\uae30:\ub0b4\uc77c",
        payload={"title": legacy_payload["title"], "date_text": legacy_payload["date_text"]},
        intent="calendar.create",
        action="create_event",
        confirmed=True,
        tools={"create_event": create_tool},
        context={"db": MagicMock(), "user_id": 7},
    )

    assert result["ok"] is True
    assert calls == [{"title": "\uc6d4\ub4dc\ucef5\uacbd\uae30", "date_text": "\ub0b4\uc77c", "reminder_type": "calendar_event"}]


def test_alarm_agent_applies_human_choice_to_payload():
    payload = apply_human_choice({"title": "\ub450\ubd80", "date_text": "\ub0b4\uc77c"}, "shopping_reminder")

    assert payload == {"title": "\ub450\ubd80", "date_text": "\ub0b4\uc77c", "reminder_type": "shopping_reminder"}


def test_alarm_agent_rejects_non_alarm_calendar_intent():
    result = run(intent="recipe.recommend", payload={"ingredient": "\ub450\ubd80"})

    assert result["ok"] is False
    assert result["intent"] == "unknown"
    assert result["action"] == "unknown"
    assert result["error"]["code"] == "UNKNOWN_INTENT"


def test_alarm_agent_accepts_alarm_word():
    result = analyze_intent("\ub0b4\uc77c \ub450\ubd80 \uba39\uc73c\ub77c\uace0 \uc54c\ub78c \ub4f1\ub85d\ud574\uc918")

    assert result["intent"] == "calendar.create"
    assert result["action"] == "create_event"
    assert result["payload"]["reminder_type"] == "consume_reminder"


def test_alarm_agent_calendar_create_requires_confirmation():
    result = run("calendar.create", {"title": "\ub450\ubd80 \uc54c\ub9bc"})

    assert result["ok"] is True
    assert result["agent"] == "alarm"
    assert result["action"] == "create_event"
    assert result["requires_confirmation"] is True
    assert result["ui"]["actions"][0]["type"] == "confirm"
    assert result["meta"]["human_in_the_loop"] is True
    assert result["meta"]["stage"] == "confirmation"


def test_alarm_agent_calls_sync_tool_after_confirmation():
    calls = []

    def tool(payload, context):
        calls.append((payload, context))
        return {"data": {"event_id": "google-event"}}

    result = run(
        "calendar.create",
        {"title": "\ub450\ubd80 \uc54c\ub9bc"},
        confirmed=True,
        tools={"create_event": tool},
        context={"user_id": 7},
    )

    assert result["ok"] is True
    assert result["requires_confirmation"] is False
    assert result["data"]["event_id"] == "google-event"
    assert result["meta"] == {"human_in_the_loop": True, "stage": "executed", "confirmed": True}
    assert calls == [({"title": "\ub450\ubd80 \uc54c\ub9bc"}, {"user_id": 7})]


def test_alarm_agent_calls_async_tool_after_confirmation():
    async def tool(payload, context):
        return {"ok": True, "message": "done", "data": {"user_id": context["user_id"], "title": payload["title"]}}

    result = asyncio.run(
        arun(
            "\ub0b4\uc77c \ub450\ubd80 \uc54c\ub9bc \ub4f1\ub85d\ud574\uc918",
            confirmed=True,
            tools={"create_event": tool},
            payload={"reminder_type": "consume_reminder"},
            context={"user_id": 7},
        )
    )

    assert result["ok"] is True
    assert result["message"] == "done"
    assert result["data"] == {"user_id": 7, "title": "\ub450\ubd80"}
    assert result["meta"] == {"human_in_the_loop": True, "stage": "executed", "confirmed": True}


def test_alarm_agent_mutating_alarm_actions_require_confirmation():
    result = run("alarm.register_device", {"device_token": "token"})

    assert result["action"] == "register_device_token"
    assert result["requires_confirmation"] is True
    assert result["meta"]["human_in_the_loop"] is True


def test_alarm_agent_wraps_tool_result():
    result = run(
        "calendar.create",
        confirmed=True,
        tool_result={"event_id": "google-event", "html_link": "https://calendar/event"},
    )

    assert result["ok"] is True
    assert result["requires_confirmation"] is False
    assert result["data"]["event_id"] == "google-event"


def test_alarm_agent_delete_tool_result_requires_deleted_true():
    result = run(
        "calendar.delete",
        {"event_key": "calendar-agent-7-x"},
        confirmed=True,
        tool_result={"data": {"event_key": "calendar-agent-7-x", "deleted": False}},
    )

    assert result["ok"] is False
    assert result["message"] == "밥벌이에서 등록한 일정을 찾을 수 없어요. 밥벌이에서 등록한 일정만 삭제할 수 있어요."
    assert result["error"]["code"] == "CALENDAR_EVENT_NOT_FOUND"


def test_alarm_agent_real_create_tool_calls_calendar_helpers(monkeypatch):
    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

    create_once = AsyncMock(return_value={"event_id": "google-event", "html_link": "https://calendar/event"})
    monkeypatch.setattr(alarm_tools.calendar_api, "_get_google_integration", lambda db, user_id: SimpleNamespace(calendar_id="primary"))
    monkeypatch.setattr(alarm_tools.calendar_api, "_get_access_token", AsyncMock(return_value="access-token"))
    monkeypatch.setattr(alarm_tools.calendar_api, "_create_event_once", create_once)
    monkeypatch.setattr(alarm_tools.httpx, "AsyncClient", lambda **_: FakeClient())

    result = asyncio.run(
        arun(
            "\ub0b4\uc77c \ub450\ubd80 \uc54c\ub78c \ub4f1\ub85d\ud574\uc918",
            confirmed=True,
            tools=ALARM_AGENT_TOOLS,
            payload={"reminder_type": "consume_reminder"},
            context={"db": MagicMock(), "user_id": 7},
        )
    )

    assert result["ok"] is True
    assert result["data"]["event_id"] == "google-event"
    assert result["data"]["event_key"].startswith("calendar-agent-7-")
    assert create_once.await_args.args[1:4] == ("primary", "access-token", result["data"]["event_key"])


def test_alarm_agent_real_delete_tool_calls_calendar_helpers(monkeypatch):
    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

    delete_once = AsyncMock(return_value={"event_key": "calendar-agent-7-x", "deleted": True})
    monkeypatch.setattr(alarm_tools.calendar_api, "_get_google_integration", lambda db, user_id: SimpleNamespace(calendar_id="primary"))
    monkeypatch.setattr(alarm_tools.calendar_api, "_get_access_token", AsyncMock(return_value="access-token"))
    monkeypatch.setattr(alarm_tools.calendar_api, "_delete_event_once", delete_once)
    monkeypatch.setattr(alarm_tools.httpx, "AsyncClient", lambda **_: FakeClient())

    result = asyncio.run(
        arun(
            "calendar.delete",
            {"event_key": "calendar-agent-7-x"},
            confirmed=True,
            tools=ALARM_AGENT_TOOLS,
            context={"db": MagicMock(), "user_id": 7},
        )
    )

    assert result["ok"] is True
    assert result["data"] == {"event_key": "calendar-agent-7-x", "deleted": True}
    delete_once.assert_awaited_once()


def test_alarm_agent_delete_without_event_key_resolves_candidate_before_confirm():
    calls = []

    def list_tool(payload, context):
        calls.append((payload, context))
        return {
            "ok": True,
            "data": {
                "events": [
                    {"eventKey": "calendar-agent-7-x", "dateKey": "\ub0b4\uc77c", "title": "\ubbf8\ud305"},
                ]
            },
        }

    result = asyncio.run(
        arun(
            "\ub0b4\uc77c \ubbf8\ud305 \uc77c\uc815 \uc0ad\uc81c\ud574\uc918",
            tools={"list_events": list_tool},
            context={"db": MagicMock(), "user_id": 7},
        )
    )

    assert result["ok"] is True
    assert result["requires_confirmation"] is True
    assert result["message"] == "\ub0b4\uc77c \ubbf8\ud305 \uc77c\uc815 \uc0ad\uc81c\ud560\uae4c\uc694?"
    assert result["data"]["payload"]["event_key"] == "calendar-agent-7-x"
    assert calls[0][0]["date_text"] == "\ub0b4\uc77c"


def test_alarm_agent_delete_without_candidate_uses_user_message():
    def list_tool(payload, context):
        return {"ok": True, "data": {"events": []}}

    result = asyncio.run(
        arun(
            "\ub0b4\uc77c \ubbf8\ud305 \uc77c\uc815 \uc0ad\uc81c\ud574\uc918",
            tools={"list_events": list_tool},
            context={"db": MagicMock(), "user_id": 7},
        )
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "CALENDAR_EVENT_NOT_FOUND"
    assert "\ubc25\ubc8c\uc774\uc5d0\uc11c \ub4f1\ub85d\ud55c \uc77c\uc815\ub9cc \uc0ad\uc81c" in result["message"]


def test_alarm_agent_real_list_tool_calls_calendar_api(monkeypatch):
    list_events = AsyncMock(return_value={"events": [{"eventKey": "calendar-agent-7-x"}]})
    monkeypatch.setattr(alarm_tools.calendar_api, "list_google_calendar_events", list_events)

    result = asyncio.run(
        arun(
            "calendar.list",
            {"date_text": "\ub0b4\uc77c"},
            tools=ALARM_AGENT_TOOLS,
            context={"db": MagicMock(), "user_id": 7},
        )
    )

    assert result["ok"] is True
    assert result["data"] == {"events": [{"eventKey": "calendar-agent-7-x"}]}
    list_events.assert_awaited_once()


def test_alarm_agent_tools_include_sync_daily():
    assert {
        "create_event",
        "delete_event",
        "list_events",
        "sync_daily_events",
        "list_notifications",
        "mark_notification_read",
        "register_device_token",
    } <= set(ALARM_AGENT_TOOLS)


def test_calendar_agent_event_key_is_visible_to_calendar_api():
    assert _event_key_belongs_to_user("calendar-agent-7-2026-07-07T09:00:00+09:00-abcd1234", 7)
    assert not _event_key_belongs_to_user("calendar-agent-17-2026-07-07T09:00:00+09:00-abcd1234", 7)
