import pytest
from fastapi.testclient import TestClient

from app.backend.main import app


client = TestClient(app)


@pytest.mark.parametrize(
    ("method", "path", "kwargs"),
    [
        ("GET", "/api/v1/inventory", {}),
        ("GET", "/api/v1/inventory/summary", {}),
        ("GET", "/api/v1/inventory/predict?name=tofu", {}),
        ("GET", "/api/v1/inventory/suggestions?q=tofu", {}),
        ("POST", "/api/v1/inventory", {"json": {"name": "tofu", "quantity": 1, "unit": "pack"}}),
        ("PUT", "/api/v1/inventory/1", {"json": {"name": "tofu", "quantity": 1, "unit": "pack"}}),
        ("DELETE", "/api/v1/inventory/1", {}),
        ("DELETE", "/api/v1/inventory/bulk", {"json": {"ingredient_ids": [1, 2]}}),
        ("GET", "/api/v1/notifications", {}),
        ("PUT", "/api/v1/notifications/1/read", {}),
        ("POST", "/api/v1/notifications/device-token", {"json": {"device_token": "token"}}),
        ("GET", "/api/v1/onboarding", {}),
        ("POST", "/api/v1/onboarding", {"json": {"is_alert_allowed": True}}),
        ("POST", "/api/v1/recipes/recommend", {"json": {"mode": "fridge_consume"}}),
        ("GET", "/api/v1/recommendations", {}),
        ("POST", "/api/v1/recommendations", {"json": {"recipe_id": 1, "recommendation_type": "manual_save"}}),
        ("DELETE", "/api/v1/recommendations/1", {}),
        ("POST", "/api/v1/shopping-list/compare", {"json": {"missing_ingredients": ["tofu"]}}),
        ("POST", "/api/v1/shopping-list/purchase", {"json": {"purchased_items": [{"name": "tofu"}]}}),
        ("GET", "/api/v1/calendar/google/status", {}),
        ("GET", "/api/v1/calendar/google/events?start_date=2026-07-07&end_date=2026-07-08", {}),
        ("POST", "/api/v1/calendar/google/connect", {"json": {"code": "oauth-code"}}),
        ("POST", "/api/v1/calendar/google/test-event", {}),
        ("DELETE", "/api/v1/calendar/google/disconnect", {}),
        ("POST", "/api/v1/guide/suggestions", {"json": {"ingredient_code": "TOFU", "guide_type": "storage", "content": "Keep tofu cold."}}),
    ],
)
def test_api_requires_login_matrix(method, path, kwargs):
    response = client.request(method, path, **kwargs)

    assert response.status_code == 401
