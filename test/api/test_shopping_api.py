from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.backend.api.shopping import shopping_api


def create_client():
    app = FastAPI()
    app.include_router(shopping_api.router, prefix="/api/v1")
    app.dependency_overrides[shopping_api.get_current_user_required] = lambda: 7
    return TestClient(app)


def test_shopping_compare_api_returns_market_contract():
    response = create_client().post(
        "/api/v1/shopping-list/compare",
        json={"missing_ingredients": ["tofu", "egg"]},
    )

    assert response.status_code == 200
    assert response.json()["total_price"] == 6000
    assert [item["name"] for item in response.json()["market_prices"]] == ["tofu", "egg"]


def test_shopping_purchase_api_returns_message_contract():
    response = create_client().post(
        "/api/v1/shopping-list/purchase",
        json={"purchased_items": [{"name": "tofu", "quantity": 1, "market": "coupang"}]},
    )

    assert response.status_code == 200
    assert response.json()["message"]
