import pytest

from ai.agents.alarm_agent.alarm_agent import (
    _extract_date_text,
    _extract_title,
    analyze_intent,
    apply_human_choice,
    run,
)


@pytest.mark.parametrize(
    ("text", "intent", "action", "reminder_type"),
    [
        ("알림 목록 보여줘", "alarm.list", "list_notifications", None),
        ("알림 읽음 처리해줘", "alarm.read", "mark_notification_read", None),
        ("푸시토큰 등록해줘", "alarm.register_device", "register_device_token", None),
        ("기기 등록해줘", "alarm.register_device", "register_device_token", None),
        ("캘린더 일정 보여줘", "calendar.list", "list_events", None),
        ("오늘 알림 동기화해줘", "calendar.sync_daily", "sync_daily_events", None),
        ("아침 자동 알림 동기화해줘", "calendar.sync_daily", "sync_daily_events", None),
        ("내일 병원 일정 등록해줘", "calendar.create", "create_event", "calendar_event"),
        ("내일 두부 먹으라고 알림 등록해줘", "calendar.create", "create_event", "consume_reminder"),
        ("내일 두부 사용하라고 알림 등록해줘", "calendar.create", "create_event", "consume_reminder"),
        ("내일 두부 사야한다고 알림 등록해줘", "calendar.create", "create_event", "shopping_reminder"),
        ("내일 두부 구매 알림 등록해줘", "calendar.create", "create_event", "shopping_reminder"),
        ("캘린더 일정 삭제해줘", "calendar.delete", "delete_event", None),
        ("캘린더 일정 취소해줘", "calendar.delete", "delete_event", None),
        ("그냥 잡담이야", "unknown", "unknown", None),
    ],
)
def test_alarm_agent_feature_intent_matrix(text, intent, action, reminder_type):
    result = analyze_intent(text)

    assert result["intent"] == intent
    assert result["action"] == action
    if reminder_type:
        assert result["payload"]["reminder_type"] == reminder_type


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("오늘 두부 알림", "오늘"),
        ("내일 두부 알림", "내일"),
        ("모레 두부 알림", "모레"),
        ("2026-07-07 두부 알림", "2026-07-07"),
        ("7/8 두부 알림", "7/8"),
        ("7월 9일 두부 알림", "7월 9일"),
        ("날짜 없는 알림", None),
    ],
)
def test_alarm_agent_feature_extracts_supported_date_text(text, expected):
    assert _extract_date_text(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("내일 두부 먹으라고 알림 등록해줘", "두부"),
        ("모레 우유 사야한다고 알림 등록해줘", "우유"),
        ("2026-07-07 병원 일정 등록해줘", "병원"),
        ("7월 9일 미팅 일정 등록해줘", "미팅"),
        ("알림 등록해줘", "캘린더 일정"),
    ],
)
def test_alarm_agent_feature_extracts_calendar_title(text, expected):
    assert _extract_title(text) == expected


@pytest.mark.parametrize(
    ("choice", "expected"),
    [
        ("consume_reminder", "consume_reminder"),
        ("shopping_reminder", "shopping_reminder"),
        ("calendar_event", "calendar_event"),
        ("bad_choice", None),
    ],
)
def test_alarm_agent_feature_applies_or_ignores_human_choice(choice, expected):
    payload = {"title": "두부", "date_text": "내일"}

    result = apply_human_choice(payload, choice)

    assert result.get("reminder_type") == expected
    assert payload == {"title": "두부", "date_text": "내일"}


@pytest.mark.parametrize(
    ("intent", "action", "payload"),
    [
        ("calendar.create", "create_event", {"title": "두부 알림", "date_text": "내일"}),
        ("calendar.delete", "delete_event", {"title": "두부 알림", "event_key": "calendar-agent-7-x"}),
        ("calendar.sync_daily", "sync_daily_events", {"title": "두부 알림"}),
        ("alarm.read", "mark_notification_read", {"title": "두부 알림"}),
        ("alarm.register_device", "register_device_token", {"title": "두부 알림"}),
    ],
)
def test_alarm_agent_feature_mutating_actions_require_confirmation(intent, action, payload):
    result = run(intent, payload)

    assert result["ok"] is True
    assert result["action"] == action
    assert result["requires_confirmation"] is True
    assert result["ui"]["actions"][0]["type"] == "confirm"
