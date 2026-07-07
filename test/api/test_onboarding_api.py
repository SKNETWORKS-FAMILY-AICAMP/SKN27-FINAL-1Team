from datetime import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.backend.api.onboarding import onboarding_api


def create_client():
    app = FastAPI()
    app.include_router(onboarding_api.router, prefix="/api/v1")
    app.dependency_overrides[onboarding_api.get_current_user_required] = lambda: 7
    app.dependency_overrides[onboarding_api.get_db] = lambda: object()
    return TestClient(app)


def onboarding_response(**extra):
    data = {
        "id": 1,
        "user_id": 7,
        "disliked_ingredients": ["cilantro"],
        "allergy": ["peanut"],
        "preferred_ingredients": ["tofu"],
        "is_alert_allowed": True,
        "updated_at": datetime(2026, 7, 7, 9, 0, 0),
    }
    data.update(extra)
    return data


def test_onboarding_get_and_save_api_use_current_user(monkeypatch):
    calls = {}

    def fake_get_onboarding(*, db, user_id):
        calls["get"] = user_id
        return onboarding_response()

    def fake_save_onboarding(*, db, user_id, data):
        calls["save"] = {"user_id": user_id, "alert": data.is_alert_allowed}
        return onboarding_response(is_alert_allowed=data.is_alert_allowed)

    monkeypatch.setattr(onboarding_api.onboarding_service, "get_onboarding", fake_get_onboarding)
    monkeypatch.setattr(onboarding_api.onboarding_service, "save_onboarding", fake_save_onboarding)
    client = create_client()

    loaded = client.get("/api/v1/onboarding")
    saved = client.post("/api/v1/onboarding", json={"is_alert_allowed": False, "preferred_ingredients": ["tofu"]})

    assert loaded.status_code == 200
    assert saved.status_code == 201
    assert loaded.json()["user_id"] == 7
    assert saved.json()["is_alert_allowed"] is False
    assert calls == {"get": 7, "save": {"user_id": 7, "alert": False}}
