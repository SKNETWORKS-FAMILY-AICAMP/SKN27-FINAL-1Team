from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.backend.api.recipes import recipes_api


def create_client(*, user_id=7):
    app = FastAPI()
    app.include_router(recipes_api.router, prefix="/api/v1")
    app.dependency_overrides[recipes_api.get_current_user] = lambda: user_id
    app.dependency_overrides[recipes_api.get_current_user_required] = lambda: user_id
    app.dependency_overrides[recipes_api.get_db] = lambda: object()
    return TestClient(app)


def recipe_item(**extra):
    data = {
        "recipe_id": 10,
        "title": "tofu salad",
        "category": "side",
        "difficulty": "easy",
        "cooking_time_min": 10,
        "serving_count": 1,
        "main_image_url": None,
    }
    data.update(extra)
    return data


def test_recipe_search_api_normalizes_all_filter(monkeypatch):
    calls = {}

    def fake_search_recipes(**kwargs):
        calls.update(kwargs)
        return {"items": [recipe_item()], "total": 1, "page": kwargs["page"], "page_size": kwargs["page_size"], "has_next": False}

    monkeypatch.setattr(recipes_api.recipe_search_service, "search_recipes", fake_search_recipes)

    response = create_client(user_id=0).get("/api/v1/recipes/search?query=tofu&category=%EC%A0%84%EC%B2%B4")

    assert response.status_code == 200
    assert response.json()["items"][0]["recipe_id"] == 10
    assert calls["query"] == "tofu"
    assert calls["category"] is None


def test_recipe_recommend_api_requires_login_and_returns_result(monkeypatch):
    calls = {}

    def fake_recommend_recipes(db, user_id, config, *, exclude_recipe_ids=None, refresh_pool=False):
        calls["user_id"] = user_id
        calls["mode"] = config.mode
        calls["exclude"] = exclude_recipe_ids
        return {
            "items": [
                {
                    **recipe_item(),
                    "match_rate": 80,
                    "display_match_rate": 80,
                    "owned_ingredient_count": 2,
                    "missing_ingredient_count": 1,
                    "expiry_score": 0,
                    "reason": "enough ingredients",
                }
            ],
            "returned_count": 1,
            "has_more": False,
            "applied_tier": "strict",
            "fallback_used": False,
            "empty_reason": "none",
        }

    monkeypatch.setattr(recipes_api.recommendation_service, "recommend_recipes", fake_recommend_recipes)

    response = create_client().post(
        "/api/v1/recipes/recommend",
        json={"mode": "menu_custom", "limit": 1, "exclude_recipe_ids": [9], "query": "tofu"},
    )

    assert response.status_code == 200
    assert response.json()["items"][0]["missing_ingredient_count"] == 1
    assert calls == {"user_id": 7, "mode": "menu_custom", "exclude": [9]}


def test_recipe_detail_api_uses_guest_user_when_token_missing(monkeypatch):
    calls = {}

    def fake_get_recipe_detail(db, recipe_id, user_id):
        calls["recipe_id"] = recipe_id
        calls["user_id"] = user_id
        return {
            **recipe_item(recipe_id=recipe_id),
            "owned_ingredients": [],
            "maybe_owned_ingredients": [],
            "missing_ingredients": [],
            "match_rate": 0,
            "display_match_rate": 0,
            "steps": [],
            "source_url": None,
        }

    monkeypatch.setattr(recipes_api.recipe_detail_service, "get_recipe_detail", fake_get_recipe_detail)

    response = create_client(user_id=0).get("/api/v1/recipes/10")

    assert response.status_code == 200
    assert calls == {"recipe_id": 10, "user_id": 0}
