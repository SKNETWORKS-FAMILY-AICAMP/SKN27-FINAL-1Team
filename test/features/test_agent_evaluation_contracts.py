"""에이전트별 공통 응답 계약과 안전한 도구 실행을 검증합니다."""

from types import SimpleNamespace

from ai.agents.general_food_agent import general_food_agent
from ai.agents.guide_agent.guide_agent import answer_guide_query
from ai.agents.inventory_agent import inventory_agent
from ai.agents.recipe_agent.recipe_agent import build_supervisor_result
from ai.agents.recipe_agent.recipe_state import RecipeAction, RecipeAgentReply, RecipeSource


class _FakeGeneralFoodClient:
    """외부 OpenAI 호출 없이 General Food Agent 응답 계약을 확인하는 테스트 대역입니다."""

    def __init__(self, *, api_key: str):
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(
                create=lambda **_kwargs: SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content="에어프라이어로 데워 드세요."))]
                )
            )
        )


class _FakeDb:
    """재고 도구 실행 여부만 기록하는 최소 DB 대역입니다."""

    def rollback(self):
        """실패 경로에서 호출될 수 있는 롤백 인터페이스를 제공합니다."""


def test_guide_agent_returns_common_contract_for_unresolved_season_query():
    """제철 월이 없는 요청도 Supervisor가 처리할 수 있는 공통 응답 계약을 반환해야 합니다."""
    result = answer_guide_query("제철음식")

    assert result["agent"] == "guide"
    assert result["status"] in {"needs_input", "error", "not_found"}
    assert isinstance(result["message"], str)
    assert set(result["ui"]) == {"actions", "cards", "sources"}


def test_guide_agent_rejects_empty_query_with_common_response_contract():
    """빈 가이드 질문은 공통 상태와 오류 코드를 함께 반환해야 합니다."""
    result = answer_guide_query("")

    assert result["agent"] == "guide"
    assert result["status"] == "needs_input"
    assert result["meta"]["result_code"] == "EMPTY_GUIDE_QUERY"


def test_recipe_agent_maps_actions_and_sources_to_supervisor_contract():
    """Recipe Agent 결과는 Supervisor가 읽는 응답·버튼·출처 형식으로 변환되어야 합니다."""
    reply = RecipeAgentReply(
        message="감자 요리예요.",
        actions=[RecipeAction(label="감자볶음", url="/recipes/1", data={"recipe_id": 1})],
        sources=[RecipeSource(title="레시피 출처", url="https://example.com")],
    )

    result = build_supervisor_result(reply)

    assert result["response_text"] == "감자 요리예요."
    assert result["actions"][0]["data"]["recipe_id"] == 1
    assert result["sources"][0]["title"] == "레시피 출처"
    assert result["slots"] == {"shown_recipe_ids": [1]}


def test_general_food_agent_returns_common_response_when_model_is_available(monkeypatch):
    """General Food Agent는 외부 모델 응답을 공통 response_text 형식으로 반환해야 합니다."""
    monkeypatch.setattr(general_food_agent, "OpenAI", _FakeGeneralFoodClient)
    monkeypatch.setattr(general_food_agent, "settings", SimpleNamespace(OPENAI_API_KEY="test", OPENAI_MODEL="test"))

    result = general_food_agent.run_general_food("남은 치킨 데우는 방법은?")

    assert result == {"response_text": "에어프라이어로 데워 드세요."}


def test_inventory_agent_executes_add_only_after_confirmed_action(monkeypatch):
    """재료 추가는 미리보기 단계에서 실행하지 않고 확인 명령에서만 도구를 호출해야 합니다."""
    calls = []

    def fake_add(_db, user_id, name, quantity, storage):
        """실제 저장 대신 호출 인자만 기록합니다."""
        calls.append((user_id, name, quantity, storage))
        return "양파를 추가했어요."

    monkeypatch.setattr(inventory_agent, "is_valid_ingredient", lambda _name: True)
    monkeypatch.setattr(inventory_agent, "resolve_ingredient_name", lambda _db, name: name)
    monkeypatch.setattr(inventory_agent.inventory_service, "add_ingredient_by_name", fake_add)
    db = _FakeDb()

    preview = inventory_agent.run_inventory_agent(
        intent="inventory.action",
        text="냉장고에 양파 1개 냉장에 추가해줘",
        history=[],
        db=db,
        user_id=7,
    )
    confirmed = inventory_agent.run_inventory_agent(
        intent="action.confirm",
        text="확인:add_ingredient:양파:1:냉장",
        history=[],
        db=db,
        user_id=7,
    )

    assert calls == [(7, "양파", 1.0, "냉장")]
    assert preview["actions"][0]["label"] == "확인"
    assert confirmed["response_text"] == "양파를 추가했어요."
