import json
from types import SimpleNamespace

import pytest

pytest.importorskip("langchain_openai")

import ai.agents.alarm_agent.alarm_agent as alarm_agent_module
from ai.agents.supervisor_agent import supervisor_agent
from ai.agents.supervisor_agent import chat_context, supervisor_utils
from ai.agents.supervisor_agent.supervisor_service import supervisor_service


def _invoke_multi_agent(state: dict) -> dict:
    """주어진 작업 목록을 실제 Supervisor 병렬 그래프로 실행합니다."""
    original_service = state.get("service")

    class FixedPlanner:
        """테스트 작업 계획을 반환하고 기존 서비스 기능은 그대로 위임합니다."""

        def _route_intent_payload_with_llm(self, _text, _history):
            return {
                "intent": "multi_agent",
                "confidence": 1.0,
                "slots": state.get("slots") or {},
                "tasks": state.get("tasks") or [],
            }

        def __getattr__(self, name):
            if original_service is None:
                raise AttributeError(name)
            return getattr(original_service, name)

    return supervisor_agent.supervisor_agent.invoke({
        **state,
        "history": state.get("history") or [],
        "service": FixedPlanner(),
    })

def test_supervisor_service_maps_graph_state_to_chat_response(monkeypatch):
    def fake_invoke(state, config=None):
        assert state["text"] == "두부로 뭐 해먹지?"
        assert state["history"][0].role == "user"
        return {
            "intent": "recipe.recommend",
            "response_text": "두부김치를 추천해요.",
            "slots": {"ingredient": "두부"},
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
        "slots": {"ingredient": "두부"},
        "pending_action": None,
    }



def test_menu_recommend_question_overrides_llm_general_misclassification():
    """메뉴 추천 질문은 LLM이 일반 요리로 분류해도 레시피 Agent로 보정합니다."""

    class FakeService:
        """LLM이 일반 요리 intent를 반환하는 상황을 재현합니다."""

        def _route_intent_payload_with_llm(self, _text, _history):
            return {"intent": "food.general", "confidence": 0.8, "slots": {}, "tasks": []}

    result = supervisor_agent.router_node(
        {"text": "오늘 뭐 해먹지?", "history": [], "service": FakeService()}
    )

    assert result["intent"] == "recipe.recommend"


def test_ingredient_recipe_question_routes_to_recipe_agent():
    """식재료 활용 메뉴 질문은 레시피 Agent로 라우팅합니다."""

    class FakeService:
        """LLM의 일반 요리 오분류를 재현합니다."""

        def _route_intent_payload_with_llm(self, _text, _history):
            return {"intent": "food.general", "confidence": 0.8, "slots": {}, "tasks": []}

    result = supervisor_agent.router_node(
        {"text": "김치로 만들수있는거", "history": [], "service": FakeService()}
    )

    assert result["intent"] == "recipe.recommend"

def test_expiring_question_overrides_llm_inventory_list_misclassification():
    """소비 임박 질문은 LLM이 목록으로 분류해도 임박 재료 조회로 보정합니다."""

    class FakeService:
        """LLM이 냉장고 목록 intent를 반환하는 상황을 재현합니다."""

        def _route_intent_payload_with_llm(self, _text, _history):
            return {"intent": "inventory.list", "confidence": 0.8, "slots": {}, "tasks": []}

    result = supervisor_agent.router_node(
        {"text": "소비 임박재료 뭐 있어?", "history": [], "service": FakeService()}
    )

    assert result["intent"] == "inventory.expiring"


def test_recipe_recommend_requires_login():
    """비로그인 사용자의 보유 재료 기반 메뉴 추천은 로그인 안내를 반환합니다."""
    result = supervisor_agent.recipe_agent_node(
        {"intent": "recipe.recommend", "text": "오늘 뭐 해먹지?", "user_id": None, "slots": {}}
    )

    assert result["response_text"] == supervisor_utils.LOGIN_REQUIRED_REPLY

def test_chat_route_table_covers_current_feature_nodes():
    expected_routes = {
        "inventory.list": "Inventory Agent (Single)",
        "inventory.expiring": "Inventory Agent (Single)",
        "ingredient.guide": "Guide Agent (Single)",
        "recipe.recommend": "Recipe Agent (Single)",
        "recipe.search": "Recipe Agent (Single)",
        "receipt.guide": "Receipt Guide Agent",
        "inventory.action": "Inventory Agent (Single)",
        "shopping.current": "Shopping Agent (Single)",
        "shopping.create": "Shopping Agent (Single)",
        "shopping.compare": "Shopping Agent (Single)",
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
    bought_result = supervisor_agent.router_node({"text": "장본거 뭐 있어?", "history": []})
    create_result = supervisor_agent.router_node({"text": "두부랑 양파 장보기 목록 만들어줘", "history": []})
    compare_result = supervisor_agent.router_node({"text": "두부랑 양파 가격 비교해줘", "history": []})
    price_result = supervisor_agent.router_node({"text": "두부 가격알려줘", "history": []})
    cheaper_result = supervisor_agent.router_node({"text": "설탕 더 싼곳 없어?", "history": []})
    product_candidate_result = supervisor_agent.router_node({"text": "계란 10구 상품 후보 보여줘", "history": []})
    human_food_candidate_result = supervisor_agent.router_node({
        "text": "강아지 닭가슴살 말고 사람이 먹는 닭가슴살 보여줘",
        "history": [],
    })
    stock_in_result = supervisor_agent.router_node({"text": "장보기 목록 새우 냉장고로 입고해줘", "history": []})
    feature_result = supervisor_agent.router_node({"text": "장보기 기능 뭐있어?", "history": []})

    assert current_result["intent"] == "shopping.current"
    assert bought_result["intent"] == "shopping.current"
    assert feature_result["intent"] == "shopping.current"
    assert create_result["intent"] == "shopping.create"
    assert compare_result["intent"] == "shopping.compare"
    assert price_result["intent"] == "shopping.compare"
    assert cheaper_result["intent"] == "shopping.compare"
    assert product_candidate_result["intent"] == "shopping.compare"
    assert human_food_candidate_result["intent"] == "shopping.compare"
    assert stock_in_result["intent"] == "shopping.purchase"
    assert supervisor_agent.route_intent(current_result) == "Shopping Agent (Single)"
    assert supervisor_agent.route_intent(create_result) == "Shopping Agent (Single)"
    assert supervisor_agent.route_intent(compare_result) == "Shopping Agent (Single)"


def test_chat_routes_shopping_confirm_action_to_shopping_agent():
    """장보기 확인 버튼 메시지가 Inventory/Alarm이 아닌 Shopping Agent로 이동하는지 확인합니다."""
    state = {"intent": "action.confirm", "text": "확인:shopping_create:두부|양파"}

    assert supervisor_agent.route_intent(state) == "Shopping Agent (Single)"


def test_chat_routes_pending_shopping_flow_follow_ups_to_shopping_agent():
    selection_slots = {
        "shopping_product": "두부",
        "shopping_flow": {
            "step": "awaiting_product_selection",
            "query": "두부",
            "candidates": [{"name": "두부", "product_id": "1", "product_name": "두부 상품"}],
        },
    }
    purchase_slots = {
        "shopping_flow": {
            "step": "awaiting_purchase_confirmation",
            "shopping_list_id": 11,
            "shopping_item_id": 21,
        },
    }

    selection = supervisor_agent.router_node({
        "text": "2번",
        "history": [],
        "trusted_context": {"intent": "shopping.compare", "slots": selection_slots},
        "context_enforced": True,
    })
    purchase = supervisor_agent.router_node({
        "text": "응, 샀어",
        "history": [],
        "trusted_context": {"intent": "shopping.compare", "slots": purchase_slots},
        "context_enforced": True,
    })
    cancel = supervisor_agent.router_node({
        "text": "취소",
        "history": [],
        "trusted_context": {"intent": "shopping.compare", "slots": selection_slots},
        "context_enforced": True,
    })

    assert selection["intent"] == "shopping.compare"
    assert purchase["intent"] == "shopping.purchase"
    assert cancel["intent"] == "shopping.cancel"
    assert supervisor_agent.route_intent(cancel) == "Shopping Agent (Single)"


def test_pending_shopping_selection_passes_original_reply_to_subgraph(monkeypatch):
    calls = []

    def fake_run(**kwargs):
        calls.append(kwargs)
        return {"response_text": "선택했어요.", "actions": [], "sources": [], "slots": kwargs["slots"]}

    monkeypatch.setattr("ai.agents.shopping_agent.shopping_agent.run_shopping_agent", fake_run)
    slots = {
        "shopping_product": "두부",
        "shopping_flow": {"step": "awaiting_product_selection", "query": "두부", "candidates": []},
    }

    supervisor_agent.shopping_agent_node({
        "text": "2번",
        "intent": "shopping.compare",
        "history": [],
        "slots": slots,
        "db": SimpleNamespace(),
        "user_id": 7,
    })

    assert calls[0]["text"] == "2번"


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
    assert result["actions"][0]["data"]["message"].startswith("확인토큰:")
    assert result["pending_action"]["command"].startswith("확인토큰:")



def test_shopping_price_follow_up_passes_only_product_name(monkeypatch):
    """가격 비교 후속 표현은 상품명에서 제거한 뒤 Shopping Agent에 전달합니다."""
    calls = []

    def fake_run(**kwargs):
        calls.append(kwargs)
        return {"response_text": "가격 비교 결과예요.", "actions": [], "sources": []}

    monkeypatch.setattr("ai.agents.shopping_agent.shopping_agent.run_shopping_agent", fake_run)

    supervisor_agent.shopping_agent_node({
        "text": "설탕 더 싼곳 없어?",
        "intent": "shopping.compare",
        "history": [],
        "db": SimpleNamespace(),
        "user_id": 7,
    })

    assert calls[0]["text"] == "설탕"


def test_shopping_price_follow_up_with_exists_passes_only_product_name(monkeypatch):
    calls = []

    def fake_run(**kwargs):
        calls.append(kwargs)
        return {"response_text": "가격 비교 결과예요.", "actions": [], "sources": []}

    monkeypatch.setattr("ai.agents.shopping_agent.shopping_agent.run_shopping_agent", fake_run)

    supervisor_agent.shopping_agent_node({
        "text": "새우 더 저렴한 곳 있어?",
        "intent": "shopping.compare",
        "history": [],
        "db": SimpleNamespace(),
        "user_id": 7,
    })

    assert calls[0]["text"] == "새우"


def test_shopping_stock_in_follow_up_keeps_shopping_context():
    history = [SimpleNamespace(role="bot", text="현재 장보기 목록이에요.", intent="shopping.current", slots={})]

    result = supervisor_agent.router_node({"text": "냉장고로 입고해줘", "history": history})

    assert result["intent"] == "shopping.purchase"

def test_alarm_action_payload_survives_supervisor_adapter(monkeypatch):
    """Alarm Agent의 action payload가 슈퍼바이저 버튼 메시지에 유지되는지 확인합니다."""

    def fake_run(**kwargs):
        return {
            "intent": "calendar.create",
            "message": "등록할까요?",
            "ui": {
                "actions": [
                    {
                        "label": "등록",
                        "value": {
                            "intent": "calendar.create",
                            "action": "create_event",
                            "payload": {
                                "title": "우유",
                                "date_text": "내일",
                                "reminder_type": "shopping_reminder",
                            },
                        },
                    }
                ]
            },
        }

    monkeypatch.setattr(alarm_agent_module, "run", fake_run)

    result = supervisor_agent.alarm_agent_node({"text": "내일 우유 사기 알림 등록해줘", "intent": "alarm.notification", "db": SimpleNamespace(), "user_id": 7})
    message = result["actions"][0]["data"]["message"]
    action_payload = json.loads(message.split(":", 2)[2])

    assert message.startswith("확인:alarm:")
    assert action_payload["payload"]["reminder_type"] == "shopping_reminder"


def test_alarm_calendar_connection_error_is_mapped_to_korean(monkeypatch):
    """Google Calendar 미연동 오류는 한국어 안내와 연결 버튼으로 변환합니다."""

    def fake_run(**_kwargs):
        return {
            "ok": False,
            "intent": "calendar.create",
            "message": "Google Calendar is not connected.",
            "error": {"code": "HTTP_404", "message": "Google Calendar is not connected."},
        }

    monkeypatch.setattr(alarm_agent_module, "run", fake_run)

    result = supervisor_agent.alarm_agent_node({
        "text": "확인:alarm:{}",
        "intent": "action.confirm",
        "db": SimpleNamespace(),
        "user_id": 7,
    })

    assert result["response_text"] == "일정을 등록하려면 먼저 Google Calendar를 연결해주세요."
    assert result["slots"]["agent_status"] == "needs_input"
    assert result["actions"] == [{"label": "캘린더 연결하기", "url": "/mypage"}]


def test_alarm_confirm_payload_returns_to_alarm_agent(monkeypatch):
    """슈퍼바이저 확인 메시지가 Alarm Agent 실행 인자로 복원되는지 확인합니다."""
    calls = []

    def fake_run(**kwargs):
        calls.append(kwargs)
        return {"intent": "calendar.create", "message": "등록했어요.", "ui": {"actions": []}}

    monkeypatch.setattr(alarm_agent_module, "run", fake_run)
    payload = {"intent": "calendar.create", "action": "create_event", "payload": {"title": "우유", "date_text": "내일", "reminder_type": "shopping_reminder"}}

    supervisor_agent.alarm_agent_node({"text": "확인:alarm:" + json.dumps(payload, ensure_ascii=False), "intent": "action.confirm", "db": SimpleNamespace(), "user_id": 7})

    assert calls[0]["intent"] == "calendar.create"
    assert calls[0]["action"] == "create_event"
    assert calls[0]["payload"]["reminder_type"] == "shopping_reminder"
    assert calls[0]["confirmed"] is True


def test_context_switch_replaces_pending_inventory_request():
    """번복 뒤 새 재료 요청은 이전 pending 식재료를 이어받지 않습니다."""
    history = [SimpleNamespace(role="bot", text="두부를 몇 개 추가하시겠어요?", intent="inventory.action")]
    assert chat_context._rewrite_context_switch("소금 대신 뭐 넣어?") == "소금 대신 뭐 넣어?"

    for message in ("아니다 치즈 넣어줘", "두부말고 치즈 넣어줘", "두부 대신 치즈 넣어줘"):
        result = supervisor_agent.router_node({"text": message, "history": history})

        assert result["intent"] == "inventory.action"
        assert result["text"] == "치즈 넣어줘"
        assert result["history"] == []


def test_short_follow_up_inherits_previous_agent_intent():
    """주어가 생략된 짧은 질문은 직전 봇 응답의 intent를 이어받습니다."""
    history = [SimpleNamespace(role="bot", text="외 2개가 더 있어요.", intent="shopping.current")]

    result = supervisor_agent.router_node({"text": "외 2개는 뭐야?", "history": history})

    assert result["intent"] == "shopping.current"


def test_context_follow_up_keeps_previous_agent_domain():
    """생략된 쓰기 명령은 냉장고 규칙보다 직전 에이전트 문맥을 우선합니다."""
    shopping_history = [SimpleNamespace(role="bot", text="현재 장보기 목록이에요.", intent="shopping.current", slots={"shown_count": 5})]
    alarm_history = [SimpleNamespace(role="bot", text="등록된 일정이에요.", intent="alarm.calendar", slots={"date": "내일"})]

    shopping_result = supervisor_agent.router_node({"text": "그거 삭제해줘", "history": shopping_history})
    alarm_result = supervisor_agent.router_node({"text": "그거 삭제해줘", "history": alarm_history})

    assert shopping_result["intent"] == "shopping.delete_item"
    assert shopping_result["slots"] == {"shown_count": 5}
    assert alarm_result["intent"] == "alarm.calendar"
    assert alarm_result["slots"] == {"date": "내일"}


def test_context_follow_up_keeps_previous_slots():
    """보관 위치처럼 주어가 생략된 질문에도 직전 슬롯을 유지합니다."""
    history = [SimpleNamespace(role="bot", text="두부 보관법이에요.", intent="ingredient.guide", slots={"ingredient": "두부"})]

    result = supervisor_agent.router_node({"text": "냉동은?", "history": history})

    assert result["intent"] == "ingredient.guide"
    assert result["slots"] == {"ingredient": "두부"}


def test_guide_context_switch_uses_latest_ingredient():
    """정정한 식재료 질문은 이전 재료명을 제거하고 Guide Agent에 전달합니다."""
    received = []

    class GuideService:
        def _reply_guide(self, text):
            received.append(text)
            return {"response_text": "양파 보관법이에요.", "actions": [], "sources": []}

    result = supervisor_agent.guide_agent_node({"text": "감자 말고 양파 보관법", "service": GuideService()})

    assert received == ["양파 보관법"]
    assert result["response_text"] == "양파 보관법이에요."


def test_guide_follow_up_reuses_previous_ingredient_and_guide_type():
    """가이드 후속 질문은 직전 식재료와 가이드 유형으로 복원합니다."""
    received = []

    class GuideService:
        def _reply_guide(self, text):
            received.append(text)
            return {"response_text": "감자 냉동 보관법이에요.", "actions": [], "sources": []}

    result = supervisor_agent.guide_agent_node(
        {
            "text": "그럼 냉동 보관은?",
            "slots": {"ingredient": "감자", "guide_type": "storage"},
            "service": GuideService(),
        }
    )

    assert received == ["감자 냉동 보관법"]
    assert result["response_text"] == "감자 냉동 보관법이에요."

def test_context_switch_cancel_word_stops_pending_request():
    """새 명령이 없는 번복 표현은 진행 중 작업을 취소합니다."""
    history = [SimpleNamespace(role="bot", text="두부를 몇 개 추가하시겠어요?", intent="inventory.action")]

    result = supervisor_agent.router_node({"text": "아니다", "history": history})

    assert result["intent"] == "action.cancel"


def test_supervisor_rewrites_guide_queries_for_domain_agent():
    """가이드 질문은 식재료명과 조회 유형이 분명한 문장으로 정규화합니다."""
    assert supervisor_utils._rewrite_guide_query("감자와 비슷한 식재료도 알려줘") == "감자 뭐가 있어?"
    assert supervisor_utils._rewrite_guide_query("양파 깨끗하게 세척하는 방법") == "양파 세척법 알려줘"
    assert supervisor_utils._rewrite_guide_query("고추 영양성분과 칼로리 알려줘") == "고추 영양성분 알려줘"


def test_supervisor_normalizes_shopping_create_question_suffix():
    """장보기 추가 의문형 어미가 상품명으로 전달되지 않게 정리합니다."""
    normalized = supervisor_utils._normalize_shopping_create_query("우유 2개를 장보기 목록에 추가할까?")

    assert normalized == "우유 2개를 장보기 목록 추가해줘"
    assert "할까" not in normalized


def test_multi_agent_plan_is_not_overwritten_by_keyword_correction():
    """LLM의 유효한 복합 계획은 소비기한·레시피 키워드 보정이 덮어쓰지 않습니다."""

    class FakeService:
        """의존성이 포함된 복합 계획을 반환합니다."""

        def _route_intent_payload_with_llm(self, _text, _history):
            return {
                "intent": "multi_agent",
                "confidence": 0.9,
                "slots": {},
                "tasks": [
                    {"id": "expiry", "intent": "inventory.expiring", "text": "임박 재료 알려줘", "mode": "read", "depends_on": []},
                    {"id": "recipe", "intent": "recipe.recommend", "text": "그 재료로 레시피 추천해줘", "mode": "read", "depends_on": ["expiry"]},
                ],
            }

    result = supervisor_agent.router_node({
        "text": "소비기한 임박 재료랑 그걸로 만들 레시피 알려줘",
        "history": [],
        "service": FakeService(),
    })

    assert result["intent"] == "multi_agent"
    assert [task["id"] for task in result["tasks"]] == ["expiry", "recipe"]


def test_multi_agent_runs_dependency_before_recipe(monkeypatch):
    """임박 재료 조회 결과를 받은 뒤 Recipe Agent가 실행됩니다."""
    calls = []

    def fake_inventory(_state):
        calls.append("inventory")
        return {"response_text": "두부 D-1", "slots": {"expiring_ingredients": ["두부"]}}

    def fake_recipe(state):
        calls.append("recipe")
        assert state["text"] == "두부를 우선 활용하는 레시피를 추천해줘"
        return {"response_text": "두부김치를 추천해요.", "slots": {}}

    monkeypatch.setattr(supervisor_agent, "inventory_agent_node", fake_inventory)
    monkeypatch.setattr(supervisor_agent, "recipe_agent_node", fake_recipe)

    result = _invoke_multi_agent({
        "text": "임박 재료와 레시피 알려줘",
        "tasks": [
            {"intent": "recipe.recommend", "text": "레시피 추천해줘"},
            {"intent": "inventory.expiring", "text": "임박 재료 알려줘"},
        ],
    })

    assert calls == ["inventory", "recipe"]
    assert result["slots"]["completed_intents"] == ["recipe.recommend", "inventory.expiring"]


def test_multi_agent_runs_independent_reads_in_parallel(monkeypatch):
    """서로 의존하지 않는 읽기 task는 같은 실행 묶음에서 병렬 처리합니다."""
    from threading import Barrier

    barrier = Barrier(2)

    def fake_guide(_state):
        barrier.wait(timeout=2)
        return {"response_text": "감자 보관법", "slots": {}}

    def fake_shopping(_state):
        barrier.wait(timeout=2)
        return {"response_text": "감자 가격", "slots": {}}

    monkeypatch.setattr(supervisor_agent, "guide_agent_node", fake_guide)
    monkeypatch.setattr(supervisor_agent, "shopping_agent_node", fake_shopping)

    result = _invoke_multi_agent({
        "text": "감자 보관법과 가격 알려줘",
        "tasks": [
            {"id": "guide", "intent": "ingredient.guide", "text": "감자 보관법", "depends_on": []},
            {"id": "price", "intent": "shopping.compare", "text": "감자 가격", "depends_on": []},
        ],
    })

    assert "감자 보관법" in result["response_text"]
    assert "감자 가격" in result["response_text"]


def test_multi_agent_replans_failed_read_once(monkeypatch):
    """실패한 읽기 task만 한 번 보정해 다시 실행합니다."""
    calls = []

    def fake_guide(state):
        calls.append(state["text"])
        if len(calls) == 1:
            return {"status": "error", "response_text": "요청을 처리하는 중 문제가 생겼어요."}
        return {"response_text": "감자 보관법", "slots": {}}

    def fake_shopping(_state):
        return {"response_text": "감자 가격", "slots": {}}

    class FakeService:
        """실패한 가이드 질문을 한 번만 구체화합니다."""

        def _repair_multi_agent_task(self, _text, task, _results):
            return {**task, "text": "감자 보관법 알려줘"}

        def _synthesize_multi_agent_response(self, _text, _results):
            return None

    monkeypatch.setattr(supervisor_agent, "guide_agent_node", fake_guide)
    monkeypatch.setattr(supervisor_agent, "shopping_agent_node", fake_shopping)

    result = _invoke_multi_agent({
        "text": "감자 보관법과 가격 알려줘",
        "service": FakeService(),
        "tasks": [
            {"id": "guide", "intent": "ingredient.guide", "text": "감자 알려줘", "depends_on": []},
            {"id": "price", "intent": "shopping.compare", "text": "감자 가격", "depends_on": []},
        ],
    })

    assert calls == ["감자 알려줘", "감자 보관법 알려줘"]
    assert result["slots"]["failed_intents"] == []


def test_mixed_read_write_request_reaches_multi_agent_planner():
    """장보기 단어가 있어도 조회와 쓰기가 섞인 요청은 단일 Shopping intent로 잘리지 않습니다."""

    class FakeService:
        """조회 후 장보기 추가 계획을 반환합니다."""

        def _route_intent_payload_with_llm(self, _text, _history):
            return {
                "intent": "multi_agent",
                "confidence": 0.9,
                "slots": {},
                "tasks": [
                    {"id": "expiry", "intent": "inventory.expiring", "text": "임박 재료 알려줘", "depends_on": []},
                    {"id": "shopping", "intent": "shopping.create", "text": "필요한 재료를 장보기에 추가해줘", "depends_on": ["expiry"]},
                ],
            }

    result = supervisor_agent.router_node({
        "text": "임박 재료를 확인하고 필요한 재료를 장보기 목록에 추가해줘",
        "history": [],
        "service": FakeService(),
    })

    assert result["intent"] == "multi_agent"
    assert [task["intent"] for task in result["tasks"]] == ["inventory.expiring", "shopping.create"]


def test_llm_router_uses_last_twelve_messages():
    """LLM 의도 분류 문맥에는 최근 12개 메시지만 전달합니다."""
    history = [SimpleNamespace(role="user", text=f"질문 {index}") for index in range(15)]

    result = chat_context._build_llm_route_history(history)

    assert len(result) == 12
    assert result[0]["text"] == "질문 3"


def test_llm_router_prunes_diagnostic_slots_from_history():
    """LLM 라우팅 이력에는 후속 대화에 필요한 슬롯만 전달합니다."""
    history = [{
        "role": "bot",
        "text": "복합 요청을 처리했어요.",
        "intent": "multi_agent",
        "slots": {
            "ingredient": "감자",
            "task_outcomes": [{"id": "guide", "status": "completed"}],
            "completed_intents": ["ingredient.guide"],
        },
    }]

    result = chat_context._build_llm_route_history(history)

    assert result[0]["slots"] == {"ingredient": "감자"}
def test_llm_plan_parser_keeps_dependencies_and_write_mode():
    """LLM 계획 JSON의 의존성과 쓰기 모드를 안전한 task 계약으로 변환합니다."""
    payload = supervisor_utils._parse_llm_route_payload(json.dumps({
        "intent": "multi_agent",
        "confidence": 0.9,
        "tasks": [
            {"id": "lookup", "intent": "inventory.expiring", "text": "임박 재료 조회", "depends_on": []},
            {"id": "write", "intent": "shopping.create", "text": "장보기에 추가", "depends_on": ["lookup"]},
        ],
    }, ensure_ascii=False))

    assert payload["tasks"][0]["mode"] == "read"
    assert payload["tasks"][1]["mode"] == "write"
    assert payload["tasks"][1]["depends_on"] == ["lookup"]


def test_dependent_write_task_uses_previous_agent_result(monkeypatch):
    """조회 결과가 필요한 쓰기 task는 Supervisor가 실행 문장으로 구체화한 뒤 전달합니다."""
    received = []

    def fake_inventory(_state):
        return {"response_text": "임박 재료는 두부예요.", "slots": {"expiring_ingredients": ["두부"]}}

    def fake_shopping(state):
        received.append(state["text"])
        return {"response_text": "두부를 장보기에 추가할까요?", "slots": {}}

    class FakeService:
        """선행 결과를 근거로 장보기 실행 문장을 생성합니다."""

        def _resolve_multi_agent_task(self, _text, task, _results):
            return {**task, "text": "두부를 장보기 목록에 추가해줘"}

    monkeypatch.setattr(supervisor_agent, "inventory_agent_node", fake_inventory)
    monkeypatch.setattr(supervisor_agent, "shopping_agent_node", fake_shopping)

    result = _invoke_multi_agent({
        "text": "임박 재료를 확인하고 장보기 목록에 추가해줘",
        "service": FakeService(),
        "tasks": [
            {"id": "expiry", "intent": "inventory.expiring", "text": "임박 재료 알려줘", "depends_on": []},
            {"id": "shopping", "intent": "shopping.create", "text": "장보기에 추가해줘", "depends_on": ["expiry"]},
        ],
    })

    assert received == ["두부를 장보기 목록에 추가해줘"]
    assert result["slots"]["completed_intents"] == ["inventory.expiring", "shopping.create"]

def test_recipe_result_supplies_calendar_title_without_llm(monkeypatch):
    """추천 메뉴가 필요한 일정은 첫 레시피 제목을 사용해 실행 문장을 완성합니다."""
    monkeypatch.setattr("ai.agents.supervisor_agent.supervisor_service.app_settings.OPENAI_API_KEY", "")

    task = {
        "id": "calendar",
        "intent": "alarm.calendar",
        "text": "내일 오후 6시 30분에 일정 등록해줘",
        "mode": "write",
        "depends_on": ["recipe"],
    }
    result = supervisor_service._resolve_multi_agent_task(
        "냉장고 재료로 레시피 추천하고 내일 오후 6시 30분에 일정 등록해줘",
        task,
        [{
            "response_text": "고추장찌개, 카레라이스, 찜닭을 추천해요.",
            "actions": [
                {"label": "고추장찌개", "url": "/recipes/1", "data": {"recipe_id": 1, "title": "고추장찌개"}},
                {"label": "카레라이스", "url": "/recipes/2", "data": {"recipe_id": 2, "title": "카레라이스"}},
            ],
        }],
    )

    assert result["text"] == "내일 오후 6시 30분에 고추장찌개 일정 등록해줘"


def test_inventory_recipe_calendar_request_runs_in_dependency_order(monkeypatch):
    """냉장고 조회, 레시피 추천, 일정 등록 요청을 결과 의존 순서대로 처리합니다."""
    calls = []

    def fake_inventory(_state):
        calls.append("inventory.list")
        return {"response_text": "현재 냉장고에는 김치와 두부가 있어요."}

    def fake_recipe(state):
        calls.append("recipe.recommend")
        assert state["text"] == "김치와 두부로 레시피 추천해줘"
        return {"response_text": "두부김치를 추천해요."}

    def fake_alarm(state):
        calls.append("alarm.calendar")
        assert state["text"] == "내일 6시 30분에 두부김치 일정 등록해줘"
        return {
            "response_text": "내일 6시 30분에 두부김치 일정을 등록할까요?",
            "actions": [{"label": "등록", "data": {"message": "확인토큰:test"}}],
        }

    class FakeService:
        """대표 복합 요청을 세 개의 의존 task로 계획하고 구체화합니다."""

        def _route_intent_payload_with_llm(self, _text, _history):
            return {
                "intent": "multi_agent",
                "confidence": 0.95,
                "slots": {},
                "tasks": [
                    {"id": "inventory", "intent": "inventory.list", "text": "냉장고 재료 조회해줘", "depends_on": []},
                    {"id": "recipe", "intent": "recipe.recommend", "text": "그 재료로 레시피 추천해줘", "depends_on": []},
                    {"id": "calendar", "intent": "alarm.calendar", "text": "내일 6시 30분에 일정 등록해줘", "depends_on": []},
                ],
            }

        def _resolve_multi_agent_task(self, _text, task, dependency_results):
            if task["intent"] == "recipe.recommend":
                assert dependency_results[0]["response_text"] == "현재 냉장고에는 김치와 두부가 있어요."
                return {**task, "text": "김치와 두부로 레시피 추천해줘"}
            assert task["intent"] == "alarm.calendar"
            assert dependency_results[0]["response_text"] == "두부김치를 추천해요."
            return {**task, "text": "내일 6시 30분에 두부김치 일정 등록해줘"}

    service = FakeService()
    route = supervisor_agent.router_node({
        "text": "냉장고 재료 조회해서 레시피 추천해주고 내일 6시 30분에 일정 등록해줘",
        "history": [],
        "service": service,
        "user_id": 2,
    })
    assert route["intent"] == "multi_agent"

    monkeypatch.setattr(supervisor_agent, "inventory_agent_node", fake_inventory)
    monkeypatch.setattr(supervisor_agent, "recipe_agent_node", fake_recipe)
    monkeypatch.setattr(supervisor_agent, "alarm_agent_node", fake_alarm)

    result = _invoke_multi_agent({
        "text": "냉장고 재료 조회해서 레시피 추천해주고 내일 6시 30분에 일정 등록해줘",
        "history": [],
        "service": service,
        "user_id": 2,
        "tasks": route["tasks"],
    })

    assert calls == ["inventory.list", "recipe.recommend", "alarm.calendar"]
    assert result["slots"]["completed_intents"] == [
        "inventory.list",
        "recipe.recommend",
    ]
    assert result["slots"]["awaiting_input_intents"] == ["alarm.calendar"]
    assert result["actions"][0]["label"] == "등록"

def test_inventory_recipe_calendar_request_has_rule_fallback_when_llm_plan_fails():
    """LLM 계획이 실패해도 대표 복합 요청은 세 개의 Supervisor task로 유지합니다."""

    class FailedPlanner:
        """복합 계획을 만들지 못한 LLM 응답을 재현합니다."""

        def _route_intent_payload_with_llm(self, _text, _history):
            return {"intent": "general", "confidence": 0.0, "slots": {}, "tasks": []}

    result = supervisor_agent.router_node({
        "text": "냉장고 재료 조회해서 레시피 추천해주고 내일 6시 30분에 일정 등록해줘",
        "history": [],
        "service": FailedPlanner(),
        "user_id": 2,
    })

    assert result["intent"] == "multi_agent"
    assert [task["intent"] for task in result["tasks"]] == [
        "inventory.list",
        "recipe.recommend",
        "alarm.calendar",
    ]
    assert result["tasks"][2]["text"] == "내일 6시 30분에 일정 등록해줘"

def test_alarm_task_mode_distinguishes_lookup_and_write_requests():
    """알람과 일정의 조회 요청은 읽기, 변경 요청은 쓰기 작업으로 구분합니다."""
    tasks = [
        {"intent": "alarm.calendar", "text": "내일 일정 조회해줘"},
        {"intent": "alarm.calendar", "text": "내일 일정 등록해줘"},
        {"intent": "alarm.notification", "text": "읽지 않은 알림 있어?"},
        {"intent": "alarm.notification", "text": "우유 구매 알림 등록해줘"},
    ]

    plan = supervisor_agent._prepare_task_plan(tasks)

    assert [task["mode"] for task in plan] == ["read", "write", "read", "write"]


def test_read_task_rejects_write_confirmation_result():
    """조회 작업이 쓰기 확인 상태로 바뀌면 성공 결과로 처리하지 않습니다."""
    task = {"intent": "alarm.calendar", "text": "내일 일정 조회해줘", "mode": "read"}
    result = {
        "response_text": "일정을 등록할까요?",
        "pending_action": {"action": "create_event"},
    }

    assert supervisor_agent._agent_result_outcome(task, result) == "failed"


def test_shopping_product_selection_waits_without_retry(monkeypatch):
    """가격 조회의 상품 후보 선택은 실패 재시도 없이 사용자 입력을 기다립니다."""
    calls = []

    def fake_shopping(_state):
        calls.append("shopping.compare")
        return {
            "response_text": "네이버 쇼핑 기준 상품 후보예요.",
            "actions": [
                {"label": "1번 담기", "data": {"message": "확인:shopping_select_product:0"}},
                {"label": "선택 취소", "data": {"message": "확인:shopping_cancel_flow:"}},
            ],
        }

    class Service:
        """재시도가 발생하면 테스트를 실패시키는 최소 서비스 대역입니다."""

        def _repair_multi_agent_task(self, *_args):
            raise AssertionError("상품 후보 선택 응답을 실패로 재시도하면 안 됩니다.")

    monkeypatch.setattr(supervisor_agent, "shopping_agent_node", fake_shopping)
    monkeypatch.setattr(
        supervisor_agent,
        "guide_agent_node",
        lambda _state: {"response_text": "감자 보관법이에요."},
    )

    result = _invoke_multi_agent({
        "text": "감자 보관법과 가격 알려줘",
        "tasks": [
            {"id": "guide", "intent": "ingredient.guide", "text": "감자 보관법 알려줘"},
            {"id": "shopping", "intent": "shopping.compare", "text": "감자 가격 알려줘"},
        ],
        "service": Service(),
    })

    assert calls == ["shopping.compare"]
    assert result["slots"]["awaiting_input_intents"] == ["shopping.compare"]
    assert result["slots"]["failed_intents"] == []


def test_multi_agent_does_not_synthesize_before_shopping_selection(monkeypatch):
    """가격 상품 선택이 남아 있으면 완료된 일부 결과만으로 최종 답변을 합성하지 않습니다."""
    class Service:
        """불완전한 결과 합성이 호출되는지 확인하는 최소 테스트 서비스입니다."""

        def _synthesize_multi_agent_response(self, *_args):
            raise AssertionError("상품 선택 전에는 복합 응답을 합성하면 안 됩니다.")

    monkeypatch.setattr(
        supervisor_agent,
        "guide_agent_node",
        lambda _state: {"response_text": "감자는 서늘하고 어두운 곳에 보관하세요."},
    )
    monkeypatch.setattr(
        supervisor_agent,
        "recipe_agent_node",
        lambda _state: {"response_text": "감자채볶음을 추천해요."},
    )
    monkeypatch.setattr(
        supervisor_agent,
        "shopping_agent_node",
        lambda _state: {
            "response_text": "감자 상품을 선택해주세요.",
            "actions": [
                {"label": "1번 선택", "data": {"message": "확인:shopping_select_product:0"}},
            ],
        },
    )

    result = _invoke_multi_agent({
        "text": "감자 보관법과 감자 가격, 감자 레시피를 모두 알려줘",
        "tasks": [
            {"id": "guide", "intent": "ingredient.guide", "text": "감자 보관법 알려줘"},
            {"id": "shopping", "intent": "shopping.compare", "text": "감자 가격 알려줘"},
            {"id": "recipe", "intent": "recipe.search", "text": "감자 레시피 알려줘"},
        ],
        "service": Service(),
    })

    assert "감자 상품을 선택해주세요." in result["response_text"]
    assert result["slots"]["awaiting_input_intents"] == ["shopping.compare"]
def test_multi_agent_reports_partial_failure_by_task(monkeypatch):
    """일부 Agent만 실패하면 성공 결과와 실패한 작업명을 함께 안내합니다."""
    monkeypatch.setattr(
        supervisor_agent,
        "inventory_agent_node",
        lambda _state: {"response_text": "현재 냉장고에는 감자가 있어요."},
    )
    monkeypatch.setattr(
        supervisor_agent,
        "recipe_agent_node",
        lambda _state: {"status": "error", "response_text": "레시피 조회에 실패했어요."},
    )

    result = _invoke_multi_agent({
        "text": "냉장고를 보여주고 레시피도 추천해줘",
        "tasks": [
            {"id": "inventory", "intent": "inventory.list", "text": "냉장고 재료 조회해줘"},
            {"id": "recipe", "intent": "recipe.recommend", "text": "감자 레시피 추천해줘"},
        ],
    })

    assert "현재 냉장고에는 감자가 있어요." in result["response_text"]
    assert "처리하지 못한 요청: 레시피 추천" in result["response_text"]
    assert result["slots"]["completed_intents"] == ["inventory.list"]
    assert result["slots"]["failed_intents"] == ["recipe.recommend"]
    assert result["slots"]["task_outcomes"][1]["status"] == "failed"


def test_confirmation_pending_task_blocks_dependent_task(monkeypatch):
    """사용자 확인을 기다리는 쓰기 작업의 후속 작업은 먼저 실행하지 않습니다."""
    calls = []

    def fake_shopping(_state):
        calls.append("shopping.create")
        return {
            "response_text": "감자를 장보기 목록에 추가할까요?",
            "actions": [{"label": "추가", "data": {"message": "확인:add_item"}}],
        }

    def fake_recipe(_state):
        calls.append("recipe.recommend")
        return {"response_text": "감자 요리를 추천해요."}

    monkeypatch.setattr(supervisor_agent, "shopping_agent_node", fake_shopping)
    monkeypatch.setattr(supervisor_agent, "recipe_agent_node", fake_recipe)

    result = _invoke_multi_agent({
        "text": "감자를 장보기에 추가하고 그 재료로 레시피 추천해줘",
        "tasks": [
            {"id": "shopping", "intent": "shopping.create", "text": "감자를 장보기에 추가해줘"},
            {"id": "recipe", "intent": "recipe.recommend", "text": "그 재료로 레시피 추천해줘", "depends_on": ["shopping"]},
        ],
    })

    assert calls == ["shopping.create"]
    assert result["slots"]["awaiting_input_intents"] == ["shopping.create"]
    assert result["slots"]["blocked_intents"] == ["recipe.recommend"]
    assert "앞 작업이 완료되지 않아 실행하지 않은 요청: 레시피 추천" in result["response_text"]
    assert result["slots"]["supervisor_resume_tasks"][0]["intent"] == "recipe.recommend"
    assert result["slots"]["supervisor_original_request"] == "감자를 장보기에 추가하고 그 재료로 레시피 추천해줘"


def test_confirmed_action_restores_remaining_supervisor_plan(monkeypatch):
    """서명된 확인 요청은 저장된 후속 작업과 함께 복합 계획으로 복원합니다."""
    monkeypatch.setattr(
        supervisor_agent,
        "_verify_and_claim_confirm_token",
        lambda _text, _user_id: "shopping_create:{\"items\":[{\"name\":\"감자\"}]}",
    )

    result = supervisor_agent.router_node({
        "text": "확인토큰:test",
        "history": [],
        "user_id": 7,
        "context_enforced": True,
        "trusted_context": {
            "intent": "multi_agent",
            "slots": {
                "supervisor_original_request": "감자를 장보기에 추가하고 그 재료로 레시피 추천해줘",
                "supervisor_resume_tasks": [{
                    "id": "recipe",
                    "intent": "recipe.recommend",
                    "text": "그 재료로 레시피 추천해줘",
                    "depends_on": ["shopping"],
                }],
            },
        },
    })

    assert result["intent"] == "multi_agent"
    assert result["text"] == "감자를 장보기에 추가하고 그 재료로 레시피 추천해줘"
    assert [task["intent"] for task in result["tasks"]] == ["action.confirm", "recipe.recommend"]
    assert result["tasks"][1]["depends_on"] == ["confirmed_action"]



def test_supervisor_resume_plan_round_trips_through_signed_context():
    """남은 Supervisor 계획은 현재 사용자와 세션에 귀속된 토큰으로 복원됩니다."""
    response = {
        "intent": "multi_agent",
        "slots": {
            "supervisor_original_request": "감자를 추가하고 레시피 추천해줘",
            "supervisor_resume_tasks": [{
                "id": "recipe",
                "intent": "recipe.recommend",
                "text": "그 재료로 레시피 추천해줘",
                "depends_on": ["inventory"],
            }],
        },
    }

    token = chat_context._issue_context_token(response, user_id=7, session_id="session-resume")
    restored = chat_context._verify_context_token(token, user_id=7, session_id="session-resume")

    assert restored["slots"]["supervisor_resume_tasks"][0]["intent"] == "recipe.recommend"
    assert chat_context._verify_context_token(token, user_id=8, session_id="session-resume") == {}


def test_signed_confirmation_token_cannot_be_reused():
    """같은 확인 토큰은 최초 한 번만 내부 실행 명령으로 변환됩니다."""
    command = "확인:add_ingredient:감자:1:냉장"
    token = supervisor_utils._issue_confirm_token(command, user_id=7)

    assert supervisor_utils._verify_and_claim_confirm_token(token, user_id=7) == command
    assert supervisor_utils._verify_and_claim_confirm_token(token, user_id=7) is None


def test_multi_agent_graph_exposes_agent_specific_fanout_nodes():
    """복합 요청 그래프는 단일 처리 노드 대신 Agent별 병렬 분기를 노출합니다."""
    nodes = supervisor_agent.supervisor_agent.get_graph().nodes

    assert "multi_agent_node" not in nodes
    assert "Guide Agent" in nodes
    assert "Recipe Agent" in nodes
    assert "Shopping Agent" in nodes
    assert "execution_collect_node" in nodes


def test_compiled_graph_runs_independent_agent_branches_in_parallel(monkeypatch):
    """독립된 Guide와 Shopping 작업은 컴파일된 LangGraph에서 동시에 실행됩니다."""
    from threading import Barrier

    barrier = Barrier(2)

    class Service:
        """두 개의 독립 조회 작업을 반환하는 Supervisor 서비스 대역입니다."""

        def _route_intent_payload_with_llm(self, _text, _history):
            return {
                "intent": "multi_agent",
                "confidence": 0.95,
                "slots": {},
                "tasks": [
                    {"id": "guide", "intent": "ingredient.guide", "text": "감자 보관법", "depends_on": []},
                    {"id": "price", "intent": "shopping.compare", "text": "감자 가격", "depends_on": []},
                ],
            }

        def _synthesize_multi_agent_response(self, _text, _results):
            return None

    def fake_guide(_state):
        barrier.wait(timeout=3)
        return {"response_text": "감자 보관법", "slots": {}}

    def fake_shopping(_state):
        barrier.wait(timeout=3)
        return {"response_text": "감자 가격", "slots": {}}

    monkeypatch.setattr(supervisor_agent, "guide_agent_node", fake_guide)
    monkeypatch.setattr(supervisor_agent, "shopping_agent_node", fake_shopping)

    result = supervisor_agent.supervisor_agent.invoke({
        "text": "감자 보관법과 가격 알려줘",
        "history": [],
        "service": Service(),
        "user_id": 2,
    })

    assert "감자 보관법" in result["response_text"]
    assert "감자 가격" in result["response_text"]
    assert result["slots"]["completed_intents"] == ["ingredient.guide", "shopping.compare"]


def test_multi_agent_dispatch_serializes_write_tasks():
    """독립된 쓰기 작업도 한 번에 하나씩만 실행 묶음에 포함합니다."""
    plan = supervisor_agent._prepare_task_plan([
        {"id": "inventory", "intent": "inventory.action", "text": "양파 추가해줘"},
        {"id": "shopping", "intent": "shopping.create", "text": "감자 장보기에 넣어줘"},
    ])

    first = supervisor_agent.execution_dispatch_node({
        "multi_plan": plan,
        "multi_task_results": {},
    })
    second = supervisor_agent.execution_dispatch_node({
        "multi_plan": plan,
        "multi_task_results": {
            "inventory": {"task": plan[0], "result": {"response_text": "완료"}, "outcome": "completed"},
        },
    })

    assert [task["id"] for task in first["multi_batch"]] == ["inventory"]
    assert [task["id"] for task in second["multi_batch"]] == ["shopping"]


def test_parallel_read_fails_when_isolated_db_session_cannot_open(monkeypatch):
    """병렬 조회 세션 생성 실패 시 부모 요청의 DB 세션을 공유하지 않습니다."""
    def fail_session():
        """독립 DB 세션 생성 실패를 재현합니다."""
        raise RuntimeError("DB 연결 실패")

    monkeypatch.setattr("app.backend.db.session.SessionLocal", fail_session)
    handler_called = False

    def fake_guide(_state):
        """공유 세션으로 실행되는지 확인하는 가짜 Guide 핸들러입니다."""
        nonlocal handler_called
        handler_called = True
        return {"response_text": "감자 보관법"}

    with pytest.raises(RuntimeError, match="병렬 조회용 DB 세션"):
        supervisor_agent._run_multi_task(
            {"text": "감자 보관법", "db": object(), "slots": {}},
            {"id": "guide", "intent": "ingredient.guide", "text": "감자 보관법", "mode": "read", "depends_on": []},
            {},
            {"Guide Agent (Single)": fake_guide},
            isolated_db=True,
        )

    assert handler_called is False


def test_parallel_branch_records_domain_agent_observation(monkeypatch):
    """병렬 분기의 실제 도메인 Agent 호출이 Langfuse Agent 구간으로 기록됩니다."""
    captured = {}

    class Observation:
        """Langfuse observation의 입력과 결과 갱신을 저장합니다."""

        def __enter__(self):
            return self

        def __exit__(self, _exc_type, _exc, _traceback):
            return False

        def update(self, **kwargs):
            captured["update"] = kwargs

    class Client:
        """Agent observation 생성 요청을 저장하는 가짜 Langfuse 클라이언트입니다."""

        def start_as_current_observation(self, **kwargs):
            captured["start"] = kwargs
            return Observation()

    monkeypatch.setattr(supervisor_agent, "get_langfuse_client", lambda: Client())
    monkeypatch.setattr(
        supervisor_agent,
        "guide_agent_node",
        lambda _state: {"response_text": "감자 보관법", "slots": {}},
    )

    result = supervisor_agent._run_parallel_agent_branch({
        "text": "감자 보관법 알려줘",
        "multi_current_task": {
            "id": "guide_1",
            "intent": "ingredient.guide",
            "text": "감자 보관법 알려줘",
            "mode": "read",
            "depends_on": [],
        },
        "multi_task_results": {},
    })

    assert captured["start"]["name"] == "Guide Agent"
    assert captured["start"]["as_type"] == "agent"
    assert captured["start"]["input"]["task_id"] == "guide_1"
    assert captured["update"]["output"]["outcome"] == "completed"
    assert result["multi_task_results"]["guide_1"]["outcome"] == "completed"


def test_compiled_graph_runs_dependent_tasks_in_separate_steps(monkeypatch):
    """냉장고 조회, 레시피 추천, 일정 확인은 선행 결과 순서대로 다시 분기됩니다."""
    calls = []

    class Service:
        """의존성이 있는 세 작업을 반환하고 후속 문장을 구체화합니다."""

        def _route_intent_payload_with_llm(self, _text, _history):
            return {
                "intent": "multi_agent",
                "confidence": 0.95,
                "slots": {},
                "tasks": [
                    {"id": "inventory", "intent": "inventory.list", "text": "냉장고 조회", "depends_on": []},
                    {"id": "recipe", "intent": "recipe.recommend", "text": "레시피 추천", "depends_on": ["inventory"]},
                    {"id": "calendar", "intent": "alarm.calendar", "text": "내일 일정 등록", "depends_on": ["recipe"]},
                ],
            }

        def _resolve_multi_agent_task(self, _text, task, _results):
            if task["intent"] == "recipe.recommend":
                return {**task, "text": "감자로 레시피 추천"}
            return {**task, "text": "내일 오후 6시 30분 감자전 일정 등록"}

    def fake_inventory(_state):
        calls.append("inventory.list")
        return {"response_text": "감자가 있어요."}

    def fake_recipe(state):
        calls.append("recipe.recommend")
        assert state["text"] == "감자로 레시피 추천"
        return {"response_text": "감자전을 추천해요."}

    def fake_alarm(state):
        calls.append("alarm.calendar")
        assert state["text"] == "내일 오후 6시 30분 감자전 일정 등록"
        return {"status": "needs_input", "response_text": "감자전 일정을 등록할까요?"}

    monkeypatch.setattr(supervisor_agent, "inventory_agent_node", fake_inventory)
    monkeypatch.setattr(supervisor_agent, "recipe_agent_node", fake_recipe)
    monkeypatch.setattr(supervisor_agent, "alarm_agent_node", fake_alarm)

    result = supervisor_agent.supervisor_agent.invoke({
        "text": "냉장고 조회해서 레시피 추천하고 내일 일정 등록해줘",
        "history": [],
        "service": Service(),
        "user_id": 2,
    })

    assert calls == ["inventory.list", "recipe.recommend", "alarm.calendar"]
    assert result["slots"]["completed_intents"] == ["inventory.list", "recipe.recommend"]
    assert result["slots"]["awaiting_input_intents"] == ["alarm.calendar"]
