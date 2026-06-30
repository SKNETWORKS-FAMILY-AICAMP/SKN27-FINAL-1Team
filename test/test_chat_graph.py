import sys
from pathlib import Path

# 직접 실행해도 프로젝트 루트 기준 import가 가능하도록 경로를 맞춥니다.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.backend.services.chat_graph import LOGIN_REQUIRED_REPLY, mcp_agent_node, route_intent, router_node


class FakeService:
    """LangGraph 라우터 테스트에 필요한 최소 ChatService 대역입니다."""

    def __init__(self, intent: str):
        self.intent = intent

    def _route_intent_with_llm(self, text, history):
        return self.intent


def test_inventory_expiry_does_not_route_to_mcp() -> None:
    """소비기한 질문은 소비 처리 MCP로 빠지지 않습니다."""
    state = {"text": "소비기한 임박 재료 알려줘", "service": FakeService("inventory.expiring"), "history": []}
    assert router_node(state)["intent"] == "inventory.expiring"


def test_inventory_action_routes_to_mcp() -> None:
    """실제 소비 행동 문장은 inventory MCP 노드로 보냅니다."""
    state = {"text": "감자 2개 먹었어", "service": FakeService("general"), "history": []}
    assert router_node(state)["intent"] == "mcp.inventory"


def test_mcp_requires_login() -> None:
    """MCP성 쓰기 작업은 비회원 상태에서 실행하지 않습니다."""
    assert mcp_agent_node({"user_id": 0, "text": "감자 먹었어"})["response_text"] == LOGIN_REQUIRED_REPLY


def test_route_intent_uses_lookup_table() -> None:
    """일반 intent는 대응하는 LangGraph 노드 이름으로 변환됩니다."""
    assert route_intent({"intent": "recipe.search"}) == "recipe_search_node"
    assert route_intent({"intent": "mcp.inventory"}) == "mcp_agent_node"
    assert route_intent({"intent": "unknown"}) == "general_node"


if __name__ == "__main__":
    test_inventory_expiry_does_not_route_to_mcp()
    test_inventory_action_routes_to_mcp()
    test_mcp_requires_login()
    test_route_intent_uses_lookup_table()
    print("chat graph tests ok")
