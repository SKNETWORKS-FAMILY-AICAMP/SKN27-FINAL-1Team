"""Alarm·Shopping Agent의 도구 호출 안전성과 인자 전달을 평가합니다."""

from ai.agents.alarm_agent.alarm_agent import run as run_alarm_agent
from ai.agents.shopping_agent import shopping_graph


def test_alarm_create_tool_is_not_called_before_confirmation():
    """일정 생성은 미리보기 단계에서 외부 캘린더 도구를 호출하면 안 됩니다."""
    calls = []

    def create_event(payload, context):
        """호출 여부와 전달 인자를 기록하는 캘린더 도구 대역입니다."""
        calls.append((payload, context))
        return {"ok": True, "data": {"event_id": "event-1"}}

    result = run_alarm_agent(
        intent="calendar.create",
        action="create_event",
        payload={"title": "장보기", "date_text": "내일", "hour": 19, "minute": 0},
        tools={"create_event": create_event},
        context={"user_id": 7},
    )

    assert calls == []
    assert result["requires_confirmation"] is True
    assert result["meta"]["stage"] == "confirmation"


def test_alarm_create_tool_receives_exact_payload_after_confirmation():
    """확인된 일정 생성만 캘린더 도구에 제목·날짜·시간을 그대로 전달해야 합니다."""
    calls = []
    payload = {"title": "장보기", "date_text": "내일", "hour": 19, "minute": 0}

    def create_event(tool_payload, context):
        """도구 호출 인자를 기록하고 성공 결과를 반환합니다."""
        calls.append((tool_payload, context))
        return {"ok": True, "data": {"event_id": "event-1"}}

    result = run_alarm_agent(
        intent="calendar.create",
        action="create_event",
        payload=payload,
        confirmed=True,
        tools={"create_event": create_event},
        context={"user_id": 7},
    )

    assert calls == [(payload, {"user_id": 7})]
    assert result["ok"] is True
    assert result["meta"]["stage"] == "executed"
    assert result["meta"]["confirmed"] is True


def test_shopping_confirmed_create_dispatches_only_selected_items(monkeypatch):
    """확인된 장보기 추가는 구분자 payload의 실제 상품명만 핸들러로 전달해야 합니다."""
    calls = []

    def create_list(db, user_id, names):
        """DB 저장 대신 장보기 생성 인자만 기록합니다."""
        calls.append((db, user_id, names))
        return "우유, 계란을 장보기 목록에 추가했어요.", []

    monkeypatch.setattr(shopping_graph, "handle_create_confirm", create_list)

    result = shopping_graph.execute_confirmed_shopping_action(
        "shopping_create",
        "우유|계란||",
        db="test-db",
        user_id=7,
    )

    assert calls == [("test-db", 7, ["우유", "계란"])]
    assert "우유" in result["response_text"]


def test_shopping_unknown_confirmation_does_not_call_write_handler(monkeypatch):
    """알 수 없는 확인 명령은 장보기 쓰기 핸들러를 호출하지 않아야 합니다."""
    called = False

    def unexpected_handler(*_args, **_kwargs):
        """호출되면 안 되는 쓰기 핸들러입니다."""
        nonlocal called
        called = True
        return "실행되면 안 돼요.", []

    monkeypatch.setattr(shopping_graph, "handle_create_confirm", unexpected_handler)

    result = shopping_graph.execute_confirmed_shopping_action(
        "unknown_action",
        "우유",
        db="test-db",
        user_id=7,
    )

    assert called is False
    assert "찾지 못했어요" in result["response_text"]
