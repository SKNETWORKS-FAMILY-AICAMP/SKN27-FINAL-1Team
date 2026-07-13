from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.backend.api.shopping import shopping_api


def create_client():
    app = FastAPI()
    app.include_router(shopping_api.router, prefix="/api/v1")
    app.dependency_overrides[shopping_api.get_current_user_required] = lambda: 7
    app.dependency_overrides[shopping_api.get_db] = lambda: object()
    return TestClient(app)


def shopping_list_response(**extra):
    data = {
        "id": 11,
        "user_id": 7,
        "recipe_id": 3,
        "recipe_title": "두부 김치찌개",
        "source": "recipe",
        "status": "active",
        "total_price": 5900,
        "checked_count": 1,
        "purchased_count": 0,
        "created_at": None,
        "items": [
            {
                "id": 21,
                "ingredient_id": 31,
                "name": "두부",
                "required_quantity": 1,
                "unit": "모",
                "provider": "naver",
                "product_id": "100",
                "product_name": "국산 두부 1모",
                "product_link": "https://shopping.example/products/100",
                "product_image": "https://shopping.example/products/100.jpg",
                "price": 5900,
                "mall_name": "네이버쇼핑",
                "is_checked": True,
                "is_purchased": False,
                "created_at": None,
            }
        ],
    }
    data.update(extra)
    return data


def test_shopping_openapi_exposes_mcp_callable_contract():
    openapi = create_client().get("/openapi.json").json()

    assert "/api/v1/shopping-list/from-recipe" in openapi["paths"]
    assert "/api/v1/shopping-list/current" in openapi["paths"]
    assert "/api/v1/shopping-list/history" in openapi["paths"]
    assert "/api/v1/shopping-list/purchase" in openapi["paths"]


def test_create_shopping_list_from_recipe_api_returns_product_links(monkeypatch):
    calls = {}

    def fake_create_list(*, db, user_id, recipe_id, source, missing_ingredients):
        calls["user_id"] = user_id
        calls["recipe_id"] = recipe_id
        calls["source"] = source
        calls["missing_names"] = [item.name for item in missing_ingredients]
        return shopping_list_response(recipe_id=recipe_id, source=source)

    monkeypatch.setattr(shopping_api.shopping_service, "create_list", fake_create_list)

    response = create_client().post(
        "/api/v1/shopping-list/from-recipe",
        json={
            "recipe_id": 3,
            "missing_ingredients": [
                {"ingredient_id": 31, "name": "두부", "required_quantity": 1, "unit": "모"}
            ],
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["items"][0]["product_link"] == "https://shopping.example/products/100"
    assert calls == {"user_id": 7, "recipe_id": 3, "source": "recipe", "missing_names": ["두부"]}


def test_current_update_delete_and_purchase_routes_call_service_with_user(monkeypatch):
    calls = {}

    def fake_get_current(*, db, user_id):
        calls["current"] = user_id
        return shopping_list_response()

    def fake_update_item(*, db, user_id, item_id, is_checked, is_purchased):
        calls["update"] = {
            "user_id": user_id,
            "item_id": item_id,
            "is_checked": is_checked,
            "is_purchased": is_purchased,
        }
        return shopping_list_response()

    def fake_delete_item(*, db, user_id, item_id):
        calls["delete"] = {"user_id": user_id, "item_id": item_id}
        return shopping_list_response(items=[])

    def fake_complete_purchase(*, db, user_id, shopping_list_id, item_ids):
        calls["purchase"] = {"user_id": user_id, "shopping_list_id": shopping_list_id, "item_ids": item_ids}
        purchased = shopping_list_response(status="completed", purchased_count=1)
        purchased["items"][0]["is_purchased"] = True
        return {"message": "1개 재료가 냉장고에 입고되었습니다.", "stocked_count": 1, "shopping_list": purchased}

    monkeypatch.setattr(shopping_api.shopping_service, "get_current", fake_get_current)
    monkeypatch.setattr(shopping_api.shopping_service, "update_item", fake_update_item)
    monkeypatch.setattr(shopping_api.shopping_service, "delete_item", fake_delete_item)
    monkeypatch.setattr(shopping_api.shopping_service, "complete_purchase", fake_complete_purchase)
    client = create_client()

    current = client.get("/api/v1/shopping-list/current")
    updated = client.patch("/api/v1/shopping-list/items/21", json={"is_checked": False})
    deleted = client.delete("/api/v1/shopping-list/items/21")
    purchased = client.post("/api/v1/shopping-list/purchase", json={"shopping_list_id": 11, "item_ids": [21]})

    assert current.status_code == 200
    assert updated.status_code == 200
    assert deleted.status_code == 200
    assert purchased.status_code == 200
    assert purchased.json()["stocked_count"] == 1
    assert calls == {
        "current": 7,
        "update": {"user_id": 7, "item_id": 21, "is_checked": False, "is_purchased": None},
        "delete": {"user_id": 7, "item_id": 21},
        "purchase": {"user_id": 7, "shopping_list_id": 11, "item_ids": [21]},
    }


def test_history_and_delete_list_routes_call_service_with_user(monkeypatch):
    calls = {}

    def fake_get_history(*, db, user_id, limit):
        calls["history"] = {"user_id": user_id, "limit": limit}
        return [shopping_list_response(id=11), shopping_list_response(id=10, status="completed")]

    def fake_delete_list(*, db, user_id, shopping_list_id):
        calls["delete_list"] = {"user_id": user_id, "shopping_list_id": shopping_list_id}

    monkeypatch.setattr(shopping_api.shopping_service, "get_history", fake_get_history)
    monkeypatch.setattr(shopping_api.shopping_service, "delete_list", fake_delete_list)
    client = create_client()

    history = client.get("/api/v1/shopping-list/history?limit=5")
    deleted = client.delete("/api/v1/shopping-list/11")

    assert history.status_code == 200
    assert deleted.status_code == 200
    assert history.json()["shopping_lists"][1]["status"] == "completed"
    assert deleted.json()["message"] == "장보기 목록을 삭제했어요."
    assert calls == {
        "history": {"user_id": 7, "limit": 5},
        "delete_list": {"user_id": 7, "shopping_list_id": 11},
    }


def test_compare_api_returns_provider_product_candidates(monkeypatch):
    def fake_compare_products(missing_ingredients):
        assert missing_ingredients == ["두부", "대파"]
        return {
            "total_price": 7900,
            "delivery_saving": 0,
            "recommended_market": "네이버 쇼핑",
            "market_prices": [
                {
                    "name": "두부",
                    "coupang": None,
                    "kurly": None,
                    "best_market": "네이버쇼핑",
                    "provider": "naver",
                    "product_id": "100",
                    "product_name": "국산 두부 1모",
                    "product_link": "https://shopping.example/products/100",
                    "product_image": "https://shopping.example/products/100.jpg",
                    "price": 5900,
                    "mall_name": "네이버쇼핑",
                }
            ],
        }

    monkeypatch.setattr(shopping_api.shopping_service, "compare_products", fake_compare_products)

    response = create_client().post(
        "/api/v1/shopping-list/compare",
        json={"missing_ingredients": ["두부", "대파"]},
    )

    assert response.status_code == 200
    assert response.json()["market_prices"][0]["product_link"] == "https://shopping.example/products/100"
    assert response.json()["market_prices"][0]["product_image"] == "https://shopping.example/products/100.jpg"
