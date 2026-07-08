from datetime import date, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.backend.api.inventory import inventory_api


def create_client():
    app = FastAPI()
    app.include_router(inventory_api.router, prefix="/api/v1")
    app.dependency_overrides[inventory_api.get_current_user_required] = lambda: 7
    app.dependency_overrides[inventory_api.get_db] = lambda: object()
    return TestClient(app)


def ingredient_response(**extra):
    data = {
        "id": 1,
        "fridge_id": 2,
        "name": "tofu",
        "category": "bean",
        "quantity": 1,
        "unit": "pack",
        "storage_method": "cold",
        "purchase_date": date(2026, 7, 7),
        "expiration_date": date(2026, 7, 10),
        "created_at": datetime(2026, 7, 7, 9, 0, 0),
        "updated_at": None,
        "d_day": 3,
        "is_expiring_soon": True,
        "is_expired": False,
        "status": "expiring",
        "is_ai_recommended": False,
    }
    data.update(extra)
    return data


def test_inventory_predict_api_returns_ai_contract(monkeypatch):
    def fake_predict(name):
        assert name == "tofu"
        return {"is_valid_food": True, "storage_method": "cold", "lifespan_days": 3}

    monkeypatch.setattr(inventory_api.expiration_ai_service, "predict_ingredient_info", fake_predict)

    response = create_client().get("/api/v1/inventory/predict?name=tofu")

    assert response.status_code == 200
    assert response.json() == {"is_valid_food": True, "storage_method": "cold", "lifespan_days": 3}


def test_inventory_create_and_list_api_use_current_user(monkeypatch):
    calls = {}

    def fake_add_ingredient(*, db, user_id, data):
        calls["add"] = {"user_id": user_id, "name": data.name}
        return ingredient_response(name=data.name)

    def fake_get_ingredients(*, db, user_id):
        calls["list"] = {"user_id": user_id}
        return [ingredient_response()]

    monkeypatch.setattr(inventory_api.inventory_service, "add_ingredient", fake_add_ingredient)
    monkeypatch.setattr(inventory_api.inventory_service, "get_ingredients", fake_get_ingredients)
    client = create_client()

    created = client.post("/api/v1/inventory", json={"name": "tofu", "quantity": 2, "unit": "pack"})
    listed = client.get("/api/v1/inventory")

    assert created.status_code == 201
    assert listed.status_code == 200
    assert created.json()["name"] == "tofu"
    assert listed.json()[0]["id"] == 1
    assert calls == {"add": {"user_id": 7, "name": "tofu"}, "list": {"user_id": 7}}


def test_inventory_bulk_delete_api_accepts_body(monkeypatch):
    deleted = {}

    def fake_delete_bulk(*, db, user_id, ingredient_ids):
        deleted["user_id"] = user_id
        deleted["ids"] = ingredient_ids

    monkeypatch.setattr(inventory_api.inventory_service, "delete_ingredients_bulk", fake_delete_bulk)

    response = create_client().request("DELETE", "/api/v1/inventory/bulk", json={"ingredient_ids": [1, 2]})

    assert response.status_code == 204
    assert deleted == {"user_id": 7, "ids": [1, 2]}
