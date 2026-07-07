from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.backend.api.notifications import notifications_api


def create_client(*, user_id=None):
    app = FastAPI()
    app.include_router(notifications_api.router, prefix="/api/v1")
    if user_id is not None:
        app.dependency_overrides[notifications_api.get_current_user_required] = lambda: user_id
    return TestClient(app)


def test_notifications_require_login():
    client = create_client()

    response = client.get("/api/v1/notifications")

    assert response.status_code == 401


def test_notifications_list_returns_item_contract():
    client = create_client(user_id=7)

    response = client.get("/api/v1/notifications")

    assert response.status_code == 200
    item = response.json()[0]
    assert {"id", "type", "title", "message", "is_read", "created_at"} <= set(item)
    assert item["is_read"] is False


def test_notification_mutations_return_message_contract():
    client = create_client(user_id=7)

    read_response = client.put("/api/v1/notifications/1/read")
    token_response = client.post("/api/v1/notifications/device-token", json={"device_token": "fcm-token"})

    assert read_response.status_code == 200
    assert token_response.status_code == 200
    assert read_response.json()["message"]
    assert token_response.json()["message"]
