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
        "recipe.recommend": "recipe_recommend_node",
        "recipe.search": "recipe_search_node",
        "receipt.guide": "receipt_guide_node",
        "inventory.action": "inventory_agent_node",
    }

    for intent, node_name in expected_routes.items():
        assert supervisor_agent.route_intent({"intent": intent}) == node_name


def test_chat_feature_ab_routes_inventory_and_calendar_requests():
    assert supervisor_agent.router_node({"text": "두부 1개 샀어", "history": []}) == {"intent": "inventory.action"}
    assert supervisor_agent.router_node({"text": "내일 캘린더 일정 등록해줘", "history": []}) == {
        "intent": "alarm.calendar"
    }
