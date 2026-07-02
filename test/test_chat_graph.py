import sys
from datetime import date, timedelta
from pathlib import Path

# 직접 실행해도 프로젝트 루트 기준 import가 가능하도록 경로를 맞춥니다.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.backend.services.chat_graph import LOGIN_REQUIRED_REPLY, _calendar_datetime_from_text, _extract_add_items, _extract_delete_name, _extract_quantity, _extract_storage, _parse_calendar_date, mcp_agent_node, route_intent, router_node


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









def test_inventory_add_sentence_asks_storage_without_llm() -> None:
    """\uc2dd\uc7ac\ub8cc \uad6c\ub9e4 \ubb38\uc7a5\uc740 LLM \ubcf4\uad00\ubc95\uc73c\ub85c \uc0c8\uc9c0 \uc54a\uace0 \ucd94\uac00 \ud655\uc778\uc73c\ub85c \uac11\ub2c8\ub2e4."""
    text = "\ub450\ubd80 \uc5b4\uc81c 1\uac1c \uc0c0\uc5b4"
    assert router_node({"text": text, "service": FakeService("ingredient.guide"), "history": []})["intent"] == "mcp.inventory"
    result = mcp_agent_node({"user_id": 1, "text": text, "intent": "mcp.inventory", "history": []})
    assert result["response_text"] == "\ub450\ubd80 1\uac1c\ub97c \uc5b4\ub514\uc5d0 \ubcf4\uad00\ud560\uae4c\uc694? \ub0c9\uc7a5, \ub0c9\ub3d9, \uc2e4\uc628 \uc911\uc5d0\uc11c \uc54c\ub824\uc8fc\uc138\uc694."

def test_pending_calendar_time_update_stays_calendar() -> None:
    """일정 확인 문맥에서 시간만 바꿔도 재료 추가로 빠지지 않습니다."""
    class Message:
        def __init__(self, role, text):
            self.role = role
            self.text = text

    history = [Message("bot", "'럭키데이' 일정을 2024-07-07 09:00에 등록할까요?")]
    state = {"text": '11시에 등록해줘', "service": FakeService("general"), "history": history}
    assert router_node(state)["intent"] == "mcp.pending_calendar"
    result = mcp_agent_node({"user_id": 1, "text": '11시에 등록해줘', "intent": "mcp.pending_calendar", "history": history})
    assert result["response_text"] == "'럭키데이' 일정을 2024-07-07 11:00에 등록할까요?"
    assert result["actions"][0]["data"]["message"] == '확인:add_calendar_event:럭키데이:2024-07-07T11:00:00+09:00'


def test_pending_add_asks_storage_after_quantity() -> None:
    """수량만 답하면 보관 위치를 추가로 물어봅니다."""
    class Message:
        def __init__(self, role, text):
            self.role = role
            self.text = text

    history = [Message("bot", "냉동 새우를 몇 개 추가할까요? 수량을 알려주세요.")]
    state = {"text": "1", "service": FakeService("general"), "history": history}
    assert router_node(state)["intent"] == "mcp.pending_add"
    result = mcp_agent_node({"user_id": 1, "text": "1", "intent": "mcp.pending_add", "history": history})
    assert result["response_text"] == "냉동 새우 1개를 어디에 보관할까요? 냉장, 냉동, 실온 중에서 알려주세요."


def test_pending_add_storage_answer_builds_confirm_action() -> None:
    """보관 위치만 답하면 직전 추가 요청의 수량과 합쳐 확인합니다."""
    class Message:
        def __init__(self, role, text):
            self.role = role
            self.text = text

    history = [Message("bot", "냉동 새우 1개를 어디에 보관할까요? 냉장, 냉동, 실온 중에서 알려주세요.")]
    state = {"text": "냉동실에", "service": FakeService("general"), "history": history}
    assert _extract_storage("내 냉장고 재료 뭐 있어?") is None
    assert _extract_storage("냉동실에") == "냉동"
    assert router_node(state)["intent"] == "mcp.pending_add_storage"
    result = mcp_agent_node({"user_id": 1, "text": "냉동실에", "intent": "mcp.pending_add_storage", "history": history})
    assert result["response_text"] == "냉동 새우 1개를 냉동에 추가할까요?"
    assert result["actions"][0]["data"]["message"] == "확인:add_ingredient:냉동 새우:1.0:냉동"


def test_inventory_list_ignores_pending_add_when_no_quantity_or_storage() -> None:
    """냉장고 조회 질문은 직전 추가 대기 상태를 이어받지 않습니다."""
    class Message:
        def __init__(self, role, text):
            self.role = role
            self.text = text

    history = [Message("bot", "냉동 새우를 몇 개 추가할까요? 수량을 알려주세요.")]
    state = {"text": "내 냉장고 재료 뭐 있어?", "service": FakeService("inventory.list"), "history": history}
    assert router_node(state)["intent"] == "inventory.list"
def test_pending_add_handles_short_quantity_question() -> None:
    """봇이 짧게 수량을 물어도 후속 수량 답변을 추가 확인으로 이어갑니다."""
    class Message:
        def __init__(self, role, text):
            self.role = role
            self.text = text

    history = [Message("bot", "감자를 몇 개 추가하시겠어요?")]
    state = {"text": "한개", "service": FakeService("general"), "history": history}
    assert router_node(state)["intent"] == "mcp.pending_add"
    result = mcp_agent_node({"user_id": 1, "text": "한개", "intent": "mcp.pending_add", "history": history})
    assert result["response_text"] == "감자 1개를 어디에 보관할까요? 냉장, 냉동, 실온 중에서 알려주세요."


def test_multi_add_items_build_confirm_action() -> None:
    """여러 식재료와 수량을 한 번에 말하면 일괄 추가 확인을 만듭니다."""
    text = "파스타1, 토마토소스2, 냉동새우1"
    items = _extract_add_items(text)
    assert [item["name"] for item in items] == ["파스타", "토마토소스", "냉동새우"]
    result = mcp_agent_node({"user_id": 1, "text": text, "intent": "mcp.pending_add_many", "history": []})
    assert result["actions"][0]["data"]["message"] == "확인:add_ingredients:파스타,1.0,냉장|토마토소스,2.0,냉장|냉동새우,1.0,냉장"

def test_extract_add_item_trims_also_particle() -> None:
    """추가 요청의 '도' 조사는 제거하고 실제 재료명은 보존합니다."""
    assert _extract_add_items("토마토 소스도 추가해줘")[0]["name"] == "토마토 소스"
    assert _extract_add_items("양파도 추가해줘")[0]["name"] == "양파"
    assert _extract_add_items("포도 추가해줘")[0]["name"] == "포도"
    assert _extract_add_items("아보카도 추가해줘")[0]["name"] == "아보카도"


def test_pending_add_many_quantity_only_asks_for_named_quantities() -> None:
    """여러 재료 추가 대기 중 수량만 오면 재료명까지 다시 요청합니다."""
    class Message:
        def __init__(self, role, text):
            self.role = role
            self.text = text

    history = [Message("bot", "각 식재료의 수량을 알려주시면 추가해드릴게요.")]
    state = {"text": "1,1,1", "service": FakeService("general"), "history": history}
    assert router_node(state)["intent"] == "mcp.pending_add_many_retry"
    result = mcp_agent_node({"user_id": 1, "text": "1,1,1", "intent": "mcp.pending_add_many_retry", "history": history})
    assert result["response_text"] == "식재료와 갯수를 함께 말해주세요. 예: 파스타면1, 토마토소스1, 냉동 새우1"
def test_pending_add_quantity_routes_to_mcp() -> None:
    """추가 대기 중 수량만 답해도 MCP로 이어집니다."""
    class Message:
        def __init__(self, role, text):
            self.role = role
            self.text = text

    history = [Message("bot", "팽이버섯을 몇 개 추가할까요? 수량을 알려주세요.")]
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
    assert result["response_text"] == "팽이버섯 2개를 어디에 보관할까요? 냉장, 냉동, 실온 중에서 알려주세요."


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


def test_stale_pending_add_history_is_ignored() -> None:
    """이미 끝난 추가 질문은 숫자 응답으로 다시 살아나면 안 됩니다."""
    class Message:
        def __init__(self, role, text):
            self.role = role
            self.text = text

    history = [
        Message("bot", '토마토 소스 1개를 어디에 보관할까요? 냉장, 냉동, 실온 중에서 알려주세요.'),
        Message("bot", '알겠어요. 작업을 취소했어요.'),
    ]
    assert router_node({"text": "1", "service": FakeService("general"), "history": history})["intent"] == "general"


def test_latest_pending_question_wins_over_old_add_history() -> None:
    """과거 추가 질문보다 최신 소비 질문을 우선합니다."""
    class Message:
        def __init__(self, role, text):
            self.role = role
            self.text = text

    history = [
        Message("bot", '토마토 소스 1개를 어디에 보관할까요? 냉장, 냉동, 실온 중에서 알려주세요.'),
        Message("bot", '양파를 몇 개 소비할까요?'),
    ]
    assert router_node({"text": "1", "service": FakeService("general"), "history": history})["intent"] == "mcp.pending_consume"


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



def test_calendar_month_day_uses_current_year() -> None:
    """월/일만 있는 일정은 LLM의 과거 연도를 버리고 현재 연도를 사용합니다."""
    result = _calendar_datetime_from_text('7월7일 럭키데이 일정 등록해줘', "2023-07-07T09:00:00")
    assert result.date() == date(date.today().year, 7, 7)
    assert result.hour == 9


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
    test_pending_calendar_time_update_stays_calendar()
    test_confirm_and_cancel_route_to_mcp()
    test_inventory_add_sentence_asks_storage_without_llm()
    test_pending_add_asks_storage_after_quantity()
    test_pending_add_storage_answer_builds_confirm_action()
    test_inventory_list_ignores_pending_add_when_no_quantity_or_storage()
    test_pending_add_handles_short_quantity_question()
    test_multi_add_items_build_confirm_action()
    test_extract_add_item_trims_also_particle()
    test_pending_add_many_quantity_only_asks_for_named_quantities()
    test_pending_add_quantity_routes_to_mcp()
    test_pending_add_quantity_builds_confirm_action()
    test_pending_add_korean_quantity_and_storage()
    test_stale_pending_add_history_is_ignored()
    test_latest_pending_question_wins_over_old_add_history()
    test_pending_consume_quantity_builds_confirm_action()
    test_mcp_requires_login()
    test_calendar_date_parser()
    test_calendar_month_day_uses_current_year()
    test_calendar_today_time_uses_current_date()
    test_route_intent_uses_lookup_table()
    print("chat graph tests ok")
