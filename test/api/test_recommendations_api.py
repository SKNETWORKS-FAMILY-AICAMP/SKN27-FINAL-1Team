from datetime import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.backend.api.recommendations import recommendations_api


def create_client():
    app = FastAPI()
    app.include_router(recommendations_api.router, prefix="/api/v1")
    app.dependency_overrides[recommendations_api.get_current_user_required] = lambda: 7
    app.dependency_overrides[recommendations_api.get_db] = lambda: object()
    return TestClient(app)


def saved_recipe(**extra):
    data = {
        "recommendation_id": 1,
        "recipe_id": 10,
        "title": "tofu salad",
        "description": None,
        "category": "side",
        "cooking_time_min": 10,
        "difficulty": "easy",
        "image_url": None,
        "recommendation_type": "manual_save",
        "created_at": datetime(2026, 7, 7, 9, 0, 0),
    }
    data.update(extra)
    return data


def test_recommendations_list_and_save_api_use_current_user(monkeypatch):
    calls = {}

    def fake_list_user_recipes(db, user_id):
        calls["list_user_id"] = user_id
        return [saved_recipe()]

    def fake_save_recipe(db, user_id, recipe_id, recommendation_type):
        calls["save"] = (user_id, recipe_id, recommendation_type)
        return saved_recipe(recipe_id=recipe_id)

    monkeypatch.setattr(recommendations_api.recommendation_service, "list_user_recipes", fake_list_user_recipes)
    monkeypatch.setattr(recommendations_api.recommendation_service, "save_recipe", fake_save_recipe)
    client = create_client()

    listed = client.get("/api/v1/recommendations")
    saved = client.post("/api/v1/recommendations", json={"recipe_id": 11, "recommendation_type": "manual_save"})

    assert listed.status_code == 200
    assert saved.status_code == 201
    assert listed.json()[0]["title"] == "tofu salad"
    assert saved.json()["recipe_id"] == 11
    assert calls == {"list_user_id": 7, "save": (7, 11, "manual_save")}


def test_recommendations_delete_api_returns_204(monkeypatch):
    deleted = {}

    def fake_delete_user_recipe(db, user_id, recommendation_id):
        deleted["user_id"] = user_id
        deleted["recommendation_id"] = recommendation_id

    monkeypatch.setattr(recommendations_api.recommendation_service, "delete_user_recipe", fake_delete_user_recipe)

    response = create_client().delete("/api/v1/recommendations/1")

    assert response.status_code == 204
    assert deleted == {"user_id": 7, "recommendation_id": 1}
