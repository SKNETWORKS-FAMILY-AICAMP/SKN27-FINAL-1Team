from ai.agents.shopping_agent.shopping_agent import run_shopping_agent
from ai.agents.shopping_agent.shopping_utils import analyze_shopping_intent
import ai.agents.shopping_agent.shopping_handlers as shopping_handlers


def shopping_list_response(**extra):
    data = {
        "id": 11,
        "recipe_id": 3,
        "recipe_title": "두부 김치찌개",
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
    items = [
        {
            "id": index,
            "name": f"재료{index}",
            "required_quantity": 1,
            "unit": "개",
            "price": index * 1000,
            "is_checked": True,
            "is_purchased": False,
        }
        for index in range(1, 8)
    ]
    monkeypatch.setattr(
        shopping_handlers.shopping_service,
        "get_current",
        lambda *, db, user_id: shopping_list_response(items=items, total_price=28000),
    )

    result = run_shopping_agent(
        "장보기 목록 보여줘",
        db=object(),
        user_id=7,
        intent="shopping.current",
    )

    assert set(result) == {"response_text", "actions", "sources", "slots"}
    assert "7. 재료7" in result["response_text"]
    assert "외" not in result["response_text"]
    assert result["actions"][0]["url"] == "/shopping-list?shoppingListId=11"
    assert result["slots"]["shopping_next_offset"] == 7
    assert result["slots"]["shopping_has_more"] is False


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


def test_run_shopping_agent_owned_uses_slot_shopping_list(monkeypatch):
    calls = {}

    def fake_get_list(*, db, user_id, shopping_list_id):
        calls["shopping_list_id"] = shopping_list_id
        return shopping_list_response(id=77, recipe_title="야채찜", owned_ingredients=[{"name": "양파", "amount": "1개"}])

    monkeypatch.setattr(shopping_handlers.shopping_service, "get_list", fake_get_list)

    result = run_shopping_agent(
        "보유재료는?",
        db=object(),
        user_id=7,
        intent="shopping.owned",
        slots={"shopping_list_id": 77, "shopping_recipe_title": "야채찜"},
    )

    assert calls == {"shopping_list_id": 77}
    assert "양파 1개" in result["response_text"]


def test_run_shopping_agent_recipe_title_creates_recipe_list(monkeypatch):
    calls = {}

    monkeypatch.setattr(shopping_handlers.shopping_service, "get_history", lambda *, db, user_id, limit: [])
    monkeypatch.setattr(
        shopping_handlers.recipe_search_service,
        "search_recipes",
        lambda **kwargs: {"items": [{"recipe_id": 9, "title": "야채찜"}]},
    )
    monkeypatch.setattr(
        shopping_handlers.recipe_detail_service,
        "get_recipe_detail",
        lambda db, recipe_id, user_id: {
            "recipe_id": recipe_id,
            "title": "야채찜",
            "missing_ingredients": [
                {"ingredient_id": 101, "name": "브로콜리", "amount": "1개"},
                {"ingredient_id": 102, "name": "당근", "amount": "1개"},
            ],
        },
    )

    def fake_create_list(*, db, user_id, recipe_id, source, missing_ingredients):
        calls["recipe_id"] = recipe_id
        calls["source"] = source
        calls["names"] = [item.name for item in missing_ingredients]
        return shopping_list_response(
            id=88,
            recipe_id=recipe_id,
            recipe_title="야채찜",
            items=[
                {"id": 1, "name": "브로콜리", "price": 3000, "is_purchased": False},
                {"id": 2, "name": "당근", "price": 2000, "is_purchased": False},
            ],
            total_price=5000,
        )

    monkeypatch.setattr(shopping_handlers.shopping_service, "create_list", fake_create_list)

    result = run_shopping_agent(
        "야채찜의 장보기 목록",
        db=object(),
        user_id=7,
        intent="shopping.current",
    )

    assert "야채찜 장보기 목록" in result["response_text"]
    assert "브로콜리" in result["response_text"]
    assert "새우" not in result["response_text"]
    assert calls == {"recipe_id": 9, "source": "recipe", "names": ["브로콜리", "당근"]}
    assert result["actions"][0]["url"] == "/shopping-list?shoppingListId=88"
    assert result["slots"]["shopping_recipe_title"] == "야채찜"


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


def test_run_shopping_agent_remaining_uses_previous_offset(monkeypatch):
    items = [
        {"id": index, "name": f"재료{index}", "price": index * 1000, "is_purchased": False}
        for index in range(1, 18)
    ]
    monkeypatch.setattr(
        shopping_handlers.shopping_service,
        "get_current",
        lambda *, db, user_id: shopping_list_response(items=items, total_price=28000),
    )

    result = run_shopping_agent(
        "나머지 2개는?",
        db=object(),
        user_id=7,
        intent="shopping.current",
        slots={"shopping_next_offset": 15, "shopping_total_count": 17, "shopping_has_more": True},
    )

    assert "16. 재료16" in result["response_text"]
    assert "17. 재료17" in result["response_text"]
    assert "1. 재료1" not in result["response_text"]
    assert result["slots"]["shopping_next_offset"] == 17
    assert result["slots"]["shopping_has_more"] is False
