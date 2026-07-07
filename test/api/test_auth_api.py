from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.backend.api.auth import auth_api


class FakeQuery:
    def __init__(self, row):
        self.row = row

    def filter(self, *_):
        return self

    def first(self):
        return self.row


class FakeDb:
    def __init__(self, row=None):
        self.row = row

    def query(self, *_):
        return FakeQuery(self.row)


def create_client(*, db=None, user_id=None):
    app = FastAPI()
    app.include_router(auth_api.router, prefix="/api/v1")
    app.dependency_overrides[auth_api.get_db] = lambda: db or FakeDb()
    if user_id is not None:
        app.dependency_overrides[auth_api.get_current_user_required] = lambda: user_id
    return TestClient(app)


def test_auth_me_requires_token():
    client = create_client()

    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401


def test_auth_me_returns_current_user():
    user = SimpleNamespace(
        id=7,
        email="tester@example.com",
        provider="kakao",
        nickname="tester",
        created_at=datetime.now(timezone.utc),
        is_onboarded=False,
    )
    client = create_client(db=FakeDb(user), user_id=user.id)

    response = client.get("/api/v1/auth/me")

    assert response.status_code == 200
    assert response.json()["id"] == 7
    assert response.json()["email"] == "tester@example.com"


def test_dev_login_issues_bearer_token(monkeypatch):
    calls = {}

    def fake_authenticate_social_user(**kwargs):
        calls.update(kwargs)
        return "dev.jwt.token"

    monkeypatch.setattr(auth_api.auth_service, "authenticate_social_user", fake_authenticate_social_user)
    client = create_client()

    response = client.post("/api/v1/auth/dev-login")

    assert response.status_code == 200
    assert response.json() == {"access_token": "dev.jwt.token", "token_type": "bearer"}
    assert calls["provider"] == "kakao"
    assert calls["provider_id"] == "dev_cheat_id_9999"


def test_social_login_uses_oauth_profile_and_issues_token(monkeypatch):
    calls = {}

    async def fake_google_user(code, redirect_uri):
        calls["code"] = code
        calls["redirect_uri"] = redirect_uri
        return {"provider_id": "google-7", "email": "g@example.com", "nickname": "google user"}

    def fake_authenticate_social_user(**kwargs):
        calls["auth"] = kwargs
        return "google.jwt.token"

    monkeypatch.setattr(auth_api.oauth_client, "get_google_user", fake_google_user)
    monkeypatch.setattr(auth_api.auth_service, "authenticate_social_user", fake_authenticate_social_user)
    client = create_client()

    response = client.post(
        "/api/v1/auth/social-login",
        json={"provider": "google", "code": "oauth-code", "redirect_uri": "http://localhost/callback"},
    )

    assert response.status_code == 200
    assert response.json()["access_token"] == "google.jwt.token"
    assert calls["code"] == "oauth-code"
    assert calls["auth"]["provider"] == "google"
    assert calls["auth"]["provider_id"] == "google-7"
