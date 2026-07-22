import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwk, jwt
from mcp.server.auth.provider import AccessToken

from app.backend.core.config import settings
from app.backend.core.security import create_access_token, create_refresh_token
from app.backend.mcp.auth import BobbeoriTokenVerifier
from app.backend.mcp.confirmation import PreviewTokenError, issue_preview_token, verify_preview_token
from app.backend.mcp import runtime
from app.backend.mcp.server import mcp, token_verifier


EXPECTED_TOOLS = {
    "inventory.list": "bobbeori-mcp/inventory.read",
    "inventory.expiring": "bobbeori-mcp/inventory.read",
    "recipe.recommend": "bobbeori-mcp/recipe.read",
    "recipe.get": "bobbeori-mcp/recipe.read",
    "ingredient.guide": "bobbeori-mcp/guide.read",
    "receipt.preview": "bobbeori-mcp/receipt.write",
    "receipt.commit": "bobbeori-mcp/receipt.write",
    "shopping.preview": "bobbeori-mcp/shopping.write",
    "shopping.save": "bobbeori-mcp/shopping.write",
    "calendar.preview": "bobbeori-mcp/calendar.write",
    "calendar.create": "bobbeori-mcp/calendar.write",
    "reminder.preview": "bobbeori-mcp/calendar.write",
    "reminder.create": "bobbeori-mcp/calendar.write",
}


def test_public_mcp_tool_contract_has_no_user_id_argument():
    tools = asyncio.run(mcp.list_tools())
    by_name = {tool.name: tool for tool in tools}

    assert set(by_name) == set(EXPECTED_TOOLS)
    for name, scope in EXPECTED_TOOLS.items():
        tool = by_name[name]
        assert "user_id" not in tool.inputSchema.get("properties", {})
        if name not in ("receipt.commit", "shopping.save", "calendar.create", "reminder.create"):
            assert tool.annotations.readOnlyHint is True
        assert tool.meta["securitySchemes"][0]["scopes"] == [scope]
        assert tool.outputSchema["properties"]["trace_id"]

    for name in ("receipt.commit", "shopping.save", "calendar.create", "reminder.create"):
        assert by_name[name].inputSchema["properties"]["confirmed"]["const"] is True
        assert by_name[name].annotations.readOnlyHint is False


def test_dev_token_verifier_uses_token_subject_and_server_scopes():
    access_token = asyncio.run(token_verifier.verify_token(create_access_token("42")))

    assert access_token is not None
    assert access_token.subject == "42"
    assert set(access_token.scopes) == {
        "bobbeori-mcp/inventory.read",
        "bobbeori-mcp/recipe.read",
        "bobbeori-mcp/guide.read",
        "bobbeori-mcp/receipt.write",
        "bobbeori-mcp/shopping.write",
        "bobbeori-mcp/calendar.write",
    }
    assert set(settings.MCP_REQUIRED_SCOPES) == set(access_token.scopes)


def test_dev_token_verifier_rejects_invalid_token():
    assert asyncio.run(token_verifier.verify_token("not-a-jwt")) is None
    refresh_token = create_refresh_token("42")
    assert asyncio.run(token_verifier.verify_token(refresh_token)) is None


def test_preview_token_is_bound_to_action_and_user_and_is_not_an_access_token():
    token, idempotency_key = issue_preview_token("shopping.save", 42, {"ingredients": []})

    payload, decoded_key = verify_preview_token(token, "shopping.save", 42)
    assert payload == {"ingredients": []}
    assert decoded_key == idempotency_key
    with pytest.raises(PreviewTokenError):
        verify_preview_token(token, "receipt.commit", 42)
    with pytest.raises(PreviewTokenError):
        verify_preview_token(token, "shopping.save", 7)
    assert asyncio.run(token_verifier.verify_token(token)) is None


def test_production_token_verifier_checks_jwks_issuer_audience_and_scopes(monkeypatch):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    public_jwk = jwk.construct(public_pem, algorithm="RS256").to_dict()
    public_jwk.update({"kid": "test-key", "alg": "RS256", "use": "sig"})
    config = SimpleNamespace(
        MCP_DEV_TOKEN_AUTH=False,
        MCP_ISSUER_URL="https://cognito-idp.ap-northeast-2.amazonaws.com/ap-northeast-2_test",
        MCP_RESOURCE_URL="https://mcp.example.com/mcp",
        MCP_JWT_AUDIENCE="bobbeori-mcp-client",
        MCP_JWT_ALGORITHMS=["RS256"],
        MCP_JWKS_URL="https://issuer.example/.well-known/jwks.json",
        MCP_JWKS_CACHE_SECONDS=300,
    )
    verifier = BobbeoriTokenVerifier(config)

    async def fake_get_jwks():
        return {"keys": [public_jwk]}

    monkeypatch.setattr(verifier, "_get_jwks", fake_get_jwks)
    now = datetime.now(timezone.utc)
    claims = {
        "iss": config.MCP_ISSUER_URL,
        "aud": config.MCP_JWT_AUDIENCE,
        "sub": "9d70aa32-ff4e-4dd6-9d82-59ddf40f3f8c",
        "scope": "bobbeori-mcp/inventory.read bobbeori-mcp/shopping.write",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
    }
    token = jwt.encode(claims, private_pem, algorithm="RS256", headers={"kid": "test-key"})

    verified = asyncio.run(verifier.verify_token(token))
    assert verified is not None
    assert verified.subject == claims["sub"]
    assert verified.scopes == claims["scope"].split()

    bad_audience = jwt.encode(
        {**claims, "aud": "another-client"},
        private_pem,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )
    bad_issuer = jwt.encode(
        {**claims, "iss": "https://another-issuer.example"},
        private_pem,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )
    assert asyncio.run(verifier.verify_token(bad_audience)) is None
    assert asyncio.run(verifier.verify_token(bad_issuer)) is None


def test_production_runtime_maps_cognito_subject_to_bobbeori_user(monkeypatch):
    token = AccessToken(
        token="access-token",
        client_id="client-id",
        scopes=["bobbeori-mcp/inventory.read"],
        subject="cognito-subject",
        claims={"iss": "https://cognito.example/user-pool"},
    )

    class FakeSession:
        def close(self):
            return None

    monkeypatch.setattr(runtime.settings, "MCP_DEV_TOKEN_AUTH", False)
    monkeypatch.setattr(runtime, "get_access_token", lambda: token)
    monkeypatch.setattr(runtime, "SessionLocal", FakeSession)
    monkeypatch.setattr(runtime, "resolve_or_link_external_user_id", lambda *_args, **_kwargs: 42)

    assert runtime.require_user("inventory:read") == 42


def test_production_runtime_rejects_unlinked_cognito_subject(monkeypatch):
    token = AccessToken(
        token="access-token",
        client_id="client-id",
        scopes=["bobbeori-mcp/inventory.read"],
        subject="unlinked-subject",
        claims={"iss": "https://cognito.example/user-pool"},
    )

    class FakeSession:
        def close(self):
            return None

    monkeypatch.setattr(runtime.settings, "MCP_DEV_TOKEN_AUTH", False)
    monkeypatch.setattr(runtime, "get_access_token", lambda: token)
    monkeypatch.setattr(runtime, "SessionLocal", FakeSession)
    monkeypatch.setattr(runtime, "resolve_or_link_external_user_id", lambda *_args, **_kwargs: None)

    with pytest.raises(PermissionError, match="Link this OAuth account"):
        runtime.require_user("inventory:read")


def test_production_runtime_auto_links_verified_userinfo_email(monkeypatch):
    token = AccessToken(
        token="access-token",
        client_id="client-id",
        scopes=["bobbeori-mcp/inventory.read"],
        subject="cognito-subject",
        claims={"iss": "https://cognito.example/user-pool"},
    )
    calls = []

    class FakeSession:
        def close(self):
            return None

    def fake_resolve_or_link(_db, **kwargs):
        calls.append(kwargs)
        return None if len(calls) == 1 else 42

    monkeypatch.setattr(runtime.settings, "MCP_DEV_TOKEN_AUTH", False)
    monkeypatch.setattr(runtime.settings, "MCP_USERINFO_URL", "https://auth.example/oauth2/userInfo")
    monkeypatch.setattr(runtime, "get_access_token", lambda: token)
    monkeypatch.setattr(runtime, "SessionLocal", FakeSession)
    monkeypatch.setattr(runtime, "resolve_or_link_external_user_id", fake_resolve_or_link)
    monkeypatch.setattr(
        runtime,
        "_fetch_userinfo",
        lambda _token: {"email": "Tester@Example.com", "email_verified": True},
    )

    assert runtime.require_user("inventory:read") == 42
    assert calls[1]["email"] == "tester@example.com"
    assert calls[1]["email_verified"] is True
