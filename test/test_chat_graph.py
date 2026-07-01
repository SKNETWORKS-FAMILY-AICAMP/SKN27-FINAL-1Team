import sys
from datetime import date, timedelta
from pathlib import Path

# 직접 실행해도 프로젝트 루트 기준 import가 가능하도록 경로를 맞춥니다.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.backend.services.chat_graph import LOGIN_REQUIRED_REPLY, _calendar_datetime_from_text, _extract_delete_name, _extract_quantity, _parse_calendar_date, mcp_agent_node, route_intent, router_node


class FakeService:
    """LangGraph 라우팅 테스트에 필요한 최소 ChatService 대역입니다."""

    def __init__(self, intent: str):
        self.intent = intent

    def _route_intent_with_llm(self, text, history):
        return self.intent


def test_inventory_expiry_does_not_route_to_mcp() -> None:
    """소비기한 질문은 소비 처리 MCP로 빠지지 않습니다."""
    state = {"text": "\uc18c\ube44\uae30\ud55c \uc784\ubc15 \uc7ac\ub8cc \uc54c\ub824\uc918", "service": FakeService("inventory.expiring"), "history": []}
    assert router_node(state)["intent"] == "inventory.expiring"


def test_inventory_action_routes_to_mcp() -> None:
    """실제 소비/등록 문장은 inventory MCP 노드로 보냅니다."""
    assert router_node({"text": "\uac10\uc790 2\uac1c \uba39\uc5c8\uc5b4", "service": FakeService("general"), "history": []})["intent"] == "mcp.inventory"
    assert router_node({"text": "\uac10\uc790 \ub4f1\ub85d\ud574\uc918", "service": FakeService("general"), "history": []})["intent"] == "mcp.inventory"
    assert router_node({"text": "\ub450\ubd80 \uc5b4\uc81c 1\uac1c \uc0c0\uc5b4", "service": FakeService("ingredient.guide"), "history": []})["intent"] == "mcp.inventory"
    assert router_node({"text": "\ub450\ubd80 \uc5b4\uc81c 1\uac1c \uc0bf\uc5b4", "service": FakeService("ingredient.guide"), "history": []})["intent"] == "mcp.inventory"




def test_delete_inventory_item_routes_to_mcp() -> None:
    """삭제/폐기 문장은 전체 폐기 확인 플로우로 보냅니다."""
    text = "냉장고에 두부 폐기처리 해줘"
    assert _extract_delete_name(text) == "두부"
    assert router_node({"text": text, "service": FakeService("general"), "history": []})["intent"] == "mcp.delete"
    result = mcp_agent_node({"user_id": 1, "text": text, "intent": "mcp.delete", "history": []})
    assert result["response_text"] == "두부 폐기 처리할까요?"
    assert result["actions"][0]["data"]["message"] == "확인:delete_ingredient:두부"
def test_calendar_action_routes_to_mcp() -> None:
    """일정/캘린더 문장은 calendar MCP 노드로 보냅니다."""
    state = {"text": "\ub0b4\uc77c \uc800\ub141 \uc77c\uc815 \ub4f1\ub85d\ud574\uc918", "service": FakeService("general"), "history": []}
    assert router_node(state)["intent"] == "mcp.calendar"


def test_confirm_and_cancel_route_to_mcp() -> None:
    """확인/취소 버튼으로 돌아온 내부 메시지는 MCP 노드에서 처리합니다."""
    assert router_node({"text": "\ud655\uc778:add_ingredient:\uac10\uc790:1.0:\ub0c9\uc7a5", "service": FakeService("general"), "history": []})["intent"] == "mcp.confirm"
    assert router_node({"text": "\ucde8\uc18c", "service": FakeService("general"), "history": []})["intent"] == "mcp.cancel"



def test_pending_add_quantity_routes_to_mcp() -> None:
    """?? ??? ?? ?? ?? ?? ?? ??? ??????."""
    class Message:
        def __init__(self, role, text):
            self.role = role
            self.text = text

    history = [Message("bot", "\ud33d\uc774\ubc84\uc12f\uc744 \uba87 \uac1c \ucd94\uac00\ud560\uae4c\uc694? \uc218\ub7c9\uc744 \uc54c\ub824\uc8fc\uc138\uc694.")]
    state = {"text": "2\uac1c", "service": FakeService("general"), "history": history}
    assert router_node(state)["intent"] == "mcp.pending_add"



def test_pending_add_quantity_builds_confirm_action() -> None:
    """수량 답변을 받으면 추가 확인 버튼 메시지를 만듭니다."""
    class Message:
        def __init__(self, role, text):
            self.role = role
            self.text = text

    history = [Message("bot", "팽이버섯을 몇 개 추가할까요? 수량을 알려주세요.")]
    result = mcp_agent_node({"user_id": 1, "text": "2개", "intent": "mcp.pending_add", "history": history})
    assert result["response_text"] == "팽이버섯 2개를 냉장에 추가할까요?"
    assert result["actions"][0]["data"]["message"] == "확인:add_ingredient:팽이버섯:2.0:냉장"


def test_pending_add_korean_quantity_and_storage() -> None:
    """한글 수량과 보관 위치를 함께 답해도 추가 확인으로 이어집니다."""
    class Message:
        def __init__(self, role, text):
            self.role = role
            self.text = text

    history = [Message("bot", "두부를 몇 개나 추가할까요? 그리고 보관 방법은 냉장, 냉동, 실온 중 어떤 걸 원하시나요?")]
    state = {"text": "한개 냉장", "service": FakeService("ingredient.guide"), "history": history}
    assert _extract_quantity("한개 냉장") == 1.0
    assert router_node(state)["intent"] == "mcp.pending_add"
    result = mcp_agent_node({"user_id": 1, "text": "한개 냉장", "intent": "mcp.pending_add", "history": history})
    assert result["response_text"] == "두부 1개를 냉장에 추가할까요?"
    assert result["actions"][0]["data"]["message"] == "확인:add_ingredient:두부:1.0:냉장"


def test_pending_consume_quantity_builds_confirm_action() -> None:
    """소비 수량만 답한 경우 직전 소비 대기 요청을 이어받습니다."""
    class Message:
        def __init__(self, role, text):
            self.role = role
            self.text = text

    history = [Message("bot", "귤을 몇 개 먹으셨나요? 수량을 알려주시면, 냉장고에서 차감해드리겠습니다.")]
    state = {"text": "1개", "service": FakeService("inventory.list"), "history": history}
    assert router_node(state)["intent"] == "mcp.pending_consume"
    result = mcp_agent_node({"user_id": 1, "text": "1개", "intent": "mcp.pending_consume", "history": history})
    assert result["response_text"] == "귤 1개를 소비 처리할까요?"
    assert result["actions"][0]["data"]["message"] == "확인:consume_ingredient:귤:1.0"

def test_mcp_requires_login() -> None:
    """MCP 쓰기 작업은 비회원 상태에서 실행하지 않습니다."""
    assert mcp_agent_node({"user_id": 0, "text": "\uac10\uc790 \uba39\uc5c8\uc5b4", "intent": "mcp.inventory"})["response_text"] == LOGIN_REQUIRED_REPLY


def test_calendar_date_parser() -> None:
    """캘린더 날짜 표현을 실제 날짜로 변환합니다."""
    assert _parse_calendar_date("\uc624\ub298") == date.today()
    assert _parse_calendar_date("\ub0b4\uc77c") == date.today() + timedelta(days=1)
    assert _parse_calendar_date("2026-07-01") == date(2026, 7, 1)



def test_calendar_today_time_uses_current_date() -> None:
    """LLM이 과거 날짜를 줘도 사용자 원문의 오늘/시간을 우선합니다."""
    result = _calendar_datetime_from_text("오늘 11시에 미팅 일정 등록해줘", "2023-10-04T11:00:00")
    assert result.date() == date.today()
    assert result.hour == 11
    assert result.minute == 0

def test_route_intent_uses_lookup_table() -> None:
    """일반 intent를 대응하는 LangGraph 노드 이름으로 변환합니다."""
    assert route_intent({"intent": "recipe.search"}) == "recipe_search_node"
    assert route_intent({"intent": "mcp.inventory"}) == "mcp_agent_node"
    assert route_intent({"intent": "unknown"}) == "general_node"


if __name__ == "__main__":
    test_inventory_expiry_does_not_route_to_mcp()
    test_inventory_action_routes_to_mcp()
    test_delete_inventory_item_routes_to_mcp()
    test_calendar_action_routes_to_mcp()
    test_confirm_and_cancel_route_to_mcp()
    test_pending_add_quantity_routes_to_mcp()
    test_pending_add_quantity_builds_confirm_action()
    test_pending_add_korean_quantity_and_storage()
    test_pending_consume_quantity_builds_confirm_action()
    test_mcp_requires_login()
    test_calendar_date_parser()
    test_calendar_today_time_uses_current_date()
    test_route_intent_uses_lookup_table()
    print("chat graph tests ok")
