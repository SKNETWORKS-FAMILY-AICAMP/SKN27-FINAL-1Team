from fastapi.testclient import TestClient

from app.backend.api.chat import chat_api
from app.backend.main import app


client = TestClient(app)


def test_chat_api_returns_legacy_chat_contract(monkeypatch):
    def fake_handle_message(**kwargs):
        assert kwargs["user_id"] == 0
        assert kwargs["message"] == "냉장고에 뭐 있어?"
        return {
            "intent": "inventory.list",
            "reply": "냉장고 재료를 조회했어요.",
            "actions": [{"label": "냉장고 보기", "url": "/fridge", "data": {"tab": "list"}}],
            "sources": [],
        }

    monkeypatch.setattr(chat_api.supervisor_service, "handle_message", fake_handle_message)

    response = client.post(
        "/api/v1/chat",
        json={
            "message": "냉장고에 뭐 있어?",
            "history": [],
            "settings": {
                "shortAnswer": False,
                "fridgeFirst": True,
                "expiringFirst": True,
                "excludeDislikes": True,
            },
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "intent": "inventory.list",
        "reply": "냉장고 재료를 조회했어요.",
        "actions": [{"label": "냉장고 보기", "url": "/fridge", "data": {"tab": "list"}}],
        "sources": [],
    }
