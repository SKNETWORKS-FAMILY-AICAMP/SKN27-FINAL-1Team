import json
from types import SimpleNamespace

import pytest

pytest.importorskip("langchain_openai")

import ai.agents.alarm_agent.alarm_agent as alarm_agent_module
from ai.agents.supervisor_agent import supervisor_agent
from ai.agents.supervisor_agent import chat_context, supervisor_utils
from ai.agents.supervisor_agent.supervisor_service import supervisor_service


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
    assert supervisor_agent.route_intent(current_result) == "shopping_agent_node"
    assert supervisor_agent.route_intent(create_result) == "shopping_agent_node"
    assert supervisor_agent.route_intent(compare_result) == "shopping_agent_node"


def test_chat_routes_shopping_confirm_action_to_shopping_agent():
    """장보기 확인 버튼 메시지가 Inventory/Alarm이 아닌 Shopping Agent로 이동하는지 확인합니다."""
    state = {"intent": "action.confirm", "text": "확인:shopping_create:두부|양파"}

    assert supervisor_agent.route_intent(state) == "shopping_agent_node"


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
    assert supervisor_agent.route_intent(cancel) == "shopping_agent_node"


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


def test_context_switch_cancel_word_stops_pending_request():
    """새 명령이 없는 번복 표현은 진행 중 작업을 취소합니다."""
    history = [SimpleNamespace(role="bot", text="두부를 몇 개 추가하시겠어요?", intent="inventory.action")]

    result = supervisor_agent.router_node({"text": "아니다", "history": history})

    assert result["intent"] == "action.cancel"
