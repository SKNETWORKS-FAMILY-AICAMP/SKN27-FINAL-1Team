from datetime import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.backend.api.guide import guide_api


def create_client(*, user_id=7):
    app = FastAPI()
    app.include_router(guide_api.router, prefix="/api/v1")
    app.dependency_overrides[guide_api.get_current_user] = lambda: user_id
    app.dependency_overrides[guide_api.get_current_user_required] = lambda: user_id
    app.dependency_overrides[guide_api.get_db] = lambda: object()
    return TestClient(app)


def test_guide_search_api_passes_filters_to_service(monkeypatch):
    calls = {}

    def fake_search_guides(**kwargs):
        calls.update(kwargs)
        return {
            "items": [{"code": "TOFU", "name": "tofu"}],
            "total": 1,
            "returned_count": 1,
            "page": kwargs["page"],
            "page_size": kwargs["page_size"],
            "has_next": False,
        }

    monkeypatch.setattr(guide_api.guide_service, "search_guides", fake_search_guides)

    response = create_client(user_id=0).get("/api/v1/guide?keyword=tofu&page=2&page_size=10")

    assert response.status_code == 200
    assert response.json()["items"][0]["code"] == "TOFU"
    assert calls["keyword"] == "tofu"
    assert calls["page"] == 2
    assert calls["page_size"] == 10


def test_guide_detail_api_returns_404_when_missing(monkeypatch):
    monkeypatch.setattr(guide_api.guide_service, "get_guide_detail", lambda code: None)

    response = create_client(user_id=0).get("/api/v1/guide/detail/NOPE")

    assert response.status_code == 404


def test_guide_suggestion_api_maps_user_and_response(monkeypatch):
    saved = {}

    def fake_create_suggestion(*, db, user_id, data):
        saved["user_id"] = user_id
        saved["code"] = data.ingredient_code
        return {
            "id": 3,
            "ingredient_code": data.ingredient_code,
            "ingredient_name": "tofu",
            "guide_type": data.guide_type,
            "content": data.content,
            "source_name": data.source_name,
            "source_url": None,
            "status": "pending",
            "created_at": datetime(2026, 7, 7, 9, 0, 0),
        }

    monkeypatch.setattr(guide_api.guide_service, "create_suggestion", fake_create_suggestion)

    response = create_client().post(
        "/api/v1/guide/suggestions",
        json={
            "ingredient_code": "TOFU",
            "guide_type": "storage",
            "content": "Keep tofu sealed in cold water.",
            "source_name": "team",
        },
    )

    assert response.status_code == 201
    assert response.json()["status"] == "pending"
    assert saved == {"user_id": 7, "code": "TOFU"}
