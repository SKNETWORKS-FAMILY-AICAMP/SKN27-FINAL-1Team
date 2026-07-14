from unittest.mock import MagicMock
import sys
from pathlib import Path

# 직접 실행해도 프로젝트 루트 기준 import가 가능하도록 경로를 맞춥니다.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from ai.agents.supervisor_agent.supervisor_service import supervisor_service
from ai.agents.supervisor_agent import supervisor_utils
import ai.agents.recipe_agent.recipe_handlers as recipe_handlers


def test_route_intent_examples() -> None:
    """챗봇 대표 문장이 기대 intent로 분류되는지 확인합니다."""
    cases = {
        "오늘 먼저 먹어야 할 거 뭐야?": "inventory.expiring",
        "재료 기한 다되어 가는거 있어?": "inventory.expiring",
        "김치 유통기한 언제까지야": "inventory.expiring",
        "내 냉장고 재료 뭐 있어?": "inventory.list",
        "영수증 등록 어디서 해?": "receipt.guide",
        "파 어떻게 보관해?": "ingredient.guide",
        "파 보관법": "ingredient.guide",
        "아보카도 보관법": "ingredient.guide",
        "남은 피자 보관법": "ingredient.guide",
        "계란 보관 어떻게 해": "ingredient.guide",
        "먹다 남은 햄버거 어떡하지?": "ingredient.guide",
        "양파 영양성분 알려줘": "ingredient.guide",
        "감자 칼로리 알려줘": "ingredient.guide",
        "7월 제철 음식 뭐야": "ingredient.guide",
        "두부로 뭐 만들수있어?": "recipe.recommend",
        "두부로 뭘 만들지?": "recipe.recommend",
        "이걸로 만들수 있는 메뉴 뭐야": "recipe.recommend",
        "냉장고 재료로 뭐 만들어 먹지?": "recipe.recommend",
        "냉장고 재료로 뭐해먹지": "recipe.recommend",
        "냉장고 재료로 요리 추천해줘": "recipe.recommend",
        "냉장고속 재료로 요리추천": "recipe.recommend",
        "냉장고 재료로 만들 요리 알려줘": "recipe.recommend",
        "냉장고 재료로 뭐만들어먹지?": "recipe.recommend",
        "파 빨리 써야 하는데 뭐하지": "recipe.recommend",
        "감자로 간단하게 만들수 있는거 알려줘": "recipe.recommend",
        "먹다남은 감자튀김 어디에 쓸수있을까": "recipe.recommend",
        "바베큐 레시피 알려줘": "recipe.search",
        "김치볶음밥 레시피": "recipe.search",
        "김치볶음밥이랑 먹기 좋은 음식": "recipe.pairing",
        "감자튀김 에어프라이기 시간": "recipe.search",
        "남은 치킨 에어프라이기 시간 추천": "recipe.search",
    }

    for message, expected in cases.items():
        assert supervisor_service._route_intent(message) == expected


def test_extract_recipe_ingredient() -> None:
    """특정 재료 레시피 질문에서 재료명만 추출되는지 확인합니다."""
    assert supervisor_utils._extract_recipe_ingredient("두부로 뭐 만들수있어?") == "두부"
    assert supervisor_utils._extract_recipe_ingredient("두부로 뭘 만들지?") == "두부"
    assert supervisor_utils._extract_recipe_ingredient("이걸로 만들수 있는 메뉴 뭐야") == ""
    assert supervisor_utils._extract_recipe_ingredient("냉장고에 있는 걸로 저녁 추천") == ""
    assert supervisor_utils._extract_recipe_ingredient("파 빨리 써야 하는데 뭐하지") == "대파"
    assert supervisor_utils._extract_recipe_ingredient("먹다남은 감자튀김 어디에 쓸수있을까") == "감자튀김"

    assert supervisor_utils._extract_keyword("아보카도 보관법") == "아보카도"
    assert supervisor_utils._extract_keyword("남은 피자 보관법") == "피자"


def test_login_status_question() -> None:
    """로그인 상태를 묻는 문장을 별도로 인식합니다."""
    assert supervisor_utils._is_login_status_question("지금 로그인 되어 있어?")
    assert supervisor_utils._is_login_status_question("나 로그인 상태야?")
    assert not supervisor_utils._is_login_status_question("로그인하려면 어디로 가?")

def test_guest_chat_login_boundary() -> None:
    """비회원은 개인 냉장고 기능만 막고 일반 레시피/보관법은 허용합니다."""
    assert supervisor_utils._requires_login("inventory.list", "내 냉장고 재료 뭐 있어?")
    assert supervisor_utils._requires_login("inventory.expiring", "소비기한 임박 재료 알려줘")
    assert supervisor_utils._requires_login("recipe.recommend", "냉장고 재료로 뭐 먹을까?")
    assert supervisor_utils._requires_login("recipe.recommend", "내 식재료로 레시피 추천해줘")
    assert supervisor_utils._extract_recipe_ingredient("내 식재료로 레시피 추천해줘") == ""
    assert not supervisor_utils._requires_login("recipe.recommend", "두부로 뭐 만들 수 있어?")
    assert not supervisor_utils._requires_login("recipe.search", "깐풍기 레시피")
    assert not supervisor_utils._requires_login("ingredient.guide", "양파 보관법")

def test_guide_result_match() -> None:
    """가이드 검색이 비슷한 이름의 다른 재료를 답하지 않는지 확인합니다."""
    assert not supervisor_utils._is_guide_result_match("피자", "피자소스")
    assert not supervisor_utils._is_guide_result_match("치킨", "치킨스톡")
    assert not supervisor_utils._is_guide_result_match("김", "김치")
    assert supervisor_utils._is_guide_result_match("파", "대파")
    assert supervisor_utils._is_guide_result_match("마늘", "깐마늘")


def test_search_result_relevance() -> None:
    """웹 검색 fallback이 질문 핵심어와 무관한 결과를 거르는지 확인합니다."""
    good = {"title": "남은 치킨 보관법", "content": "치킨은 밀폐 후 냉장 보관", "url": "https://example.com"}
    bad = {"title": "마늘 양파 보관법", "content": "마늘과 양파는 상온 보관", "url": "https://example.com"}
    pizza_sauce = {"title": "피자소스 보관법", "content": "피자소스는 개봉 후 냉장 보관", "url": "https://example.com"}
    url_only = {"title": "마늘 보관법", "content": "마늘은 서늘하게 보관", "url": "https://example.com/chicken"}

    assert supervisor_utils._is_relevant_search_result("먹다남은 치킨", good)
    assert not supervisor_utils._is_relevant_search_result("먹다남은 치킨", bad)
    assert not supervisor_utils._is_relevant_search_result("피자", pizza_sauce)
    assert not supervisor_utils._is_relevant_search_result("보관법", good)
    assert not supervisor_utils._is_relevant_search_result("치킨", url_only)


def test_format_guide_tip() -> None:
    """긴 보관법 문장을 번호 목록으로 줄여 보여주는지 확인합니다."""
    formatted = supervisor_utils._format_guide_tip("첫 문장입니다. 둘째 문장입니다. 셋째 문장입니다. 넷째 문장입니다.")
    assert formatted == "1. 첫 문장입니다.\n2. 둘째 문장입니다.\n3. 셋째 문장입니다."
    assert supervisor_utils._format_guide_tip("제품 표시 기준에 따라 보관한다.") == "제품 표시 기준에 따라 보관한다."


def test_cooking_time_question_uses_external_recipe() -> None:
    """조리 시간 질문은 DB 레시피 목록 대신 웹 검색 안내로 보냅니다."""
    original_external = recipe_handlers.reply_external_recipe
    called = {"external": False, "query": ""}

    def fake_external(keyword: str, query_text: str | None = None):
        called["external"] = True
        called["query"] = query_text or ""
        return f"{keyword} 웹 검색", []

    recipe_handlers.reply_external_recipe = fake_external
    try:
        reply, actions, sources = recipe_handlers.handle_recipe_search(None, "감자튀김 에어프라이기 시간")
        assert called["external"]
        assert called["query"] == "감자튀김 에어프라이기 시간"
        assert reply == "감자튀김 웹 검색"
        assert actions == []
        assert sources == []
    finally:
        recipe_handlers.reply_external_recipe = original_external
if __name__ == "__main__":
    test_route_intent_examples()
    test_extract_recipe_ingredient()
    test_login_status_question()
    test_guest_chat_login_boundary()
    test_guide_result_match()
    test_search_result_relevance()
    test_format_guide_tip()
    test_cooking_time_question_uses_external_recipe()
    print("chat service tests ok")


# ===== 통합: 챗봇 서비스 / LangGraph / 빈 냉장고 응답 테스트 =====

import sys
from datetime import date, timedelta
from pathlib import Path

# 직접 실행해도 프로젝트 루트 기준 import가 가능하도록 경로를 맞춥니다.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from ai.agents.supervisor_agent.supervisor_agent import inventory_agent_node, route_intent, router_node
from ai.agents.supervisor_agent.supervisor_utils import LOGIN_REQUIRED_REPLY
from ai.agents.inventory_agent.inventory_utils import _extract_add_items, _extract_delete_name, _extract_quantity, _extract_storage, _extract_expiry_keyword, _pending_add_from_history


class FakeService:
    """LangGraph 라우팅 테스트에 필요한 최소 ChatService 대역입니다."""

    def __init__(self, intent: str):
        self.intent = intent

    def _route_intent_with_llm(self, text, history):
        return self.intent


def test_router_node_keeps_llm_payload_slots() -> None:
    """LLM fallback 라우팅 결과의 slots를 LangGraph state에 남깁니다."""

    class PayloadService:
        def _route_intent_payload_with_llm(self, text, history):
            return {
                "intent": "recipe.recommend",
                "confidence": 0.9,
                "slots": {"ingredient": "두부"},
            }

    result = router_node({"text": "애매한 추천 질문", "service": PayloadService(), "history": []})

    assert result == {
        "intent": "recipe.recommend",
        "intent_payload": {
            "intent": "recipe.recommend",
            "confidence": 0.9,
            "slots": {"ingredient": "두부"},
        },
        "slots": {"ingredient": "두부"},
    }


def test_inventory_expiry_does_not_route_to_action() -> None:
    """소비기한 질문은 소비 처리 action으로 빠지 않습니다."""
    state = {"text": "소비기한 임박 재료 알려줘", "service": FakeService("inventory.expiring"), "history": []}
    assert router_node(state)["intent"] == "inventory.expiring"


def test_inventory_action_routes_to_inventory_action() -> None:
    """실제 소비/등록 문장은 inventory action 노드로 보냅니다."""
    assert router_node({"text": "감자 2개 먹었어", "service": FakeService("general"), "history": []})["intent"] == "inventory.action"
    assert router_node({"text": "감자 등록해줘", "service": FakeService("general"), "history": []})["intent"] == "inventory.action"
    assert router_node({"text": "두부 어제 1개 샀어", "service": FakeService("ingredient.guide"), "history": []})["intent"] == "inventory.action"
    assert router_node({"text": "두부 어제 1개 삿어", "service": FakeService("ingredient.guide"), "history": []})["intent"] == "inventory.action"




def test_inventory_consume_plain_word_routes_to_inventory_action() -> None:
    """소비해줘 표현도 냉장고 소비 처리로 보냅니다."""
    assert router_node({"text": "두부 소비해줘", "service": FakeService("general"), "history": []})["intent"] == "inventory.action"
    assert router_node({"text": "냉장고에 두부 소비해줘", "service": FakeService("general"), "history": []})["intent"] == "inventory.action"


def test_expiring_question_does_not_use_consume_as_ingredient_name() -> None:
    """소비기한 임박 질문에서 소비를 식재료명으로 보지 않습니다."""
    assert router_node({"text": "소비기한 임박 재료 있어?", "service": FakeService("general"), "history": []})["intent"] == "inventory.expiring"
    assert _extract_expiry_keyword("소비기한 임박 재료 있어?") == ""
    assert _extract_expiry_keyword("소비 임박재료 뭐 있어?") == ""


def test_delete_inventory_item_routes_to_inventory_delete() -> None:
    """삭제/폐기 문장은 전체 폐기 확인 플로우로 보냅니다."""
    text = "냉장고에 두부 폐기처리 해줘"
    assert _extract_delete_name(text) == "두부"
    assert router_node({"text": text, "service": FakeService("general"), "history": []})["intent"] == "inventory.delete"
    result = inventory_agent_node({"db": MagicMock(), "user_id": 1, "text": text, "intent": "inventory.delete", "history": []})
    assert result["response_text"] == "두부 폐기 처리할까요?"
    assert result["actions"][0]["data"]["message"] == "확인:delete_ingredient:두부"
def test_receipt_register_words_route_to_receipt_guide() -> None:
    """영수증 등록 요청은 냉장고 재료 추가가 아니라 영수증 안내로 보냅니다."""
    messages = ("영수증 등록", "영수증 등록 어디서해", "OCR 등록")

    for message in messages:
        assert router_node({"text": message, "service": FakeService("general"), "history": []})["intent"] == "receipt.guide"

def test_alarm_agent_feature_words_route_to_alarm() -> None:
    """알림과 캘린더 요청을 슈퍼바이저에서 분리해 보냅니다."""
    notification_messages = (
        "내일 알람 삭제해줘",
        "리마인더 조회해줘",
        "푸시토큰 등록해줘",
        "알림 읽음 처리해줘",
    )
    calendar_messages = (
        "내일 저녁 일정 등록해줘",
        "캘린더 일정 조회",
        "내일 캘린더 일정 알려줘",
    )

    for message in notification_messages:
        assert router_node({"text": message, "service": FakeService("general"), "history": []})["intent"] == "alarm.notification"
    for message in calendar_messages:
        assert router_node({"text": message, "service": FakeService("general"), "history": []})["intent"] == "alarm.calendar"


def test_alarm_agent_node_passes_notification_intent(monkeypatch) -> None:
    """알림 조회는 캘린더 조회가 아니라 알림 intent로 알람 에이전트에 넘깁니다."""
    import ai.agents.supervisor_agent.supervisor_agent as supervisor_agent

    captured = {}

    def fake_run_alarm_agent(**kwargs):
        captured.update(kwargs)
        return {"message": "알림 목록을 조회했어요."}

    monkeypatch.setattr("ai.agents.alarm_agent.alarm_agent.run", fake_run_alarm_agent)

    supervisor_agent.alarm_agent_node({
        "db": MagicMock(),
        "user_id": 1,
        "text": "알림 조회",
        "intent": "alarm.notification",
    })

    assert captured["intent"] == "alarm.list"

def test_unread_notification_query_is_not_reported_as_full_list(monkeypatch) -> None:
    """읽지 않은 알림 조회는 전체 알림 조회 성공처럼 응답하지 않습니다."""
    import ai.agents.supervisor_agent.supervisor_agent as supervisor_agent

    def fail_run_alarm_agent(**kwargs):
        raise AssertionError("미확인 알림 조회는 아직 알람 에이전트럼 넘기지 않습니다.")

    monkeypatch.setattr("ai.agents.alarm_agent.alarm_agent.run", fail_run_alarm_agent)

    result = supervisor_agent.alarm_agent_node({
        "db": MagicMock(),
        "user_id": 1,
        "text": "읽지 않은 알림 있어?",
        "intent": "alarm.notification",
    })

    assert "아직 준비 중" in result["response_text"]


def test_alarm_agent_node_does_not_force_notification_create_to_list(monkeypatch) -> None:
    """알림 등록 문장은 알림 목록 조회로 고정하지 않고 알람 에이전트가 분류하게 둡니다."""
    import ai.agents.supervisor_agent.supervisor_agent as supervisor_agent

    captured = {}

    def fake_run_alarm_agent(**kwargs):
        captured.update(kwargs)
        return {"message": "어떤 알림인지 알려주세요."}

    monkeypatch.setattr("ai.agents.alarm_agent.alarm_agent.run", fake_run_alarm_agent)

    supervisor_agent.alarm_agent_node({
        "db": MagicMock(),
        "user_id": 1,
        "text": "내일 우유 사기 알림 등록해줘",
        "intent": "alarm.notification",
    })

    assert captured["intent"] is None

def test_calendar_delete_routes_to_alarm() -> None:
    """일정 삭제 요청은 냉장고 삭제가 아니라 알람 에이전트로 보냅니다."""
    state = {"text": "장보기 일정 삭제해줘", "service": FakeService("general"), "history": []}

    assert router_node(state)["intent"] == "alarm.calendar"


def test_supervisor_calendar_list_shows_events(monkeypatch) -> None:
    """캘린더 조회 결과가 있으면 일정 목록을 말풍선에 보여줍니다."""
    import ai.agents.supervisor_agent.supervisor_agent as supervisor_agent

    def fake_run_alarm_agent(**kwargs):
        return {
            "intent": "calendar.list",
            "message": "캘린더 일정을 조회했어요.",
            "data": {"events": [{"dateKey": "2026-07-08", "title": "장보기"}]},
        }

    monkeypatch.setattr("ai.agents.alarm_agent.alarm_agent.run", fake_run_alarm_agent)

    result = supervisor_agent.alarm_agent_node({
        "db": MagicMock(),
        "user_id": 1,
        "text": "내일 등록된 일정 있어?",
        "intent": "alarm.calendar",
    })

    assert result["response_text"] == "등록된 일정이에요.\n2026-07-08 - 장보기"


def test_supervisor_calendar_delete_delegates_to_alarm_agent(monkeypatch) -> None:
    """자연어 일정 삭제 후보 조회는 alarm agent 책임입니다."""
    import ai.agents.supervisor_agent.supervisor_agent as supervisor_agent

    captured = {}

    def fake_run_alarm_agent(**kwargs):
        captured.update(kwargs)
        return {"message": "밥벌이에서 등록한 일정을 찾을 수 없어요. 밥벌이에서 등록한 일정만 삭제할 수 있어요."}

    monkeypatch.setattr("ai.agents.alarm_agent.alarm_agent.run", fake_run_alarm_agent)

    result = supervisor_agent.alarm_agent_node({
        "db": MagicMock(),
        "user_id": 1,
        "text": "내일 장보기 일정 삭제해줘",
        "intent": "alarm.calendar",
    })

    assert captured["tools"]
    assert captured["context"]["user_id"] == 1
    assert result["response_text"] == "밥벌이에서 등록한 일정을 찾을 수 없어요. 밥벌이에서 등록한 일정만 삭제할 수 있어요."


def test_confirm_and_cancel_route_to_action() -> None:
    """확인/취소 버튼으로 돌아온 내부 메시지는 action 노드에서 처리합니다."""
    assert router_node({"text": "확인:add_ingredient:감자:1.0:냉장", "service": FakeService("general"), "history": []})["intent"] == "action.confirm"
    assert router_node({"text": "취소", "service": FakeService("general"), "history": []})["intent"] == "action.cancel"









def test_inventory_add_sentence_asks_storage_without_llm(monkeypatch) -> None:
    """식재료 구매 문장은 LLM 보관법으로 새지 않고 추가 확인으로 갑니다."""
    from app.backend.services.inventory_service.inventory_service import inventory_service
    monkeypatch.setattr(inventory_service, "_resolve_known_ingredient_name", lambda db, name: name)
    text = "두부 어제 1개 샀어"
    assert router_node({"text": text, "service": FakeService("ingredient.guide"), "history": []})["intent"] == "inventory.action"
    result = inventory_agent_node({"db": MagicMock(), "user_id": 1, "text": text, "intent": "inventory.action", "history": []})
    assert result["response_text"] == "두부 1개를 어디에 보관할까요? 냉장, 냉동, 실온 중에서 알려주세요."



def test_pending_add_cancel_word_routes_to_cancel() -> None:
    """추가 대기 상태에서 거절 표현은 새 추가 요청으로 보지 않습니다."""
    class Message:
        def __init__(self, role, text):
            self.role = role
            self.text = text

    history = [Message("bot", "감자를 몇 개 추가하시겠어요?")]
    state = {"text": "안넣어", "service": FakeService("general"), "history": history}

    assert router_node(state)["intent"] == "action.cancel"


def test_pending_add_asks_storage_after_quantity() -> None:
    """수량만 답하면 보관 위치를 추가로 물어봅니다."""
    class Message:
        def __init__(self, role, text):
            self.role = role
            self.text = text

    history = [Message("bot", "냉동 새우를 몇 개 추가할까요? 수량을 알려주세요.")]
    state = {"text": "1", "service": FakeService("general"), "history": history}
    assert router_node(state)["intent"] == "inventory.pending_add"
    result = inventory_agent_node({"db": MagicMock(), "user_id": 1, "text": "1", "intent": "inventory.pending_add", "history": history})
    assert result["response_text"] == "냉동 새우 1개를 어디에 보관할까요? 냉장, 냉동, 실온 중에서 알려주세요."


def test_pending_add_quantity_sentence_with_storage_keeps_previous_item() -> None:
    """수량 질문 뒤 보관 위치와 수량을 함께 말해도 추가 흐름을 이어갑니다."""
    class Message:
        def __init__(self, role, text):
            self.role = role
            self.text = text

    history = [Message("bot", "냉동실에 피자의 수량을 알려주시겠어요? (예: 냉동실에 피자 1개)")]
    state = {"text": "냉동실에 피자 1개", "service": FakeService("general"), "history": history}

    assert _pending_add_from_history(history) == "피자"
    assert router_node(state)["intent"] == "inventory.pending_add"
    result = inventory_agent_node({"db": MagicMock(), "user_id": 1, "text": "냉동실에 피자 1개", "intent": "inventory.pending_add", "history": history})
    assert result["response_text"] == "피자 1개를 냉동에 추가할까요?"
    assert result["actions"][0]["data"]["message"] == "확인:add_ingredient:피자:1.0:냉동"


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
    assert router_node(state)["intent"] == "inventory.pending_add_storage"
    result = inventory_agent_node({"db": MagicMock(), "user_id": 1, "text": "냉동실에", "intent": "inventory.pending_add_storage", "history": history})
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
    assert router_node(state)["intent"] == "inventory.pending_add"
    result = inventory_agent_node({"db": MagicMock(), "user_id": 1, "text": "한개", "intent": "inventory.pending_add", "history": history})
    assert result["response_text"] == "감자 1개를 어디에 보관할까요? 냉장, 냉동, 실온 중에서 알려주세요."


def test_multi_add_items_build_confirm_action() -> None:
    """여러 식재료와 수량을 한 번에 말하면 일괄 추가 확인을 만듭니다."""
    text = "파스타1, 토마토소스2, 냉동새우1"
    items = _extract_add_items(text)
    assert [item["name"] for item in items] == ["파스타", "토마토소스", "냉동새우"]
    result = inventory_agent_node({"db": MagicMock(), "user_id": 1, "text": text, "intent": "inventory.pending_add_many", "history": []})
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
    assert router_node(state)["intent"] == "inventory.pending_add_many_retry"
    result = inventory_agent_node({"db": MagicMock(), "user_id": 1, "text": "1,1,1", "intent": "inventory.pending_add_many_retry", "history": history})
    assert result["response_text"] == "식재료와 갯수를 함께 말해주세요. 예: 파스타면1, 토마토소스1, 냉동 새우1"
def test_pending_add_quantity_routes_to_inventory_pending() -> None:
    """추가 대기 중 수량만 답해도 inventory pending으로 이어집니다."""
    class Message:
        def __init__(self, role, text):
            self.role = role
            self.text = text

    history = [Message("bot", "팽이버섯을 몇 개 추가할까요? 수량을 알려주세요.")]
    state = {"text": "2개", "service": FakeService("general"), "history": history}
    assert router_node(state)["intent"] == "inventory.pending_add"



def test_pending_add_quantity_builds_confirm_action() -> None:
    """수량 답변을 받으면 추가 확인 버튼 메시지를 만듭니다."""
    class Message:
        def __init__(self, role, text):
            self.role = role
            self.text = text

    history = [Message("bot", "팽이버섯을 몇 개 추가할까요? 수량을 알려주세요.")]
    result = inventory_agent_node({"db": MagicMock(), "user_id": 1, "text": "2개", "intent": "inventory.pending_add", "history": history})
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
    assert router_node(state)["intent"] == "inventory.pending_add"
    result = inventory_agent_node({"db": MagicMock(), "user_id": 1, "text": "한개 냉장", "intent": "inventory.pending_add", "history": history})
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
    assert router_node({"text": "1", "service": FakeService("general"), "history": history})["intent"] == "inventory.pending_consume"


def test_pending_consume_quantity_builds_confirm_action() -> None:
    """소비 수량만 답한 경우 직전 소비 대기 요청을 이어받습니다."""
    class Message:
        def __init__(self, role, text):
            self.role = role
            self.text = text

    history = [Message("bot", "귤을 몇 개 먹으셨나요? 수량을 알려주시면, 냉장고에서 차감해드리겠습니다.")]
    state = {"text": "1개", "service": FakeService("inventory.list"), "history": history}
    assert router_node(state)["intent"] == "inventory.pending_consume"
    result = inventory_agent_node({"db": MagicMock(), "user_id": 1, "text": "1개", "intent": "inventory.pending_consume", "history": history})
    assert result["response_text"] == "귤 1개를 소비 처리할까요?"
    assert result["actions"][0]["data"]["message"] == "확인:consume_ingredient:귤:1.0"

def test_inventory_action_requires_login() -> None:
    """action 쓰기 작업은 비회원 상태에서 실행하지 않습니다."""
    assert inventory_agent_node({"db": MagicMock(), "user_id": 0, "text": "감자 먹었어", "intent": "inventory.action"})["response_text"] == LOGIN_REQUIRED_REPLY




def test_route_intent_uses_lookup_table() -> None:
    """일반 intent를 대응하는 LangGraph 노드 이름으로 변환합니다."""
    assert route_intent({"intent": "recipe.search"}) == "recipe_agent_node"
    assert route_intent({"intent": "recipe.pairing"}) == "recipe_pairing_node"
    assert route_intent({"intent": "inventory.action"}) == "inventory_agent_node"
    assert route_intent({"intent": "unknown"}) == "general_node"


if __name__ == "__main__":
    test_inventory_expiry_does_not_route_to_action()
    test_inventory_action_routes_to_inventory_action()
    test_delete_inventory_item_routes_to_inventory_delete()
    test_calendar_action_routes_to_mcp()
    test_pending_calendar_time_update_stays_calendar()
    test_confirm_and_cancel_route_to_action()
    test_inventory_add_sentence_asks_storage_without_llm()
    test_pending_add_asks_storage_after_quantity()
    test_pending_add_storage_answer_builds_confirm_action()
    test_inventory_list_ignores_pending_add_when_no_quantity_or_storage()
    test_pending_add_handles_short_quantity_question()
    test_multi_add_items_build_confirm_action()
    test_extract_add_item_trims_also_particle()
    test_pending_add_many_quantity_only_asks_for_named_quantities()
    test_pending_add_quantity_routes_to_inventory_pending()
    test_pending_add_quantity_builds_confirm_action()
    test_pending_add_korean_quantity_and_storage()
    test_stale_pending_add_history_is_ignored()
    test_latest_pending_question_wins_over_old_add_history()
    test_pending_consume_quantity_builds_confirm_action()
    test_inventory_action_requires_login()
    test_route_intent_uses_lookup_table()
    print("chat graph tests ok")


# ===== 통합: 챗봇 서비스 / LangGraph / 빈 냉장고 응답 테스트 =====

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from ai.agents.supervisor_agent import supervisor_service as chat_module



def test_inventory_add_rejects_greeting_name_before_quantity(monkeypatch) -> None:
    """인사말은 수량 질문으로 넘기지 않고 거절합니다."""
    import ai.agents.supervisor_agent.supervisor_agent as supervisor_agent
    from app.backend.services.inventory_service.inventory_service import inventory_service

    monkeypatch.setattr(inventory_service, "_resolve_known_ingredient_name", lambda db, name: None)

    result = supervisor_agent.inventory_agent_node({"db": MagicMock(), 
        "user_id": 1,
        "db": object(),
        "text": "안녕 냉장고에 넣어줘",
        "intent": "inventory.action",
        "history": [],
    })

    assert result["response_text"] == "올바른 식재료명을 입력해주세요."


def test_inventory_add_unknown_name_asks_quantity(monkeypatch) -> None:
    """마스터에 없는 식재료는 1개로 두고 보관 위치를 확인합니다."""
    import ai.agents.supervisor_agent.supervisor_agent as supervisor_agent
    from app.backend.services.inventory_service.inventory_service import inventory_service

    monkeypatch.setattr(inventory_service, "_resolve_known_ingredient_name", lambda db, name: None)

    result = supervisor_agent.inventory_agent_node({"db": MagicMock(), 
        "user_id": 1,
        "db": object(),
        "text": "게살 냉장고에 넣어줘",
        "intent": "inventory.action",
        "history": [],
    })

    assert result["response_text"] == "'게살'의 수량을 알려주시겠어요? (예: 게살 1개)"



def test_extract_add_items_keeps_leading_ga() -> None:
    """식재료명 맨 앞의 가를 조사로 잘라내지 않습니다."""
    items = _extract_add_items("가지튀김 냉장고에 넣어줘")

    assert items[0]["name"] == "가지튀김"


def test_inventory_add_negative_name_rejected_before_storage(monkeypatch) -> None:
    """부정 표현이 섞인 재료명은 보관 위치를 묻지 않습니다."""
    import ai.agents.supervisor_agent.supervisor_agent as supervisor_agent
    from app.backend.services.inventory_service.inventory_service import inventory_service

    monkeypatch.setattr(inventory_service, "_resolve_known_ingredient_name", lambda db, name: None)
    import ai.agents.inventory_agent.inventory_agent as inv_agent
    monkeypatch.setattr(inv_agent, "is_valid_ingredient", lambda name: False)

    result = supervisor_agent.inventory_agent_node({"db": MagicMock(), 
        "user_id": 1,
        "db": object(),
        "text": "가지 안튀김 냉장고에 넣어줘",
        "intent": "inventory.action",
        "history": [],
    })

    assert result["response_text"] == "올바른 식재료명을 입력해주세요."
    assert "actions" not in result


def test_inventory_add_name_starting_with_an_is_not_blocked(monkeypatch) -> None:
    """안으로 시작하는 실제 재료명은 부정 표현으로 처리하지 않습니다."""
    import ai.agents.supervisor_agent.supervisor_agent as supervisor_agent
    from app.backend.services.inventory_service.inventory_service import inventory_service

    monkeypatch.setattr(inventory_service, "_resolve_known_ingredient_name", lambda db, name: None)

    result = supervisor_agent.inventory_agent_node({"db": MagicMock(), 
        "user_id": 1,
        "db": object(),
        "text": "안심 냉장고에 넣어줘",
        "intent": "inventory.action",
        "history": [],
    })

    assert result["response_text"] == "'안심'의 수량을 알려주시겠어요? (예: 안심 1개)"




def test_guide_reply_formats_nutrition(monkeypatch) -> None:
    """영양성분 응답을 확인합니다."""
    def fake_answer(query):
        return {
            "ok": True,
            "action": "lookup_nutrition",
            "data": {
                "ingredient": {"name": "두부"},
                "nutrition": {
                    "base_amount": "100g",
                    "energy_kcal": 80,
                    "protein_g": 8.1,
                    "carbohydrate_g": 1.9,
                    "fat_g": 4.8,
                    "sodium_mg": 7,
                },
            },
            "ui": {"sources": [{"title": "영양DB", "url": None}]},
        }

    monkeypatch.setattr("ai.agents.supervisor_agent.supervisor_service.answer_guide_query", fake_answer)

    reply, sources = supervisor_service._reply_guide("두부 영양성분")

    assert "두부 영양성분이에요." in reply
    assert "기준량: 100g" in reply
    assert "열량: 80kcal" in reply
    assert "단백질: 8.1g" in reply
    assert sources[0]["url"] == ""


def test_guide_reply_formats_seasonality(monkeypatch) -> None:
    """제철 목록 응답을 확인합니다."""
    def fake_answer(query):
        return {
            "ok": True,
            "action": "list_seasonal_ingredients",
            "data": {
                "month": 7,
                "items": [{"name": "수박"}, {"name": "애호박"}, {"name": "옥수수"}],
            },
            "ui": {"sources": []},
        }

    monkeypatch.setattr("ai.agents.supervisor_agent.supervisor_service.answer_guide_query", fake_answer)

    reply, sources = supervisor_service._reply_guide("7월 제철음식")

    assert reply == "7월 제철 식재료는 수박, 애호박, 옥수수이에요."
    assert sources == []



def test_guide_reply_formats_ingredient_seasonality(monkeypatch) -> None:
    """식재료별 제철 응답을 월 목록으로 보여줍니다."""
    def fake_answer(query):
        return {
            "ok": True,
            "action": "lookup_seasonality",
            "data": {
                "ingredient": {"name": "딸기"},
                "seasonality": {"months": [1, 2, 3]},
            },
            "ui": {"sources": []},
        }

    monkeypatch.setattr("ai.agents.supervisor_agent.supervisor_service.answer_guide_query", fake_answer)

    reply, sources = supervisor_service._reply_guide("딸기 제철 언제야")

    assert reply == "딸기 제철은 1월, 2월, 3월이에요."
    assert sources == []


def test_guide_reply_formats_intake_tip(monkeypatch) -> None:
    """섭취 팁 응답을 챗봇 말풍선으로 변환합니다."""
    def fake_answer(query):
        assert query == "크림치즈"
        return {
            "ok": True,
            "action": "lookup_intake",
            "data": {
                "ingredient": {"name": "크림치즈"},
                "guides": {"intake": {"status": "available", "content": "빵이나 크래커에 발라 먹으면 좋다."}},
            },
            "ui": {"sources": []},
        }

    monkeypatch.setattr("ai.agents.supervisor_agent.supervisor_service.answer_guide_query", fake_answer)

    reply, sources = supervisor_service._reply_guide("크림치즈 맛있게 먹는법")

    assert "크림치즈 섭취 팁이에요." in reply
    assert "빵이나 크래커" in reply
    assert sources == []

def test_llm_router_keeps_rule_based_recipe_recommend() -> None:
    """규칙으로 잡힌 레시피 추천은 LLM 분류로 넘기지 않습니다."""
    messages = [
        "냉장고 재료로 뭐 만들어 먹지?",
        "냉장고 재료로 만들 요리 알려줘",
        "냉장고 재료로 뭐만들어먹지?",
    ]

    for message in messages:
        assert supervisor_service._route_intent_with_llm(message) == "recipe.recommend"



def test_llm_route_payload_json_parser() -> None:
    """LLM intent 응답을 JSON 객체로 파싱합니다."""
    payload = supervisor_service._parse_llm_route_payload(
        '{"intent":"recipe.recommend","confidence":0.82,"slots":{"ingredient":"두부"}}'
    )

    assert payload == {
        "intent": "recipe.recommend",
        "confidence": 0.82,
        "slots": {"ingredient": "두부"},
    }


def test_recipe_pairing_reply() -> None:
    """곁들임 질문은 레시피 검색 실패 대신 메뉴 조합을 안내합니다."""
    reply = supervisor_service._reply_recipe_pairing("김치볶음밥이랑 먹기 좋은 음식")

    assert "김치볶음밥에는" in reply
    assert "계란국" in reply
