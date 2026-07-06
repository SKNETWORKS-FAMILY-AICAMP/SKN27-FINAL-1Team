import os
import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.main import app
from app.backend.api.deps import get_current_user_required

client = TestClient(app)

# 인증 의존성 Mocking
@pytest.fixture(autouse=True)
def mock_auth():
    app.dependency_overrides[get_current_user_required] = lambda: 1
    yield
    app.dependency_overrides = {}

@patch("app.backend.api.inventory.inventory_api.inventory_service")
def test_get_inventory_summary(mock_service):
    # 실제 스키마: total, expiring_soon, expired, today_added, storage
    mock_service.get_inventory_summary.return_value = {
        "total": 5,
        "expiring_soon": 2,
        "expired": 0,
        "today_added": 1,
        "storage": {"냉장": 3, "냉동": 2, "실온": 0, "기타": 0}
    }

    response = client.get("/api/v1/inventory/summary")
    
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 5
    assert data["expiring_soon"] == 2
    assert data["storage"]["냉장"] == 3

@patch("app.backend.api.inventory.inventory_api.inventory_service")
def test_add_ingredient(mock_service):
    mock_service.add_ingredient.return_value = {"id": 100, "name": "당근", "status": "stored", "quantity": 1.0, "unit": "개", "storage_method": "냉장", "purchase_date": "2026-06-26", "created_at": "2026-06-26T00:00:00Z", "fridge_id": 1, "receipt_item_id": None, "category": "채소", "expiration_date": "2026-07-03", "updated_at": None, "d_day": 3, "is_expiring_soon": True, "is_expired": False, "is_ai_recommended": False}

    # 실제 스키마에 맞춰 float 타입 및 storage_method 필드명 사용
    payload = {
        "name": "당근",
        "category": "채소",
        "storage_method": "냉장",
        "quantity": 1.0,
        "unit": "개"
    }
    
    response = client.post("/api/v1/inventory", json=payload)
    
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "당근"

@patch("app.backend.api.inventory.inventory_api.inventory_service")
def test_update_ingredient(mock_service):
    mock_service.update_ingredient.return_value = {"id": 100, "name": "당근(수정)", "status": "stored", "quantity": 2.0, "unit": "개", "storage_method": "냉장", "purchase_date": "2026-06-26", "created_at": "2026-06-26T00:00:00Z", "fridge_id": 1, "receipt_item_id": None, "category": "채소", "expiration_date": "2026-07-03", "updated_at": None, "d_day": 3, "is_expiring_soon": True, "is_expired": False, "is_ai_recommended": False}

    payload = {
        "name": "당근(수정)",
        "category": "채소",
        "storage_method": "냉장",
        "quantity": 2.0,
        "unit": "개"
    }
    
    ingredient_id = 100
    response = client.put(f"/api/v1/inventory/{ingredient_id}", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "당근(수정)"

@patch("app.backend.api.inventory.inventory_api.inventory_service")
def test_delete_ingredient(mock_service):
    mock_service.delete_ingredient.return_value = None

    ingredient_id = 100
    response = client.delete(f"/api/v1/inventory/{ingredient_id}")
    
    assert response.status_code == 204

@patch("app.backend.api.inventory.inventory_api.inventory_service")
def test_delete_ingredients_bulk(mock_service):
    mock_service.delete_ingredients_bulk.return_value = None

    payload = {
        "ingredient_ids": [100, 101, 102]
    }
    
    # httpx TestClient는 delete 요청 시 json 인자를 받지 않을 수 있으므로 request() 사용
    response = client.request("DELETE", "/api/v1/inventory/bulk", json=payload)
    
    assert response.status_code == 204
