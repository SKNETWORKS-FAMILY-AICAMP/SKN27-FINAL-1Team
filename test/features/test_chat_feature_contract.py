from types import SimpleNamespace

import pytest

pytest.importorskip("langchain_openai")

from ai.agents.supervisor_agent import supervisor_agent
from ai.agents.supervisor_agent.supervisor_service import supervisor_service


def test_supervisor_service_maps_graph_state_to_chat_response(monkeypatch):
    def fake_invoke(state):
        assert state["text"] == "두부로 뭐 해먹지?"
        assert state["history"][0].role == "user"
        return {
            "intent": "recipe.recommend",
            "response_text": "두부김치를 추천해요.",
            "actions": [{"label": "레시피 보기", "url": "/recipes/10", "data": {"recipe_id": 10}}],
            "sources": [{"title": "출처", "url": "https://example.com"}],
        }

    monkeypatch.setattr(supervisor_agent.supervisor_agent, "invoke", fake_invoke)

    result = supervisor_service.handle_message(
        db=SimpleNamespace(),
        user_id=7,
        message="두부로 뭐 해먹지?",
        history=[SimpleNamespace(role="user", text="냉장고에 두부 있어")],
        user_settings=SimpleNamespace(shortAnswer=False),
    )

    assert result == {
        "intent": "recipe.recommend",
        "reply": "두부김치를 추천해요.",
        "actions": [{"label": "레시피 보기", "url": "/recipes/10", "data": {"recipe_id": 10}}],
        "sources": [{"title": "출처", "url": "https://example.com"}],
    }


def test_chat_route_table_covers_current_feature_nodes():
    expected_routes = {
        "inventory.list": "inventory_agent_node",
        "inventory.expiring": "inventory_agent_node",
        "ingredient.guide": "guide_agent_node",
        "recipe.recommend": "recipe_agent_node",
        "recipe.search": "recipe_agent_node",
        "receipt.guide": "receipt_guide_node",
        "inventory.action": "inventory_agent_node",
        "shopping.current": "shopping_agent_node",
        "shopping.create": "shopping_agent_node",
        "shopping.compare": "shopping_agent_node",
    }

    for intent, node_name in expected_routes.items():
        assert supervisor_agent.route_intent({"intent": intent}) == node_name


def test_chat_feature_ab_routes_inventory_and_calendar_requests():
    """대표 요청이 올바른 에이전트 intent로 라우팅되는지 확인합니다."""
    inventory_result = supervisor_agent.router_node({"text": "두부 1개 샀어", "history": []})
    calendar_result = supervisor_agent.router_node({"text": "내일 캘린더 일정 등록해줘", "history": []})

    assert inventory_result["intent"] == "inventory.action"
    assert inventory_result["intent_payload"]["intent"] == "inventory.action"
    assert calendar_result["intent"] == "alarm.calendar"
    assert calendar_result["intent_payload"]["intent"] == "alarm.calendar"


def test_chat_routes_shopping_requests_to_shopping_agent():
    """장보기 요청이 슈퍼바이저에서 Shopping Agent로 라우팅되는지 확인합니다."""
    current_result = supervisor_agent.router_node({"text": "장보기 목록 보여줘", "history": []})
    create_result = supervisor_agent.router_node({"text": "두부랑 양파 장보기 목록 만들어줘", "history": []})
    compare_result = supervisor_agent.router_node({"text": "두부랑 양파 가격 비교해줘", "history": []})
    price_result = supervisor_agent.router_node({"text": "두부 가격알려줘", "history": []})
    feature_result = supervisor_agent.router_node({"text": "장보기 기능 뭐있어?", "history": []})

    assert current_result["intent"] == "shopping.current"
    assert feature_result["intent"] == "shopping.current"
    assert create_result["intent"] == "shopping.create"
    assert compare_result["intent"] == "shopping.compare"
    assert price_result["intent"] == "shopping.compare"
    assert supervisor_agent.route_intent(current_result) == "shopping_agent_node"
    assert supervisor_agent.route_intent(create_result) == "shopping_agent_node"
    assert supervisor_agent.route_intent(compare_result) == "shopping_agent_node"


def test_chat_routes_shopping_confirm_action_to_shopping_agent():
    """장보기 확인 버튼 메시지가 Inventory/Alarm이 아닌 Shopping Agent로 이동하는지 확인합니다."""
    state = {"intent": "action.confirm", "text": "확인:shopping_create:두부|양파"}

    assert supervisor_agent.route_intent(state) == "shopping_agent_node"


def test_supervisor_service_invokes_shopping_agent_from_chat():
    """ChatService로 들어온 장보기 생성 요청이 Shopping Agent 응답으로 변환되는지 확인합니다."""
    result = supervisor_service.handle_message(
        db=SimpleNamespace(),
        user_id=7,
        message="두부랑 양파 장보기 목록 만들어줘",
        history=[],
        user_settings=SimpleNamespace(shortAnswer=False),
    )

    assert result["intent"] == "shopping.create"
    assert "장보기 목록을 만들까요" in result["reply"]
    assert result["actions"][0]["data"]["message"] == "확인:shopping_create:두부|양파"
