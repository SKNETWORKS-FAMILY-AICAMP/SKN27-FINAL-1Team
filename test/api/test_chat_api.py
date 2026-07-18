from contextlib import contextmanager
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.backend.api.chat import chat_api
from app.backend.main import app
from ai.agents.supervisor_agent import supervisor_service as supervisor_service_module


client = TestClient(app)


def test_chat_api_returns_legacy_chat_contract(monkeypatch):
    def fake_handle_message(**kwargs):
        assert kwargs["user_id"] == 0
        assert kwargs["message"] == "냉장고에 뭐 있어?"
        return {
            "intent": "inventory.list",
            "reply": "냉장고 재료를 조회했어요.",
            "actions": [{"label": "냉장고 보기", "url": "/fridge", "data": {"tab": "list"}}],
            "sources": [],
        }

    monkeypatch.setattr(chat_api.supervisor_service, "handle_message", fake_handle_message)

    response = client.post(
        "/api/v1/chat",
        json={
            "message": "냉장고에 뭐 있어?",
            "history": [],
            "settings": {
                "shortAnswer": False,
                "fridgeFirst": True,
                "expiringFirst": True,
                "excludeDislikes": True,
            },
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "intent": "inventory.list",
        "reply": "냉장고 재료를 조회했어요.",
        "actions": [{"label": "냉장고 보기", "url": "/fridge", "data": {"tab": "list"}}],
        "sources": [],
        "slots": {},
        "pending_action": None,
    }



def test_chat_api_runs_supervisor_graph_and_inventory_agent(monkeypatch):
    """채팅 API가 Supervisor Graph를 거쳐 Inventory Agent 응답을 반환하는지 검증합니다."""
    import ai.agents.inventory_agent.inventory_agent as inventory_agent

    monkeypatch.setattr(
        chat_api.supervisor_service,
        "_route_intent_payload_with_llm",
        lambda text, history: {"intent": "inventory.list", "confidence": 0.95, "slots": {}, "tasks": []},
    )
    monkeypatch.setattr(
        inventory_agent,
        "run_inventory_agent",
        lambda **kwargs: {
            "response_text": "현재 냉장고에는 두부가 있어요.",
            "actions": [{"label": "냉장고 보기", "url": "/fridge"}],
        },
    )

    app.dependency_overrides[chat_api.get_current_user_optional] = lambda: 7
    try:
        response = client.post("/api/v1/chat", json={"message": "내 냉장고 재료 뭐 있어?"})
    finally:
        app.dependency_overrides.pop(chat_api.get_current_user_optional, None)

    assert response.status_code == 200
    assert response.json()["intent"] == "inventory.list"
    assert response.json()["reply"] == "현재 냉장고에는 두부가 있어요."


def test_chat_api_uses_rule_fallback_when_llm_routing_fails(monkeypatch):
    """LLM 분류 실패 시 읽기 규칙으로 보완해 Guide Agent까지 처리합니다."""
    monkeypatch.setattr(
        chat_api.supervisor_service,
        "_route_intent_payload_with_llm",
        lambda text, history: {"intent": "general", "confidence": 0.0, "slots": {}, "tasks": []},
    )
    monkeypatch.setattr(
        chat_api.supervisor_service,
        "_reply_guide",
        lambda text: {"response_text": "감자는 서늘하고 어두운 곳에 보관하세요."},
    )

    response = client.post("/api/v1/chat", json={"message": "감자 보관법 알려줘"})

    assert response.status_code == 200
    assert response.json()["intent"] == "ingredient.guide"
    assert "서늘하고 어두운 곳" in response.json()["reply"]


def test_chat_api_returns_error_contract_when_graph_fails(monkeypatch):
    """Supervisor Graph 예외가 API 오류 계약으로 변환되는지 검증합니다."""
    import ai.agents.supervisor_agent.supervisor_agent as supervisor_agent_module

    def raise_graph_error(*args, **kwargs):
        """그래프 실패 상황을 재현합니다."""
        raise RuntimeError("graph failed")

    monkeypatch.setattr(supervisor_agent_module.supervisor_agent, "invoke", raise_graph_error)

    response = client.post("/api/v1/chat", json={"message": "감자 보관법 알려줘"})

    assert response.status_code == 200
    assert response.json()["intent"] == "error"
    assert "잠시 후 다시 시도" in response.json()["reply"]


def test_langfuse_records_supervisor_result(monkeypatch):
    """Langfuse에 최종 intent와 성공 평가 점수가 기록되는지 검증합니다."""
    observation = MagicMock()
    langfuse_client = MagicMock()

    @contextmanager
    def fake_attributes(**kwargs):
        """테스트에서 Langfuse 속성 전파 문맥을 대체합니다."""
        yield

    @contextmanager
    def fake_observation(**kwargs):
        """테스트에서 Langfuse observation 문맥을 대체합니다."""
        yield observation

    langfuse_client.start_as_current_observation.side_effect = fake_observation
    monkeypatch.setattr(supervisor_service_module, "get_langfuse_client", lambda: langfuse_client)
    monkeypatch.setattr(supervisor_service_module, "propagate_attributes", fake_attributes)
    monkeypatch.setattr(supervisor_service_module, "LangfuseCallbackHandler", lambda: MagicMock())
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "test-public")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "test-secret")
    monkeypatch.setattr(
        chat_api.supervisor_service,
        "_route_intent_payload_with_llm",
        lambda text, history: {"intent": "general", "confidence": 0.9, "slots": {}, "tasks": []},
    )

    result = chat_api.supervisor_service.handle_message(
        db=MagicMock(),
        user_id=7,
        message="안녕",
        history=[],
        session_id="session-1",
    )

    assert result["intent"] == "general"
    observation.update.assert_called_once()
    assert observation.update.call_args.kwargs["output"] == {"intent": "general"}
    assert observation.update.call_args.kwargs["metadata"]["route_confidence"] == 0.9
    assert observation.update.call_args.kwargs["metadata"]["failed_intents"] == []
    langfuse_client.score_current_trace.assert_called_once_with(
        name="supervisor_success",
        value=1,
        data_type="BOOLEAN",
    )



def test_chat_api_confirms_and_executes_inventory_add(monkeypatch):
    """재료 추가 요청이 확인 단계를 거쳐 Inventory Service 실행까지 이어지는지 검증합니다."""
    import ai.agents.inventory_agent.inventory_agent as inventory_agent
    from app.backend.services.inventory_service.inventory_service import inventory_service

    added = {}

    def fake_add(db, user_id, name, quantity, storage):
        """실제 DB 저장 대신 전달된 재료 추가 인자를 기록합니다."""
        added.update(user_id=user_id, name=name, quantity=quantity, storage=storage)
        return "양파를 2개 냉장에 추가했어요."

    monkeypatch.setattr(inventory_agent, "is_valid_ingredient", lambda name: True)
    monkeypatch.setattr(inventory_agent, "resolve_ingredient_name", lambda db, name: name)
    monkeypatch.setattr(inventory_service, "add_ingredient_by_name", fake_add)
    app.dependency_overrides[chat_api.get_current_user_optional] = lambda: 7
    try:
        pending_response = client.post(
            "/api/v1/chat",
            json={"message": "양파 2개 냉장에 추가해줘"},
        )
        command = pending_response.json()["pending_action"]["command"]
        confirmed_response = client.post(
            "/api/v1/chat",
            json={"message": command},
        )
    finally:
        app.dependency_overrides.pop(chat_api.get_current_user_optional, None)

    assert pending_response.status_code == 200
    assert pending_response.json()["intent"] == "inventory.action"
    assert command == "확인:add_ingredient:양파:2.0:냉장"
    assert confirmed_response.status_code == 200
    assert confirmed_response.json()["intent"] == "action.confirm"
    assert confirmed_response.json()["reply"] == "양파를 2개 냉장에 추가했어요."
    assert added == {"user_id": 7, "name": "양파", "quantity": 2.0, "storage": "냉장"}



def test_langfuse_recording_failure_does_not_break_chat(monkeypatch):
    """Langfuse 기록 실패가 정상 챗봇 응답을 오류로 바꾸지 않는지 검증합니다."""
    observation = MagicMock()
    observation.update.side_effect = RuntimeError("trace failed")
    langfuse_client = MagicMock()

    @contextmanager
    def fake_attributes(**kwargs):
        """테스트에서 Langfuse 속성 전파 문맥을 대체합니다."""
        yield

    @contextmanager
    def fake_observation(**kwargs):
        """기록 실패를 발생시키는 observation 문맥을 반환합니다."""
        yield observation

    langfuse_client.start_as_current_observation.side_effect = fake_observation
    monkeypatch.setattr(supervisor_service_module, "get_langfuse_client", lambda: langfuse_client)
    monkeypatch.setattr(supervisor_service_module, "propagate_attributes", fake_attributes)
    monkeypatch.setattr(supervisor_service_module, "LangfuseCallbackHandler", lambda: MagicMock())
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "test-public")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "test-secret")
    monkeypatch.setattr(
        chat_api.supervisor_service,
        "_route_intent_payload_with_llm",
        lambda text, history: {"intent": "general", "confidence": 0.9, "slots": {}, "tasks": []},
    )

    result = chat_api.supervisor_service.handle_message(
        db=MagicMock(),
        user_id=7,
        message="안녕",
        history=[],
    )

    assert result["intent"] == "general"
