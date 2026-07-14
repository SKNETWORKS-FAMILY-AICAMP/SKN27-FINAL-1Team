from ai.agents.shopping_agent.shopping_agent import run_shopping_agent
from ai.agents.shopping_agent.shopping_utils import analyze_shopping_intent
import ai.agents.shopping_agent.shopping_handlers as shopping_handlers


def shopping_list_response(**extra):
    data = {
        "id": 11,
        "total_price": 3900,
        "checked_count": 1,
        "items": [
            {
                "id": 21,
                "name": "두부",
                "required_quantity": 1,
                "unit": "모",
                "price": 3900,
                "is_checked": True,
                "is_purchased": False,
            }
        ],
        "owned_ingredients": [{"ingredient_id": 31, "name": "대파", "amount": "2대"}],
    }
    data.update(extra)
    return data


def test_analyze_shopping_intent_routes_clear_shopping_context():
    assert analyze_shopping_intent("장보기 목록 보여줘") == "shopping.current"
    assert analyze_shopping_intent("두부랑 양파 가격 비교해줘") == "shopping.compare"
    assert analyze_shopping_intent("두부랑 양파 장보기 목록 만들어줘") == "shopping.create"
    assert analyze_shopping_intent("최근 장보기 목록에서 내가 보유한 재료 목록은 뭐가 있어?") == "shopping.owned"
    assert analyze_shopping_intent("두부 구매했어") is None


def test_run_shopping_agent_current_returns_supervisor_contract(monkeypatch):
    monkeypatch.setattr(
        shopping_handlers.shopping_service,
        "get_current",
        lambda *, db, user_id: shopping_list_response(),
    )

    result = run_shopping_agent(
        "장보기 목록 보여줘",
        db=object(),
        user_id=7,
        intent="shopping.current",
    )

    assert set(result) == {"response_text", "actions", "sources"}
    assert "두부" in result["response_text"]
    assert result["actions"][0]["url"] == "/shopping-list?shoppingListId=11"


def test_run_shopping_agent_owned_returns_owned_ingredients(monkeypatch):
    monkeypatch.setattr(
        shopping_handlers.shopping_service,
        "get_current",
        lambda *, db, user_id: shopping_list_response(),
    )

    result = run_shopping_agent(
        "최근 장보기 목록에서 내가 보유한 재료 목록은 뭐가 있어?",
        db=object(),
        user_id=7,
        intent="shopping.owned",
    )

    assert "보유한 재료" in result["response_text"]
    assert "대파 2대" in result["response_text"]
    assert "두부" not in result["response_text"]
    assert result["actions"][0]["url"] == "/shopping-list?shoppingListId=11"


def test_run_shopping_agent_create_uses_confirmation_first():
    result = run_shopping_agent(
        "두부랑 양파 장보기 목록 만들어줘",
        db=object(),
        user_id=7,
        intent="shopping.create",
    )

    assert "만들까요" in result["response_text"]
    assert result["actions"][0]["data"]["message"] == "확인:shopping_create:두부|양파"


def test_run_shopping_agent_confirm_create_calls_service(monkeypatch):
    calls = {}

    def fake_create_list(*, db, user_id, recipe_id, source, missing_ingredients):
        calls["user_id"] = user_id
        calls["source"] = source
        calls["names"] = [item.name for item in missing_ingredients]
        return shopping_list_response()

    monkeypatch.setattr(shopping_handlers.shopping_service, "create_list", fake_create_list)

    result = run_shopping_agent(
        "확인:shopping_create:두부|양파",
        db=object(),
        user_id=7,
        intent="action.confirm",
    )

    assert "두부" in result["response_text"]
    assert calls == {"user_id": 7, "source": "manual", "names": ["두부", "양파"]}
