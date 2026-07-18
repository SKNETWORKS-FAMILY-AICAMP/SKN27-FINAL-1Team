from unittest.mock import MagicMock
import sys
from pathlib import Path

# 직접 실행해도 프로젝트 루트 기준 import가 가능하도록 경로를 맞춥니다.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from ai.agents.supervisor_agent.supervisor_service import supervisor_service
from ai.agents.supervisor_agent.supervisor_agent import router_node
from ai.agents.supervisor_agent import supervisor_utils
import ai.agents.recipe_agent.recipe_tools as recipe_tools
import ai.agents.recipe_agent.recipe_utils as recipe_utils
from ai.agents.recipe_agent import run_recipe_agent


def _route_intent(message: str) -> str:
    """실제 LangGraph 라우터를 통해 테스트 문장의 의도를 반환합니다."""
    return router_node({"text": message, "history": [], "service": supervisor_service})["intent"]


def test_route_intent_examples() -> None:
    """챗봇 대표 문장이 기대 intent로 분류되는지 확인합니다."""
    cases = {
        "오늘 먼저 먹어야 할 거 뭐야?": "inventory.expiring",
        "재료 기한 다되어 가는거 있어?": "inventory.expiring",
        "냉장고 재료 중 유통기한 임박 재료": "inventory.expiring",
        "냉장고 재료 중 유통기한 임박 재료랑 그 재료로 만들 수 있는 레시피 알려줘": "multi_agent",
        "김치 유통기한 언제까지야": "inventory.expiring",
        "내 냉장고 재료 뭐 있어?": "inventory.list",
        "영수증 등록 어디서 해?": "receipt.guide",
        "파 어떻게 보관해?": "ingredient.guide",
        "파 보관법": "ingredient.guide",
        "파 손질해줘": "ingredient.guide",
        "감자 세척해줘": "ingredient.guide",
        "아보카도 보관법": "ingredient.guide",
        "남은 피자 보관법": "ingredient.guide",
        "계란 보관 어떻게 해": "ingredient.guide",
        "양파 영양성분 알려줘": "ingredient.guide",
        "감자 칼로리 알려줘": "ingredient.guide",
        "7월 제철 음식 뭐야": "ingredient.guide",
        "간장 보관법": "ingredient.guide",
        "고추가 물러졌는데 괜찮아?": "ingredient.guide",
        "채소에 뭐가 있어?": "ingredient.guide",
        "내 냉장고에 채소 뭐 있어?": "inventory.list",
        "냉장고 재료로 뭐 만들어 먹지?": "recipe.recommend",
        "냉장고 재료로 뭐해먹지": "recipe.recommend",
        "냉장고 재료로 요리 추천해줘": "recipe.recommend",
        "냉장고속 재료로 요리추천": "recipe.recommend",
        "냉장고 재료로 만들 요리 알려줘": "recipe.recommend",
        "현재 냉장고 재료와 감자로 할 수 있는 레시피 알려줘": "recipe.recommend",
        "냉장고 재료와 양파로 가능한 메뉴 추천": "recipe.recommend",
        "보유 식재료로 만들 음식 알려줘": "recipe.recommend",
        "내 재료 기준 레시피 추천": "recipe.recommend",
        "냉장고 재료로 뭐만들어먹지?": "recipe.recommend",
        "바베큐 레시피 알려줘": "recipe.search",
        "김치볶음밥 레시피": "recipe.search",
        "김치볶음밥이랑 먹기 좋은 음식": "recipe.pairing",
        "감자튀김 에어프라이기 시간": "recipe.search",
        "남은 치킨 에어프라이기 시간 추천": "recipe.search",
    }

    for message, expected in cases.items():
        assert router_node({"text": message, "service": FakeService(expected), "history": []})["intent"] == expected


def test_intent_evaluation_dataset_contract() -> None:
    """실모델 평가 데이터셋의 형식과 Supervisor 허용 intent를 검증합니다."""
    import json

    dataset_path = Path(__file__).with_name("intent_evaluation_cases.json")
    cases = json.loads(dataset_path.read_text(encoding="utf-8-sig"))
    texts = [case.get("text") for case in cases]
    allowed_intents = set(supervisor_utils._LLM_ROUTE_INTENTS)

    assert len(cases) == 50
    assert len(texts) == len(set(texts))
    assert all(case.get("expected_intent") in allowed_intents for case in cases)
    assert all(case.get("expected_intent") not in {"inventory.action", "inventory.delete"} for case in cases)

    for case in cases:
        result = router_node({
            "text": case["text"],
            "history": case.get("history") or [],
            "service": FakeService(case["expected_intent"]),
        })
        assert result["intent"] == case["expected_intent"]

def test_intent_evaluator_reports_accuracy_and_failures(monkeypatch) -> None:
    """실모델 평가기가 정확도와 오분류 사례를 올바르게 집계하는지 확인합니다."""
    sys.path.insert(0, str(Path(__file__).parent))
    import benchmark_intent_router

    predictions = iter([
        {"intent": "ingredient.guide", "confidence": 0.9},
        {"intent": "general", "confidence": 0.6},
    ])
    monkeypatch.setattr(
        benchmark_intent_router.supervisor_service,
        "_route_intent_payload_with_llm",
        lambda text, history: next(predictions),
    )

    report = benchmark_intent_router.evaluate_cases([
        {"text": "감자 보관법", "expected_intent": "ingredient.guide"},
        {"text": "두부 레시피", "expected_intent": "recipe.search"},
    ], workers=1)

    assert report["accuracy"] == 0.5
    assert report["correct"] == 1
    assert report["failures"][0]["predicted"] == "general"

def test_extract_recipe_ingredient() -> None:
    """특정 재료 레시피 질문에서 재료명만 추출되는지 확인합니다."""
    assert recipe_utils._extract_recipe_ingredient("두부로 뭐 만들수있어?") == "두부"
    assert recipe_utils._extract_recipe_ingredient("두부로 뭘 만들지?") == "두부"
    assert recipe_utils._extract_recipe_ingredient("이걸로 만들수 있는 메뉴 뭐야") == ""
    assert recipe_utils._extract_recipe_ingredient("냉장고에 있는 걸로 저녁 추천") == ""
    assert recipe_utils._extract_recipe_ingredient("파 빨리 써야 하는데 뭐하지") == "대파"
    assert recipe_utils._extract_recipe_ingredient("먹다남은 감자튀김 어디에 쓸수있을까") == "감자튀김"



def test_login_status_question() -> None:
    """로그인 상태를 묻는 문장을 별도로 인식합니다."""
    assert supervisor_utils._is_login_status_question("지금 로그인 되어 있어?")
    assert supervisor_utils._is_login_status_question("나 로그인 상태야?")
    assert not supervisor_utils._is_login_status_question("로그인하려면 어디로 가?")

def test_guest_chat_login_boundary() -> None:
    """비회원은 개인 냉장고 기능만 막고 일반 레시피/보관법은 허용합니다."""
    assert recipe_utils._requires_login("inventory.list", "내 냉장고 재료 뭐 있어?")
    assert recipe_utils._requires_login("inventory.expiring", "소비기한 임박 재료 알려줘")
    assert recipe_utils._requires_login("recipe.recommend", "냉장고 재료로 뭐 먹을까?")
    assert recipe_utils._requires_login("recipe.recommend", "내 식재료로 레시피 추천해줘")
    assert recipe_utils._extract_recipe_ingredient("내 식재료로 레시피 추천해줘") == ""
    assert not recipe_utils._requires_login("recipe.recommend", "두부로 뭐 만들 수 있어?")
    assert not recipe_utils._requires_login("recipe.search", "깐풍기 레시피")
    assert not recipe_utils._requires_login("ingredient.guide", "양파 보관법")

def test_format_guide_tip() -> None:
    """긴 보관법 문장을 번호 목록으로 줄여 보여주는지 확인합니다."""
    formatted = supervisor_utils._format_guide_tip("첫 문장입니다. 둘째 문장입니다. 셋째 문장입니다. 넷째 문장입니다.")
    assert formatted == "1. 첫 문장입니다.\n2. 둘째 문장입니다.\n3. 셋째 문장입니다."
    assert supervisor_utils._format_guide_tip("제품 표시 기준에 따라 보관한다.") == "제품 표시 기준에 따라 보관한다."


def test_cooking_time_question_uses_external_recipe() -> None:
    """조리 시간 질문은 DB 레시피 목록 대신 웹 검색 안내로 보냅니다."""
    original_external = recipe_tools.reply_external_recipe
    called = {"external": False, "query": ""}

    def fake_external(keyword: str, query_text: str | None = None):
        called["external"] = True
        called["query"] = query_text or ""
        return f"{keyword} 웹 검색", []

    recipe_tools.reply_external_recipe = fake_external
    try:
        result = run_recipe_agent("감자튀김 에어프라이기 시간", db=None, intent="recipe.search")
        assert called["external"]
        assert called["query"] == "감자튀김 에어프라이기 시간"
        assert result["response_text"] == "감자튀김 웹 검색"
        assert result["actions"] == []
        assert result["sources"] == []
    finally:
        recipe_tools.reply_external_recipe = original_external
if __name__ == "__main__":
    test_route_intent_examples()
    test_extract_recipe_ingredient()
    test_login_status_question()
    test_guest_chat_login_boundary()
    test_format_guide_tip()
    test_cooking_time_question_uses_external_recipe()
    print("chat service tests ok")


# ===== 통합: 챗봇 서비스 / LangGraph / 빈 냉장고 응답 테스트 =====

import sys
from datetime import date, timedelta
from pathlib import Path

# 직접 실행해도 프로젝트 루트 기준 import가 가능하도록 경로를 맞춥니다.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from ai.agents.supervisor_agent.supervisor_agent import inventory_agent_node, route_intent, router_node, shopping_agent_node
from ai.agents.supervisor_agent.supervisor_utils import LOGIN_REQUIRED_REPLY, _normalize_shopping_create_query, _normalize_shopping_delete_query, _strip_shopping_compare_suffix
from ai.agents.inventory_agent.inventory_utils import _extract_add_items, _extract_delete_name, _extract_quantity, _extract_storage, _extract_expiry_keyword, _pending_add_from_history
from ai.agents.shopping_agent.shopping_utils import extract_ingredient_names


class FakeService:
    """LangGraph 라우팅 테스트에 필요한 최소 ChatService 대역입니다."""

    def __init__(self, intent: str):
        self.intent = intent

    def _route_intent_payload_with_llm(self, text, history):
        """테스트에서 LLM fallback 결과를 공통 dict 형식으로 반환합니다."""
        return {
            "intent": self.intent,
            "confidence": 0.9,
            "slots": {},
        }


def test_broad_single_words_use_llm_fallback() -> None:
    """넓은 단일 표현은 규칙으로 확정하지 않고 LLM fallback에 맡깁니다."""
    service = FakeService("general")

    for message in ("확인", "다른거", "요리"):
        assert router_node({"text": message, "service": service, "history": []})["intent"] == "general"


def test_ambiguous_read_requests_use_llm_fallback() -> None:
    """여러 의미로 해석할 수 있는 조회 표현은 LLM 분류 결과를 사용합니다."""
    recipe_service = FakeService("recipe.recommend")
    guide_service = FakeService("ingredient.guide")

    for message in (
        "두부로 뭘 만들지?",
        "두부로 뭐 만들수있어?",
        "이걸로 만들수 있는 메뉴 뭐야",
        "파 빨리 써야 하는데 뭐하지",
        "감자로 간단하게 만들수 있는거 알려줘",
        "감자로 한 끼 해결하고 싶어",
        "먹다남은 감자튀김 어디에 쓸수있을까",
    ):
        assert router_node({"text": message, "service": recipe_service, "history": []})["intent"] == "recipe.recommend"

    assert router_node({
        "text": "먹다 남은 햄버거 어떡하지?",
        "service": guide_service,
        "history": [],
    })["intent"] == "ingredient.guide"


def test_ambiguous_non_food_request_is_not_forced_to_recipe() -> None:
    """음식 문맥이 없는 애매한 표현은 레시피 요청으로 단정하지 않습니다."""
    service = FakeService("general")

    assert router_node({"text": "지금 뭐하지?", "service": service, "history": []})["intent"] == "general"


def test_llm_route_history_keeps_explicit_context() -> None:
    """LLM 문맥에 이전 intent, 슬롯, 실행 대기 작업을 함께 전달합니다."""
    history = [
        {"role": "user", "text": "두부 추가해줘"},
        {
            "role": "bot",
            "text": "두부를 몇 개 추가하시겠어요?",
            "intent": "inventory.action",
            "slots": {"ingredient": "두부"},
            "pending_action": {"action": "add_ingredient"},
        },
    ]

    assert supervisor_utils._build_llm_route_history(history)[-1] == {
        "role": "bot",
        "text": "두부를 몇 개 추가하시겠어요?",
        "intent": "inventory.action",
        "slots": {"ingredient": "두부"},
        "pending_action": {"action": "add_ingredient"},
    }


def test_read_request_uses_llm_before_rule_fallback() -> None:
    """읽기 요청은 기존 키워드 규칙보다 LLM JSON 분류를 먼저 사용합니다."""

    class TrackingService(FakeService):
        """LLM 분류 호출 여부를 기록하는 테스트 대역입니다."""

        def __init__(self) -> None:
            super().__init__("recipe.search")
            self.called = False

        def _route_intent_payload_with_llm(self, text, history):
            """호출 상태를 기록하고 규칙과 다른 읽기 intent를 반환합니다."""
            self.called = True
            return super()._route_intent_payload_with_llm(text, history)

    service = TrackingService()
    result = router_node({"text": "감자 보관법", "service": service, "history": []})

    assert service.called
    assert result["intent"] == "recipe.search"


def test_low_confidence_llm_result_uses_read_rule_fallback() -> None:
    """LLM 신뢰도가 낮으면 기존 읽기 규칙으로 안전하게 보완합니다."""

    class LowConfidenceService:
        """낮은 신뢰도의 일반 intent를 반환하는 테스트 대역입니다."""

        def _route_intent_payload_with_llm(self, text, history):
            """규칙 fallback을 확인하기 위한 낮은 신뢰도 결과를 반환합니다."""
            return {"intent": "general", "confidence": 0.2, "slots": {}}

    result = router_node({"text": "감자 보관법", "service": LowConfidenceService(), "history": []})

    assert result["intent"] == "ingredient.guide"


def test_write_request_does_not_call_llm_router() -> None:
    """냉장고 쓰기 요청은 LLM을 호출하지 않고 규칙으로 고정합니다."""

    class UnexpectedService:
        """호출되면 테스트를 실패시키는 LLM 대역입니다."""

        def _route_intent_payload_with_llm(self, text, history):
            """쓰기 요청에서 LLM 호출이 발생하면 실패합니다."""
            raise AssertionError("쓰기 요청에서 LLM 분류기를 호출했습니다.")

    result = router_node({"text": "감자 1개 추가해줘", "service": UnexpectedService(), "history": []})

    assert result["intent"] == "inventory.action"

def test_llm_fallback_excludes_write_intents() -> None:
    """DB 변경 intent는 LLM fallback 허용 목록에 포함하지 않습니다."""
    write_intents = {
        "shopping.create",
        "shopping.purchase",
        "shopping.delete_item",
        "shopping.check_item",
    }

    assert write_intents.isdisjoint(supervisor_utils._LLM_ROUTE_INTENTS)


def test_router_node_keeps_llm_payload_slots() -> None:
    """LLM fallback 라우팅 결과의 slots를 LangGraph state에 남깁니다."""

    class PayloadService:
        def _route_intent_payload_with_llm(self, text, history):
            return {
                "intent": "recipe.recommend",
                "confidence": 0.9,
                "slots": {"ingredient": "두부"},
            }

    result = router_node({"text": "이건 어떻게 하면 좋을까?", "service": PayloadService(), "history": []})

    assert result == {
        "intent": "recipe.recommend",
        "intent_payload": {
            "intent": "recipe.recommend",
            "confidence": 0.9,
            "slots": {"ingredient": "두부"},
            "tasks": [],
        },
        "slots": {"ingredient": "두부"},
        "tasks": [],
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
    assert router_node({"text": "양파 1개 먹엇어", "service": FakeService("general"), "history": []})["intent"] == "inventory.action"


def test_expiring_question_does_not_use_consume_as_ingredient_name() -> None:
    """소비기한 임박 질문에서 소비를 식재료명으로 보지 않습니다."""
    assert router_node({"text": "소비기한 임박 재료 있어?", "service": FakeService("inventory.expiring"), "history": []})["intent"] == "inventory.expiring"
    assert _extract_expiry_keyword("소비기한 임박 재료 있어?") == ""
    assert _extract_expiry_keyword("소비 임박재료 뭐 있어?") == ""
    assert _extract_expiry_keyword("냉장고 재료 중 유통기한 임박 재료") == ""



def test_multi_agent_node_runs_tasks_in_order(monkeypatch) -> None:
    """복합 질문의 작업 목록을 순서대로 실행하고 결과를 합칩니다."""
    import ai.agents.inventory_agent.inventory_agent as inventory_agent
    import ai.agents.supervisor_agent.supervisor_agent as supervisor_agent

    calls = []

    def fake_inventory(**kwargs):
        """테스트용 냉장고 응답을 반환합니다."""
        calls.append(kwargs["intent"])
        return {
            "response_text": "소비기한 확인이 필요한 재료예요. 두부 D-1",
            "slots": {"expiring_ingredients": ["두부"]},
        }

    def fake_recipe(*args, **kwargs):
        """테스트용 레시피 응답을 반환합니다."""
        calls.append((kwargs["intent"], args[0]))
        return {
            "response_text": "두부로 만들 수 있는 레시피예요.",
            "actions": [{"label": "두부조림", "url": "/recipes/1"}],
        }

    monkeypatch.setattr(inventory_agent, "run_inventory_agent", fake_inventory)
    monkeypatch.setattr(supervisor_agent, "run_recipe_agent", fake_recipe)

    text = "냉장고 재료 중 유통기한 임박 재료랑 그 재료로 만들 수 있는 레시피 알려줘"
    routed = supervisor_agent.router_node({"text": text, "history": [], "service": supervisor_service})
    result = supervisor_agent.multi_agent_node(
        {
            "text": text,
            "history": [],
            "db": MagicMock(),
            "user_id": 1,
            "tasks": routed["tasks"],
        }
    )

    assert routed["intent"] == "multi_agent"
    assert [task["intent"] for task in routed["tasks"]] == ["inventory.expiring", "recipe.recommend"]
    assert calls == ["inventory.expiring", ("recipe.recommend", "두부를 우선 활용하는 레시피를 추천해줘")]
    assert "두부 D-1" in result["response_text"]
    assert "두부로 만들 수 있는 레시피" in result["response_text"]
    assert result["actions"][0]["label"] == "두부조림"

def test_multi_agent_node_keeps_success_when_one_task_fails(monkeypatch) -> None:
    """복합 요청 중 한 Agent가 실패해도 성공한 응답은 사용자에게 반환합니다."""
    import ai.agents.supervisor_agent.supervisor_agent as supervisor_agent

    def fail_guide(state):
        """실패 격리 확인을 위해 예외를 발생시킵니다."""
        raise RuntimeError("guide failed")

    def succeed_recipe(state):
        """실패한 작업과 함께 실행되는 정상 응답을 반환합니다."""
        return {"response_text": "감자 레시피예요."}

    monkeypatch.setattr(supervisor_agent, "guide_agent_node", fail_guide)
    monkeypatch.setattr(supervisor_agent, "recipe_agent_node", succeed_recipe)

    result = supervisor_agent.multi_agent_node({
        "text": "감자 보관법과 레시피",
        "history": [],
        "db": MagicMock(),
        "user_id": 1,
        "tasks": [
            {"intent": "ingredient.guide", "text": "감자 보관법"},
            {"intent": "recipe.search", "text": "감자 레시피"},
        ],
    })

    assert "감자 레시피예요." in result["response_text"]
    assert "일부 요청은 처리하지 못했어요." in result["response_text"]
    assert result["slots"]["completed_intents"] == ["recipe.search"]
    assert result["slots"]["failed_intents"] == ["ingredient.guide"]


def test_merge_agent_results_removes_duplicate_ui_data() -> None:
    """복합 Agent 응답의 중복 버튼과 출처를 한 번만 반환합니다."""
    action = {"label": "감자 레시피", "url": "/recipes?ingredient=감자"}
    source = {"title": "농촌진흥청", "url": "https://example.com"}
    result = supervisor_utils._merge_agent_results(
        {"response_text": "첫 번째 응답", "actions": [action], "sources": [source]},
        {"response_text": "두 번째 응답", "actions": [action], "sources": [source]},
    )

    assert result["actions"] == [action]
    assert result["sources"] == [source]


def test_guide_and_price_request_builds_multi_agent_tasks() -> None:
    """보관법과 가격을 함께 물으면 두 조회 작업으로 분해합니다."""
    result = router_node({
        "text": "감자 보관법이랑 감자 가격 알려줘",
        "history": [],
        "service": supervisor_service,
    })

    assert result["intent"] == "multi_agent"
    assert [task["intent"] for task in result["tasks"]] == [
        "ingredient.guide",
        "shopping.compare",
    ]
    assert result["tasks"][1]["text"] == "감자 가격 알려줘"


def test_shopping_follow_up_shows_all_items(monkeypatch) -> None:
    """장보기 목록의 나머지 요청은 생략 없이 전체 항목을 반환합니다."""
    from app.backend.services.shopping_service import shopping_service

    shopping_list = {
        "id": 1,
        "items": [
            {"name": f"재료{index}", "quantity": 1, "unit": "개", "price": None, "is_purchased": False}
            for index in range(1, 8)
        ],
    }
    monkeypatch.setattr(shopping_service, "get_current", lambda **kwargs: shopping_list)

    for message in ("외2개도 보여줘", "다 알려줘"):
        result = shopping_agent_node({
            "text": message,
            "intent": "shopping.current",
            "db": MagicMock(),
            "user_id": 1,
            "history": [],
        })

        assert "7. 재료7 - 가격 정보 없음" in result["response_text"]
        assert "외 2개" not in result["response_text"]

def test_shopping_show_all_follow_up_keeps_current_list_intent() -> None:
    """장보기 목록 후속 요청은 LLM이 직전 목록 문맥을 반영해 분류합니다."""
    previous_message = MagicMock(role="bot", text="현재 장보기 목록이에요.", intent="shopping.current", slots={})
    service = FakeService("shopping.current")
    route_call = service._route_intent_payload_with_llm
    service._route_intent_payload_with_llm = MagicMock(wraps=route_call)

    result = router_node({
        "text": "다 알려줘",
        "history": [previous_message],
        "service": service,
    })

    service._route_intent_payload_with_llm.assert_called_once()
    assert result["intent"] == "shopping.current"
def test_shopping_create_removes_location_particle() -> None:
    """장보기 위치 조사를 제거해 상품명에 에/로가 남지 않게 합니다."""
    first = _normalize_shopping_create_query("냉동 피자 장보기에 넣어줘")
    second = _normalize_shopping_create_query("장보기에 냉동 치킨 넣어줘")

    assert extract_ingredient_names(first) == ["냉동 피자"]
    assert extract_ingredient_names(second) == ["냉동 치킨"]

def test_shopping_delete_follow_up_keeps_context(monkeypatch) -> None:
    """장보기 삭제 대상 질문 뒤 짧은 재료 답변도 삭제 intent를 유지합니다."""
    history = [MagicMock(
        role="bot",
        text="어떤 재료를 장보기 목록에서 뺄까요? 재료명을 같이 알려주세요.",
        intent="shopping.delete_item",
        slots={},
    )]

    result = router_node({"text": "피자 빼줘", "history": history, "service": FakeService("general")})

    assert result["intent"] == "shopping.delete_item"
    assert _normalize_shopping_delete_query("피자 빼줘") == "피자"
    captured = {}

    def fake_run_shopping_agent(**kwargs):
        """Shopping Agent에 전달된 삭제 대상명을 기록합니다."""
        captured.update(kwargs)
        return {"response_text": "피자를 장보기 목록에서 뺄까요?", "actions": []}

    monkeypatch.setattr("ai.agents.shopping_agent.shopping_agent.run_shopping_agent", fake_run_shopping_agent)
    shopping_agent_node({"text": "피자 빼줘", "intent": result["intent"], "db": MagicMock(), "user_id": 1, "history": history})

    assert captured["text"] == "피자"


def test_shopping_price_follow_up_reuses_previous_product(monkeypatch) -> None:
    """상품명이 생략된 가격 후속 질문은 직전 비교 상품을 이어받습니다."""
    import ai.agents.supervisor_agent.supervisor_agent as supervisor_agent

    captured = {}

    def fake_run_shopping_agent(**kwargs):
        """Shopping Agent에 전달된 상품명을 테스트용으로 기록합니다."""
        captured.update(kwargs)
        return {"response_text": "감자 가격 비교 결과예요.", "actions": [], "sources": []}

    monkeypatch.setattr(
        "ai.agents.shopping_agent.shopping_agent.run_shopping_agent",
        fake_run_shopping_agent,
    )
    history = [
        MagicMock(
            role="bot",
            text="감자 가격 비교 결과예요.",
            intent="shopping.compare",
            slots={"shopping_product": "감자"},
        )
    ]

    for message in ("더 싼 곳 없어?", "다른 곳 없어?"):
        routed = router_node({
            "text": message,
            "history": history,
            "service": FakeService("shopping.compare"),
        })
        result = supervisor_agent.shopping_agent_node({
            **routed,
            "text": message,
            "history": history,
            "db": MagicMock(),
            "user_id": 1,
        })

        assert routed["intent"] == "shopping.compare"
        assert captured["text"] == "감자"
        assert result["slots"]["shopping_product"] == "감자"

def test_price_explanation_uses_shopping_help() -> None:
    """가격 정보 없음의 이유를 묻는 후속 질문은 상품명으로 검색하지 않습니다."""
    routed = router_node({
        "text": "가격 정보 안나오는 이유?",
        "history": [],
        "service": FakeService("shopping.price_help"),
    })

    assert routed["intent"] == "shopping.price_help"
    result = shopping_agent_node({"text": "가격 정보 안나오는 이유?", **routed})
    assert "판매가를 확인하지 못했다" in result["response_text"]


def test_expensive_price_question_routes_to_shopping() -> None:
    """비싸다고 묻는 가격 질문은 식재료 가이드가 아니라 장보기 가격 비교로 보냅니다."""
    routed = router_node({
        "text": "바닐라오일 왜 이렇게 비싸?",
        "history": [],
        "service": FakeService("shopping.compare"),
    })

    assert routed["intent"] == "shopping.compare"


def test_expensive_price_question_strips_question_suffix() -> None:
    """비싸다고 묻는 표현은 상품명에서 제거한 뒤 가격 비교에 전달합니다."""
    assert _strip_shopping_compare_suffix("바닐라오일 왜 이렇게 비싸?") == "바닐라오일"


def test_inventory_add_parses_quantity_and_storage_particle() -> None:
    """수량과 보관 위치 조사가 포함되어도 재료명만 정확히 추출합니다."""
    assert _extract_add_items("양파 2개 냉장에 추가해줘") == [
        {"name": "양파", "quantity": 2.0, "storage": "냉장"}
    ]
    assert _extract_add_items("계란 한피스 추가해줘") == [
        {"name": "계란", "quantity": 1.0, "storage": None}
    ]




def test_inventory_add_question_uses_correct_particle(monkeypatch) -> None:
    """받침 있는 식재료의 추가 수량 질문에 올바른 조사를 사용합니다."""
    import ai.agents.inventory_agent.inventory_agent as inventory_agent

    monkeypatch.setattr(inventory_agent, "is_valid_ingredient", lambda name: True)
    monkeypatch.setattr(inventory_agent, "resolve_ingredient_name", lambda db, name: name)
    result = inventory_agent_node({
        "db": MagicMock(), "user_id": 1, "text": "계란 추가해줘",
        "intent": "inventory.action", "history": [],
    })

    assert result["response_text"] == "계란을 몇 개 추가하시겠어요?"
    piece_result = inventory_agent_node({
        "db": MagicMock(), "user_id": 1, "text": "계란 한피스 추가해줘",
        "intent": "inventory.action", "history": [],
    })

    assert piece_result["response_text"].startswith("계란 1개를 어디에 보관할까요?")


def test_delete_inventory_item_routes_to_inventory_delete(monkeypatch) -> None:
    """수량 없는 폐기 요청은 수량을 확인한 뒤 해당 수량만 처리합니다."""
    text = "냉장고에 두부 폐기처리 해줘"
    assert _extract_delete_name(text) == "두부"
    assert _extract_delete_name("호박 전체 삭제해줘") == "호박"
    assert _extract_delete_name("호박전체 삭제해줘") == "호박"
    assert _extract_delete_name("호박 전부 삭제해줘") == "호박"
    assert _extract_delete_name("호박 모두 삭제해줘") == "호박"
    assert router_node({"text": text, "service": FakeService("general"), "history": []})["intent"] == "inventory.delete"
    result = inventory_agent_node({"db": MagicMock(), "user_id": 1, "text": text, "intent": "inventory.delete", "history": []})
    assert result["response_text"] == "두부를 몇 개 폐기할까요?"
    assert result["slots"]["inventory_pending"] == {"action": "delete_quantity", "name": "두부"}
    history = [{
        "role": "bot",
        "text": result["response_text"],
        "intent": "inventory.delete",
        "slots": result["slots"],
    }]
    assert router_node({"text": "1개", "service": FakeService("general"), "history": history})["intent"] == "inventory.pending_delete"
    monkeypatch.setattr(
        "ai.agents.inventory_agent.inventory_agent.inventory_service.get_total_quantity_by_name",
        lambda db, user_id, name: 2,
    )
    confirmed = inventory_agent_node({
        "db": MagicMock(),
        "user_id": 1,
        "text": "1개",
        "intent": "inventory.pending_delete",
        "history": [],
        "slots": result["slots"],
    })
    assert confirmed["response_text"] == "두부 1개를 폐기 처리할까요?"
    assert confirmed["actions"][0]["data"]["message"] == "확인:delete_ingredient:두부:1.0"


def test_inventory_delete_caps_quantity_to_current_stock(monkeypatch) -> None:
    """폐기 요청 수량이 재고보다 많으면 현재 재고 전량만 확인합니다."""
    monkeypatch.setattr(
        "ai.agents.inventory_agent.inventory_agent.inventory_service.get_total_quantity_by_name",
        lambda db, user_id, name: 2,
    )

    result = inventory_agent_node({
        "db": MagicMock(), "user_id": 1, "text": "호박 5개 삭제해줘",
        "intent": "inventory.delete", "history": [],
    })

    assert result["response_text"] == "현재 호박은 2개 있어요. 2개를 모두 폐기 처리할까요?"
    assert result["actions"][0]["data"]["message"] == "확인:delete_ingredient:호박:2"


def test_inventory_delete_all_skips_quantity_question(monkeypatch) -> None:
    """전량 폐기를 명시하면 수량 질문 없이 현재 재고 전체를 확인합니다."""
    monkeypatch.setattr(
        "ai.agents.inventory_agent.inventory_agent.inventory_service.get_total_quantity_by_name",
        lambda db, user_id, name: 2,
    )

    result = inventory_agent_node({
        "db": MagicMock(), "user_id": 1, "text": "호박 전체 삭제해줘",
        "intent": "inventory.delete", "history": [],
    })

    assert result["response_text"] == "현재 호박은 2개 있어요. 2개를 모두 폐기 처리할까요?"
    assert result["actions"][0]["data"]["message"] == "확인:delete_ingredient:호박:2"




def test_inventory_delete_quantity_can_be_revised_from_confirmation(monkeypatch) -> None:
    """폐기 확인 단계와 취소 직후에 수량을 바꿔 다시 요청할 수 있습니다."""
    monkeypatch.setattr(
        "ai.agents.inventory_agent.inventory_agent.inventory_service.get_total_quantity_by_name",
        lambda db, user_id, name: 5,
    )
    initial = inventory_agent_node({
        "db": MagicMock(), "user_id": 1, "text": "호박 6개 삭제해줘",
        "intent": "inventory.delete", "history": [],
    })
    history = [{
        "role": "bot", "text": initial["response_text"],
        "intent": "inventory.delete", "slots": initial["slots"],
    }]

    routed = router_node({"text": "3개만 처리해줘", "service": FakeService("general"), "history": history})
    assert routed["intent"] == "inventory.pending_delete"
    revised = inventory_agent_node({
        "db": MagicMock(), "user_id": 1, "text": "3개만 처리해줘",
        "intent": routed["intent"], "history": history, "slots": routed["slots"],
    })
    assert revised["response_text"] == "호박 3개를 폐기 처리할까요?"

    corrected = router_node({"text": "아니다 다 삭제해줘", "service": FakeService("general"), "history": history})
    assert corrected["intent"] == "inventory.pending_delete"
    corrected_result = inventory_agent_node({
        "db": MagicMock(), "user_id": 1, "text": corrected["text"],
        "intent": corrected["intent"], "history": corrected["history"], "slots": corrected["slots"],
    })
    assert corrected_result["response_text"] == "현재 호박은 5개 있어요. 5개를 모두 폐기 처리할까요?"


    cancelled = inventory_agent_node({
        "db": MagicMock(), "user_id": 1, "text": "취소",
        "intent": "action.cancel", "history": history, "slots": initial["slots"],
    })
    cancel_history = [{
        "role": "bot", "text": cancelled["response_text"],
        "intent": "action.cancel", "slots": cancelled["slots"],
    }]
    resumed = router_node({"text": "3개만삭제", "service": FakeService("general"), "history": cancel_history})
    assert resumed["intent"] == "inventory.pending_delete"
    resumed_result = inventory_agent_node({
        "db": MagicMock(), "user_id": 1, "text": "3개만삭제",
        "intent": resumed["intent"], "history": cancel_history, "slots": resumed["slots"],
    })
    assert resumed_result["response_text"] == "호박 3개를 폐기 처리할까요?"

def test_inventory_consume_caps_quantity_to_current_stock(monkeypatch) -> None:
    """소비 요청 수량이 재고보다 많으면 현재 재고 전량만 확인합니다."""
    monkeypatch.setattr(
        "ai.agents.inventory_agent.inventory_agent.inventory_service.get_total_quantity_by_name",
        lambda db, user_id, name: 2,
    )

    result = inventory_agent_node({
        "db": MagicMock(), "user_id": 1, "text": "호박 5개 먹었어",
        "intent": "inventory.action", "history": [],
    })

    assert result["response_text"] == "현재 호박은 2개 있어요. 2개를 모두 소비 처리할까요?"
    assert result["actions"][0]["data"]["message"] == "확인:consume_ingredient:호박:2"


def test_receipt_register_words_route_to_receipt_guide() -> None:
    """영수증 등록 안내도 LLM을 먼저 거치고 올바른 Agent로 보냅니다."""
    messages = ("영수증 등록", "영수증 등록 어디서해", "OCR 등록")
    service = FakeService("receipt.guide")
    route_call = service._route_intent_payload_with_llm
    service._route_intent_payload_with_llm = MagicMock(wraps=route_call)

    for message in messages:
        assert router_node({"text": message, "service": service, "history": []})["intent"] == "receipt.guide"

    assert service._route_intent_payload_with_llm.call_count == len(messages)
def test_alarm_agent_feature_words_route_to_alarm() -> None:
    """알림과 캘린더 쓰기는 규칙으로, 조회는 LLM 결과로 분리합니다."""
    write_cases = (
        ("내일 알람 삭제해줘", "alarm.notification"),
        ("푸시토큰 등록해줘", "alarm.notification"),
        ("알림 읽음 처리해줘", "alarm.notification"),
        ("내일 저녁 일정 등록해줘", "alarm.calendar"),
    )
    read_cases = (
        ("리마인더 조회해줘", "alarm.notification"),
        ("캘린더 일정 조회", "alarm.calendar"),
        ("내일 캘린더 일정 알려줘", "alarm.calendar"),
    )

    for message, expected in write_cases:
        assert router_node({"text": message, "service": FakeService("general"), "history": []})["intent"] == expected
    for message, expected in read_cases:
        assert router_node({"text": message, "service": FakeService(expected), "history": []})["intent"] == expected

def test_alarm_agent_node_passes_notification_intent(monkeypatch) -> None:
    """알림 조회는 슈퍼바이저가 고정하지 않고 알람 에이전트가 분류하게 둡니다."""
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

    assert captured["intent"] is None
    assert captured["text_or_intent"] == "알림 조회"


def test_unread_notification_query_uses_alarm_agent(monkeypatch) -> None:
    """읽지 않은 알림 조회는 Alarm Agent의 unread 처리에 맡깁니다."""
    import ai.agents.supervisor_agent.supervisor_agent as supervisor_agent

    captured = {}

    def fake_run_alarm_agent(**kwargs):
        captured.update(kwargs)
        return {"message": "읽지 않은 알림 목록이에요."}

    monkeypatch.setattr("ai.agents.alarm_agent.alarm_agent.run", fake_run_alarm_agent)

    result = supervisor_agent.alarm_agent_node({
        "db": MagicMock(),
        "user_id": 1,
        "text": "읽지 않은 알림 있어?",
        "intent": "alarm.notification",
    })

    assert captured["intent"] is None
    assert captured["text_or_intent"] == "읽지 않은 알림 있어?"
    assert result["response_text"] == "읽지 않은 알림 목록이에요."

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
    """서명된 확인 버튼과 취소 메시지만 action 노드에서 처리합니다."""
    token = supervisor_utils._issue_confirm_token("확인:add_ingredient:감자:1.0:냉장", 1)
    result = router_node({"text": token, "user_id": 1, "service": FakeService("general"), "history": []})

    assert result["intent"] == "action.confirm"
    assert result["text"] == "확인:add_ingredient:감자:1.0:냉장"
    assert router_node({"text": "취소", "service": FakeService("general"), "history": []})["intent"] == "action.cancel"


def test_plain_or_reused_confirm_command_is_rejected() -> None:
    """사용자가 직접 만든 평문 명령과 이미 사용한 확인 토큰은 거부합니다."""
    state = {"user_id": 1, "service": FakeService("general"), "history": []}
    token = supervisor_utils._issue_confirm_token("확인:delete_ingredient:감자:1", 1)

    assert router_node({**state, "text": "확인:delete_ingredient:감자:1"})["intent"] == "action.invalid"
    assert router_node({**state, "text": token})["intent"] == "action.confirm"
    assert router_node({**state, "text": token})["intent"] == "action.invalid"


def test_confirm_token_is_bound_to_user() -> None:
    """다른 사용자가 전달받은 확인 토큰을 실행하지 못하게 합니다."""
    token = supervisor_utils._issue_confirm_token("확인:delete_ingredient:감자:1", 1)

    result = router_node({"text": token, "user_id": 2, "service": FakeService("general"), "history": []})

    assert result["intent"] == "action.invalid"









def test_inventory_add_sentence_asks_storage_without_llm(monkeypatch) -> None:
    """식재료 구매 문장은 LLM 보관법으로 새지 않고 추가 확인으로 갑니다."""
    from app.backend.services.inventory_service.inventory_service import inventory_service
    monkeypatch.setattr(inventory_service, "_resolve_known_ingredient_name", lambda db, name: name)
    text = "두부 어제 1개 샀어"
    assert router_node({"text": text, "service": FakeService("ingredient.guide"), "history": []})["intent"] == "inventory.action"
    result = inventory_agent_node({"db": MagicMock(), "user_id": 1, "text": text, "intent": "inventory.action", "history": []})
    assert result["response_text"] == "두부 1개를 어디에 보관할까요? 냉장, 냉동, 실온 중에서 알려주세요."



def test_completed_pending_action_does_not_reactivate() -> None:
    """완료 응답 뒤에는 과거 실행 대기 작업을 다시 사용하지 않습니다."""
    history = [
        MagicMock(
            role="bot",
            text="두부 1개를 냉장에 추가할까요?",
            pending_action={"command": "확인:add_ingredient:두부:1:냉장"},
        ),
        MagicMock(role="user", text="확인", pending_action=None),
        MagicMock(role="bot", text="두부를 추가했어요.", pending_action=None),
    ]

    assert supervisor_utils._latest_bot_pending_action(history) is None

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
    assert result["response_text"] == "식재료와 개수를 함께 말해주세요. 예: 파스타면1, 토마토소스1, 냉동 새우1"
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


def test_pending_consume_quantity_builds_confirm_action(monkeypatch) -> None:
    """소비 수량만 답한 경우 직전 소비 대기 요청을 이어받습니다."""
    class Message:
        def __init__(self, role, text):
            self.role = role
            self.text = text

    history = [Message("bot", "귤을 몇 개 먹으셨나요? 수량을 알려주시면, 냉장고에서 차감해드리겠습니다.")]
    state = {"text": "1개", "service": FakeService("inventory.list"), "history": history}
    assert router_node(state)["intent"] == "inventory.pending_consume"
    monkeypatch.setattr(
        "ai.agents.inventory_agent.inventory_agent.inventory_service.get_total_quantity_by_name",
        lambda db, user_id, name: 1,
    )
    result = inventory_agent_node({"db": MagicMock(), "user_id": 1, "text": "1개", "intent": "inventory.pending_consume", "history": history})
    assert result["response_text"] == "귤 1개를 소비 처리할까요?"
    assert result["actions"][0]["data"]["message"] == "확인:consume_ingredient:귤:1.0"

def test_inventory_action_requires_login() -> None:
    """action 쓰기 작업은 비회원 상태에서 실행하지 않습니다."""
    assert inventory_agent_node({"db": MagicMock(), "user_id": 0, "text": "감자 먹었어", "intent": "inventory.action"})["response_text"] == LOGIN_REQUIRED_REPLY




def test_route_intent_uses_lookup_table() -> None:
    """일반 intent를 대응하는 LangGraph 노드 이름으로 변환합니다."""
    assert route_intent({"intent": "recipe.search"}) == "recipe_agent_node"
    assert route_intent({"intent": "recipe.pairing"}) == "recipe_agent_node"
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



def test_inventory_list_keeps_all_displayed_names(monkeypatch) -> None:
    """재료가 9개 이상이어도 여덟 번째 이름과 나머지 개수를 모두 표시합니다."""
    from ai.agents.inventory_agent.inventory_agent import get_inventory_list
    from app.backend.services.inventory_service.inventory_service import inventory_service

    items = [{"name": f"재료{index}"} for index in range(1, 11)]
    monkeypatch.setattr(inventory_service, "get_ingredients", lambda **kwargs: items)

    reply = get_inventory_list(MagicMock(), 1)

    assert "재료8 외 2개" in reply


def test_unknown_valid_ingredient_uses_unchecked_confirmation(monkeypatch) -> None:
    """마스터 미등록 식재료는 유효성 확인 후 미등록 추가 명령으로 연결합니다."""
    import ai.agents.inventory_agent.inventory_agent as inventory_agent
    from app.backend.services.inventory_service.inventory_service import inventory_service

    monkeypatch.setattr(inventory_agent, "is_valid_ingredient", lambda name: True)
    monkeypatch.setattr(inventory_service, "_resolve_known_ingredient_name", lambda db, name: None)

    result = inventory_agent.run_inventory_agent(
        intent="inventory.action",
        text="게살 2개 냉장에 추가해줘",
        history=[],
        db=MagicMock(),
        user_id=1,
    )

    assert result["actions"][0]["data"]["message"] == "확인:add_ingredient_unchecked:게살:2.0:냉장"


def test_unchecked_add_revalidates_before_write(monkeypatch) -> None:
    """조작된 미등록 추가 확인 명령은 실행 시점의 유효성 검사를 통과해야 합니다."""
    import ai.agents.inventory_agent.inventory_agent as inventory_agent
    from app.backend.services.inventory_service.inventory_service import inventory_service

    monkeypatch.setattr(inventory_agent, "is_valid_ingredient", lambda name: False)
    add_unchecked = MagicMock()
    monkeypatch.setattr(inventory_service, "add_ingredient_unchecked_by_name", add_unchecked)

    result = inventory_agent.execute_inventory_action(
        "add_ingredient_unchecked",
        ["확인", "add_ingredient_unchecked", "안녕", "1", "냉장"],
        MagicMock(),
        1,
    )

    assert result["response_text"] == "올바른 식재료명을 입력해주세요."
    add_unchecked.assert_not_called()

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
    assert result["actions"] == []


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
    """Guide Agent 영양성분 데이터를 챗봇 문장으로 변환합니다."""
    def fake_answer(query):
        assert query == "두부 영양성분"
        return {
            "ok": True,
            "status": "success",
            "action": "lookup_nutrition",
            "message": "두부 영양성분을 조회했어요.",
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
            "ui": {"actions": [], "sources": [{"title": "영양DB", "url": None}]},
        }

    monkeypatch.setattr("ai.agents.supervisor_agent.supervisor_service.answer_guide_query", fake_answer)

    result = supervisor_service._reply_guide("두부 영양성분")

    assert "두부 영양성분이에요." in result["response_text"]
    assert "기준량: 100g" in result["response_text"]
    assert "열량: 80kcal" in result["response_text"]
    assert result["sources"][0]["url"] == ""
    assert result["slots"] == {"guide_status": "success", "guide_action": "lookup_nutrition"}


def test_guide_reply_formats_seasonality(monkeypatch) -> None:
    """Guide Agent 제철 목록 데이터를 챗봇 문장으로 변환합니다."""
    def fake_answer(query):
        return {
            "ok": True,
            "status": "success",
            "action": "list_seasonal_ingredients",
            "message": "7월 제철 식재료를 조회했어요.",
            "data": {
                "month": 7,
                "items": [{"name": "수박"}, {"name": "애호박"}, {"name": "옥수수"}],
            },
            "ui": {"actions": [], "sources": []},
        }

    monkeypatch.setattr("ai.agents.supervisor_agent.supervisor_service.answer_guide_query", fake_answer)

    result = supervisor_service._reply_guide("7월 제철음식")

    assert result["response_text"] == "7월 제철 식재료는 수박, 애호박, 옥수수이에요."


def test_guide_reply_uses_agent_action_instead_of_storage_default(monkeypatch) -> None:
    """명시된 Guide Agent action을 유지하고 보관법으로 강제하지 않습니다."""
    def fake_answer(query):
        assert query == "크림치즈 맛있게 먹는법"
        return {
            "ok": True,
            "status": "success",
            "action": "lookup_intake",
            "message": "크림치즈 섭취 팁을 조회했어요.",
            "data": {
                "ingredient": {"name": "크림치즈"},
                "guides": {"intake": {"status": "available", "content": "빵이나 크래커에 발라 먹으면 좋다."}},
            },
            "ui": {"actions": [], "sources": []},
        }

    monkeypatch.setattr("ai.agents.supervisor_agent.supervisor_service.answer_guide_query", fake_answer)

    result = supervisor_service._reply_guide("크림치즈 맛있게 먹는법")

    assert "크림치즈 섭취 팁이에요." in result["response_text"]
    assert "빵이나 크래커" in result["response_text"]


def test_guide_reply_keeps_full_ingredient_overview(monkeypatch) -> None:
    """전체 가이드 질문은 Guide Agent의 lookup_ingredient 응답을 유지합니다."""
    def fake_answer(query):
        assert query == "감자 알려줘"
        return {
            "ok": True,
            "status": "success",
            "action": "lookup_ingredient",
            "message": "감자 식재료 가이드를 조회했어요.",
            "data": {"ingredient": {"name": "감자"}, "guides": {}},
            "ui": {"actions": [], "sources": []},
        }

    monkeypatch.setattr("ai.agents.supervisor_agent.supervisor_service.answer_guide_query", fake_answer)

    result = supervisor_service._reply_guide("감자 알려줘")

    assert result["response_text"] == "감자 식재료 가이드를 조회했어요."
    assert "보관법" not in result["response_text"]


def test_guide_reply_preserves_candidate_query(monkeypatch) -> None:
    """후보 선택 버튼에 Guide Agent가 만든 guide_type 포함 질문을 유지합니다."""
    def fake_answer(query):
        return {
            "ok": True,
            "status": "needs_input",
            "action": "confirm_ingredient",
            "message": "비슷한 식재료를 찾았어요.",
            "data": {},
            "ui": {
                "actions": [
                    {
                        "label": "닭가슴살 신선도 확인법",
                        "value": "닭가슴살 신선도 확인법 알려줘",
                        "guide_type": "freshness",
                    }
                ],
                "sources": [],
            },
        }

    monkeypatch.setattr("ai.agents.supervisor_agent.supervisor_service.answer_guide_query", fake_answer)

    result = supervisor_service._reply_guide("닭고기 상했는지 확인하는 법 알려줘")

    assert result["actions"][0]["data"]["message"] == "닭가슴살 신선도 확인법 알려줘"
    assert result["actions"][0]["data"]["guide_type"] == "freshness"
    assert result["slots"]["guide_status"] == "needs_input"


def test_guide_reply_treats_not_found_as_normal_response(monkeypatch) -> None:
    """Guide Agent의 not_found를 시스템 오류가 아닌 사용자 안내로 전달합니다."""
    def fake_answer(query):
        return {
            "ok": True,
            "status": "not_found",
            "action": "lookup_storage",
            "message": "우동사리 보관법을 찾지 못했어요.",
            "data": {},
            "ui": {"actions": [], "sources": []},
        }

    monkeypatch.setattr("ai.agents.supervisor_agent.supervisor_service.answer_guide_query", fake_answer)

    result = supervisor_service._reply_guide("우동사리 보관법 알려줘")

    assert result["response_text"] == "우동사리 보관법을 찾지 못했어요."
    assert result["slots"]["guide_status"] == "not_found"


def test_guide_reply_converts_agent_error(monkeypatch) -> None:
    """Guide Agent 시스템 오류는 공통 오류 문구로 변환합니다."""
    def fake_answer(query):
        return {
            "ok": False,
            "status": "error",
            "action": "lookup_storage",
            "message": "DB 오류",
            "error": {"code": "GUIDE_LOOKUP_ERROR"},
            "ui": {"actions": [], "sources": []},
        }

    monkeypatch.setattr("ai.agents.supervisor_agent.supervisor_service.answer_guide_query", fake_answer)

    result = supervisor_service._reply_guide("감자 보관법")

    assert result["response_text"] == "가이드 정보를 조회하는 중 문제가 생겼어요. 잠시 후 다시 시도해주세요."



def test_chat_service_passes_session_metadata_to_graph(monkeypatch) -> None:
    """채팅 세션 ID와 문맥 개수를 LangGraph 실행 메타데이터로 전달합니다."""
    import ai.agents.supervisor_agent.supervisor_agent as supervisor_module
    import ai.agents.supervisor_agent.supervisor_service as service_module

    captured = {}

    def fake_invoke(state, config):
        """LangGraph 호출 인자를 저장하고 최소 응답 상태를 반환합니다."""
        captured["config"] = config
        return {**state, "intent": "general", "response_text": "안내", "actions": [], "sources": []}

    monkeypatch.setattr(supervisor_module.supervisor_agent, "invoke", fake_invoke)
    monkeypatch.setattr(service_module, "propagate_attributes", None)
    monkeypatch.setattr(service_module, "LangfuseCallbackHandler", None)

    response = supervisor_service.handle_message(
        db=MagicMock(),
        user_id=1,
        message="안녕",
        history=[{"role": "user", "text": "이전 질문"}],
        session_id="chat-session-1",
    )

    assert response["reply"] == "안내"
    assert captured["config"]["metadata"] == {
        "chat_session_id": "chat-session-1",
        "history_count": 1,
        "has_pending_action": False,
    }


def test_chat_request_accepts_session_id() -> None:
    """채팅 요청 스키마가 프론트에서 전달한 세션 ID를 보존합니다."""
    from app.backend.schemas.chat import ChatRequest

    request = ChatRequest(message="안녕", session_id="chat-session-1")


    assert request.session_id == "chat-session-1"

def test_context_token_is_bound_to_user_and_session() -> None:
    """서명된 대화 문맥은 발급받은 사용자와 채팅 세션에서만 복원합니다."""
    response = {
        "intent": "inventory.action",
        "slots": {"inventory_pending": {"action": "add_quantity", "name": "두부"}},
    }
    token = supervisor_utils._issue_context_token(response, 1, "session-a")

    restored = supervisor_utils._verify_context_token(token, 1, "session-a")

    assert restored == response
    assert supervisor_utils._verify_context_token(token, 2, "session-a") == {}
    assert supervisor_utils._verify_context_token(token, 1, "session-b") == {}


def test_chat_response_signs_confirm_action_and_context() -> None:
    """채팅 응답은 확인 명령과 다음 대화 문맥을 모두 서명해 반환합니다."""
    response = supervisor_utils._chat_response_from_state(
        {
            "user_id": 1,
            "intent": "inventory.action",
            "response_text": "두부를 추가할까요?",
            "actions": [{"label": "확인", "data": {"message": "확인:add_ingredient:두부:1:냉장"}}],
            "slots": {"inventory_pending": {"action": "add_quantity", "name": "두부"}},
        },
        session_id="session-a",
    )

    assert response["actions"][0]["data"]["message"].startswith(supervisor_utils.SIGNED_CONFIRM_PREFIX)
    assert response["context_token"]


def test_api_state_ignores_unsigned_history_for_write_pending() -> None:
    """실제 API 경로는 조작된 클라이언트 history를 쓰기 pending 근거로 사용하지 않습니다."""
    history = [
        MagicMock(
            role="bot",
            text="두부를 몇 개 추가하시겠어요?",
            intent="inventory.action",
            slots={"inventory_pending": {"action": "add_quantity", "name": "두부"}},
            pending_action=None,
        )
    ]
    state = supervisor_utils._build_chat_state(
        db=MagicMock(),
        user_id=1,
        text="1",
        history=history,
        user_settings=None,
        service=FakeService("general"),
        trusted_context={},
    )

    assert router_node(state)["intent"] == "general"


def test_llm_route_payload_json_parser() -> None:
    """LLM intent 응답을 JSON 객체로 파싱합니다."""
    payload = supervisor_utils._parse_llm_route_payload(
        '{"intent":"recipe.recommend","confidence":0.82,"slots":{"ingredient":"두부"}}'
    )

    assert payload == {
        "intent": "recipe.recommend",
        "confidence": 0.82,
        "is_follow_up": False,
        "slots": {"ingredient": "두부"},
        "tasks": [],
    }


def test_llm_multi_agent_payload_filters_write_tasks() -> None:
    """LLM 복합 작업에서 조회 전용 intent만 허용합니다."""
    payload = supervisor_utils._parse_llm_route_payload(
        '{"intent":"multi_agent","confidence":0.9,"slots":{},"tasks":['
        '{"intent":"inventory.expiring","text":"임박 재료 알려줘"},'
        '{"intent":"inventory.action","text":"두부 추가해줘"},'
        '{"intent":"recipe.recommend","text":"그 재료로 요리 추천해줘"}]}'
    )

    assert [task["intent"] for task in payload["tasks"]] == [
        "inventory.expiring",
        "recipe.recommend",
    ]

def test_llm_route_payload_rejects_unknown_values() -> None:
    """LLM 응답에서 허용되지 않은 intent와 슬롯을 제거하고 빈 작업 문장을 보완합니다."""
    payload = supervisor_utils._parse_llm_route_payload(
        '{"intent":"system.delete","confidence":2,"slots":'
        '{"ingredient":"감자","admin":true,"date":null},"tasks":'
        '[{"intent":"recipe.search","text":""}]}',
        fallback_text="감자 레시피",
    )

    assert payload == {
        "intent": "general",
        "confidence": 0.0,
        "is_follow_up": False,
        "slots": {"ingredient": "감자"},
        "tasks": [{"intent": "recipe.search", "text": "감자 레시피"}],
    }


def test_follow_up_inherits_only_same_intent_context() -> None:
    """후속 질문은 같은 Agent intent의 허용 슬롯만 이어받습니다."""
    class FollowUpService:
        """후속 가이드 분류 결과를 반환하는 테스트 대역입니다."""

        def _route_intent_payload_with_llm(self, text, history):
            """식재료명이 생략된 후속 가이드 결과를 반환합니다."""
            return {
                "intent": "ingredient.guide",
                "confidence": 0.9,
                "is_follow_up": True,
                "slots": {"guide_type": "washing"},
                "tasks": [],
            }

    history = [
        MagicMock(
            role="bot",
            text="감자 보관법이에요.",
            intent="ingredient.guide",
            slots={"ingredient": "감자", "guide_type": "storage", "shopping_product": "양파"},
            pending_action=None,
        )
    ]

    result = router_node({"text": "세척은?", "service": FollowUpService(), "history": history})

    assert result["intent"] == "ingredient.guide"
    assert result["slots"] == {"ingredient": "감자", "guide_type": "washing"}


def test_agent_result_contract_normalizes_status_and_ui() -> None:
    """Agent의 message·ui·status 응답을 Supervisor 공통 계약으로 변환합니다."""
    result = supervisor_utils._normalize_agent_result(
        {
            "ok": True,
            "status": "needs_input",
            "action": "confirm_ingredient",
            "message": "어떤 재료인지 선택해주세요.",
            "ui": {
                "actions": [{"label": "감자", "data": {"message": "감자"}}],
                "sources": [{"title": "출처", "url": "https://example.com"}],
            },
        },
        inherited_slots={"ingredient": "감"},
    )

    assert result["response_text"] == "어떤 재료인지 선택해주세요."
    assert result["actions"][0]["label"] == "감자"
    assert result["sources"][0]["title"] == "출처"
    assert result["slots"] == {
        "ingredient": "감",
        "agent_status": "needs_input",
        "agent_action": "confirm_ingredient",
    }


def test_food_general_guard_corrects_misclassified_read_intents() -> None:
    """명확한 식품 비교와 재가열 질문은 잘못된 Guide·Recipe 분류를 보정합니다."""
    comparison = router_node({
        "text": "동물성 휘핑크림과 식물성은 뭐가 달라?",
        "service": FakeService("ingredient.guide"),
        "history": [],
    })
    reheating = router_node({
        "text": "남은 치킨 데우는 방법은?",
        "service": FakeService("recipe.search"),
        "history": [],
    })

    assert comparison["intent"] == "food.general"
    assert reheating["intent"] == "food.general"

def test_food_general_prompt_separates_comparison_and_reheating() -> None:
    """식재료 비교와 남은 음식 재가열 질문을 food.general로 분류하도록 계약합니다."""
    prompt = supervisor_utils._LLM_ROUTE_SYSTEM_PROMPT

    assert '동물성 휘핑크림과 식물성은 뭐가 달라?' in prompt
    assert '남은 치킨 데우는 방법은?' in prompt
    assert 'must be food.general' in prompt

def test_food_fallback_routes_without_receiving_db_actions(monkeypatch) -> None:
    """일반 요리 지식은 fallback으로 보내고 DB 변경 intent와 분리합니다."""
    import ai.agents.supervisor_agent.supervisor_agent as supervisor_agent

    monkeypatch.setattr(
        "ai.agents.fallback_agent.run_food_fallback",
        lambda text, history=None: {"response_text": "설탕 5g은 일반적으로 약 1작은술이에요."},
    )
    routed = router_node({
        "text": "설탕 5g은 몇 티스푼이야?",
        "service": FakeService("food.general"),
        "history": [],
    })
    result = supervisor_agent.fallback_agent_node({
        **routed,
        "text": "설탕 5g은 몇 티스푼이야?",
        "history": [],
        "slots": {},
    })

    assert routed["intent"] == "food.general"
    assert result["response_text"].startswith("설탕 5g")
    assert result["actions"] == []
    assert "inventory" not in routed["intent"]


def test_non_food_request_stays_out_of_fallback() -> None:
    """음식과 관계없는 질문은 fallback Agent로 보내지 않습니다."""
    routed = router_node({
        "text": "파이썬으로 구구단 코드 짜줘",
        "service": FakeService("general"),
        "history": [],
    })

    assert routed["intent"] == "general"
    assert route_intent(routed) == "general_node"

def test_agent_quality_retry_runs_only_after_bad_result() -> None:
    """빈 Agent 응답은 한 번 재호출하고 정상 응답에는 재시도 횟수를 기록합니다."""
    responses = iter([
        {"status": "error", "response_text": ""},
        {"response_text": "정상 응답입니다."},
    ])
    calls = []

    def call_agent():
        """테스트용 Agent 응답을 순서대로 반환합니다."""
        calls.append(1)
        return next(responses)

    result = supervisor_utils._run_agent_with_retry(call_agent)

    assert len(calls) == 2
    assert result["response_text"] == "정상 응답입니다."
    assert result["slots"]["agent_retry_count"] == 1


def test_agent_quality_retry_skips_valid_result() -> None:
    """정상 Agent 응답은 불필요하게 다시 호출하지 않습니다."""
    calls = []

    def call_agent():
        """호출 횟수 확인용 정상 응답을 반환합니다."""
        calls.append(1)
        return {"response_text": "정상 응답입니다."}

    result = supervisor_utils._run_agent_with_retry(call_agent)

    assert len(calls) == 1
    assert result == {"response_text": "정상 응답입니다."}


def test_agent_quality_retry_is_disabled_for_write_action() -> None:
    """중복 DB 변경을 막기 위해 쓰기 작업은 응답이 비어도 재호출하지 않습니다."""
    calls = []

    def call_agent():
        """호출 횟수 확인용 빈 쓰기 응답을 반환합니다."""
        calls.append(1)
        return {"response_text": ""}

    result = supervisor_utils._run_agent_with_retry(call_agent, enabled=False)

    assert len(calls) == 1
    assert result == {"response_text": ""}



def test_guide_agent_node_does_not_retry_not_found() -> None:
    """Guide Agent의 not_found는 정상 조회 결과이므로 다시 호출하지 않습니다."""
    import ai.agents.supervisor_agent.supervisor_agent as supervisor_agent_module

    calls = []

    class GuideService:
        """not_found 호출 횟수를 검증하는 Guide Service 대역입니다."""

        def _reply_guide(self, text):
            """데이터가 없는 정상 조회 결과를 반환합니다."""
            calls.append(text)
            return {"response_text": "정보를 찾지 못했어요.", "slots": {"guide_status": "not_found"}}

    result = supervisor_agent_module.guide_agent_node({
        "text": "감자 보관법",
        "service": GuideService(),
        "slots": {},
    })

    assert calls == ["감자 보관법"]
    assert result["response_text"] == "정보를 찾지 못했어요."
    assert "agent_retry_count" not in result["slots"]

def test_inventory_write_node_never_retries(monkeypatch) -> None:
    """Inventory 쓰기 노드는 빈 응답이어도 중복 실행하지 않습니다."""
    import ai.agents.inventory_agent.inventory_agent as inventory_agent
    import ai.agents.supervisor_agent.supervisor_agent as supervisor_agent_module

    calls = []

    def fake_inventory_agent(**kwargs):
        """쓰기 Agent 호출 횟수를 기록하고 빈 응답을 반환합니다."""
        calls.append(kwargs)
        return {"response_text": ""}

    monkeypatch.setattr(inventory_agent, "run_inventory_agent", fake_inventory_agent)
    supervisor_agent_module.inventory_agent_node({
        "intent": "inventory.action",
        "text": "두부 1개 추가해줘",
        "history": [],
        "db": MagicMock(),
        "user_id": 1,
        "slots": {},
    })

    assert len(calls) == 1


def test_unknown_confirm_action_routes_to_general() -> None:
    """소유 Agent가 없는 확인 명령은 Alarm Agent로 추측하지 않습니다."""
    assert route_intent({"intent": "action.confirm", "text": "확인:unknown_action"}) == "general_node"


def test_agent_retry_converts_second_exception_to_error() -> None:
    """Agent가 두 번 모두 예외를 내면 챗봇 공통 오류 응답으로 변환합니다."""
    calls = []

    def fail_agent():
        """재시도 횟수 검증을 위해 항상 예외를 발생시킵니다."""
        calls.append(1)
        raise RuntimeError("agent failed")

    result = supervisor_utils._run_agent_with_retry(fail_agent)

    assert len(calls) == 2
    assert result["status"] == "error"
    assert result["slots"]["agent_retry_count"] == 1


def test_multi_agent_marks_error_result_as_failed(monkeypatch) -> None:
    """예외 없이 오류 dict를 반환한 작업도 완료 목록에 넣지 않습니다."""
    import ai.agents.supervisor_agent.supervisor_agent as supervisor_agent_module

    monkeypatch.setattr(
        supervisor_agent_module,
        "guide_agent_node",
        lambda state: {"status": "error", "response_text": "가이드 오류"},
    )
    monkeypatch.setattr(
        supervisor_agent_module,
        "recipe_agent_node",
        lambda state: {"response_text": "감자 레시피예요."},
    )

    result = supervisor_agent_module.multi_agent_node({
        "text": "감자 보관법과 레시피",
        "history": [],
        "db": MagicMock(),
        "user_id": 1,
        "tasks": [
            {"intent": "ingredient.guide", "text": "감자 보관법"},
            {"intent": "recipe.search", "text": "감자 레시피"},
        ],
    })

    assert result["slots"]["completed_intents"] == ["recipe.search"]
    assert result["slots"]["failed_intents"] == ["ingredient.guide"]


def test_llm_route_payload_requires_intent_entities() -> None:
    """LLM 분류 결과가 intent별 필수 슬롯을 만족하는지 후검증합니다."""
    assert not supervisor_utils._is_llm_route_payload_valid(
        {"intent": "shopping.compare", "slots": {}, "tasks": [], "is_follow_up": False},
        "가격 알려줘",
    )
    assert supervisor_utils._is_llm_route_payload_valid(
        {"intent": "shopping.compare", "slots": {"shopping_product": "감자"}, "tasks": []},
        "감자 가격 알려줘",
    )
    assert not supervisor_utils._is_llm_route_payload_valid(
        {"intent": "multi_agent", "slots": {}, "tasks": [{"intent": "ingredient.guide"}]},
        "감자 보관법과 가격",
    )


def test_structured_inventory_pending_survives_message_wording_change() -> None:
    """화면 문구가 바뀌어도 구조화 슬롯으로 재료 추가 대화를 이어갑니다."""
    class Message:
        """구조화된 이전 챗봇 응답을 표현하는 테스트 대역입니다."""

        role = "bot"
        text = "수량을 입력해주세요."
        intent = "inventory.action"
        slots = {"inventory_pending": {"action": "add_quantity", "name": "두부", "unchecked": False}}
        pending_action = None

    history = [Message()]
    routed = router_node({"text": "2개", "service": FakeService("general"), "history": history})
    result = inventory_agent_node({
        "db": MagicMock(),
        "user_id": 1,
        "text": "2개",
        "intent": routed["intent"],
        "history": history,
        "slots": routed["slots"],
    })

    assert routed["intent"] == "inventory.pending_add"
    assert result["response_text"].startswith("두부 2개를 어디에 보관할까요?")
    assert result["slots"]["inventory_pending"]["name"] == "두부"


def test_inventory_cancel_clears_structured_pending() -> None:
    """사용자가 취소하면 남아 있던 재고 작업 슬롯을 제거합니다."""
    result = inventory_agent_node({
        "db": MagicMock(),
        "user_id": 1,
        "text": "취소",
        "intent": "action.cancel",
        "history": [],
        "slots": {"inventory_pending": {"action": "add_quantity", "name": "두부"}},
    })

    assert result["slots"]["inventory_pending"] is None

def test_agent_retry_marks_second_empty_result_as_error() -> None:
    """재시도 후에도 응답이 비어 있으면 명시적인 오류 상태로 반환합니다."""
    calls = []

    def empty_agent():
        """빈 응답 재시도 횟수를 확인하는 테스트 Agent입니다."""
        calls.append(1)
        return {"response_text": ""}

    result = supervisor_utils._run_agent_with_retry(empty_agent)

    assert len(calls) == 2
    assert result["status"] == "error"
    assert result["slots"]["agent_retry_count"] == 1
