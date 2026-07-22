from __future__ import annotations

import time
from typing import Any

import httpx
from jose import JWTError, jwt
from mcp.server.auth.provider import AccessToken, TokenVerifier

from app.backend.core.config import Settings


class BobbeoriTokenVerifier(TokenVerifier):
    """Validate either local app JWTs or production OAuth access tokens."""

    def __init__(self, config: Settings) -> None:
        self.config = config
        self._jwks: dict[str, Any] | None = None
        self._jwks_expires_at = 0.0

    async def verify_token(self, token: str) -> AccessToken | None:
        if self.config.MCP_DEV_TOKEN_AUTH:
            return self._verify_dev_token(token)
        return await self._verify_oauth_token(token)

    def _verify_dev_token(self, token: str) -> AccessToken | None:
        try:
            payload = jwt.decode(
                token,
                self.config.JWT_SECRET_KEY,
                algorithms=[self.config.JWT_ALGORITHM],
            )
        except JWTError:
            return None
        if payload.get("type") not in (None, "access"):
            return None
        subject = payload.get("sub")
        if subject is None:
            return None
        return AccessToken(
            token=token,
            client_id="bobbeori-local-dev",
            scopes=self.config.MCP_SUPPORTED_SCOPES,
            resource=self.resource_url,
            subject=str(subject),
        )

    async def _verify_oauth_token(self, token: str) -> AccessToken | None:
        try:
            header = jwt.get_unverified_header(token)
            algorithm = header.get("alg")
            if algorithm not in self.config.MCP_JWT_ALGORITHMS:
                return None

            jwk = await self._find_jwk(header.get("kid"))
            if jwk is None:
                return None

            payload = None
            for audience in _audience_candidates(self.audience):
                try:
                    payload = jwt.decode(
                        token,
                        jwk,
                        algorithms=self.config.MCP_JWT_ALGORITHMS,
                        audience=audience,
                        issuer=self.issuer_url,
                    )
                    break
                except JWTError:
                    continue
            if payload is None:
                return None
        except (JWTError, httpx.HTTPError, KeyError, TypeError, ValueError):
            return None

        subject = payload.get("sub")
        if subject is None:
            return None

        return AccessToken(
            token=token,
            client_id=str(payload.get("azp") or payload.get("client_id") or "unknown"),
            scopes=_parse_scopes(payload),
            expires_at=_optional_int(payload.get("exp")),
            resource=self.audience,
            subject=str(subject),
            claims=payload,
        )

    async def _find_jwk(self, key_id: str | None) -> dict[str, Any] | None:
        jwks = await self._get_jwks()
        keys = jwks.get("keys", [])
        if key_id is None and len(keys) == 1:
            return keys[0]
        return next((key for key in keys if key.get("kid") == key_id), None)

    async def _get_jwks(self) -> dict[str, Any]:
        if self._jwks is not None and time.monotonic() < self._jwks_expires_at:
            return self._jwks

        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(self.config.MCP_JWKS_URL)
            response.raise_for_status()
            self._jwks = response.json()
        self._jwks_expires_at = time.monotonic() + self.config.MCP_JWKS_CACHE_SECONDS
        return self._jwks

    @property
    def issuer_url(self) -> str:
        return self.config.MCP_ISSUER_URL or "http://localhost:8000"

    @property
    def resource_url(self) -> str:
        return self.config.MCP_RESOURCE_URL or "http://localhost:8001/mcp"

    @property
    def audience(self) -> str:
        return self.config.MCP_JWT_AUDIENCE or self.resource_url


def validate_mcp_auth_config(config: Settings) -> None:
    if config.MCP_DEV_TOKEN_AUTH:
        if not config.MCP_PREVIEW_TOKEN_SECRET:
            raise RuntimeError("MCP_PREVIEW_TOKEN_SECRET or JWT_SECRET_KEY is required")
        return

    missing = [
        name
        for name, value in (
            ("MCP_ISSUER_URL", config.MCP_ISSUER_URL),
            ("MCP_RESOURCE_URL", config.MCP_RESOURCE_URL),
            ("MCP_JWKS_URL", config.MCP_JWKS_URL),
            ("MCP_PREVIEW_TOKEN_SECRET", config.MCP_PREVIEW_TOKEN_SECRET),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(
            "Production MCP authentication is not configured: " + ", ".join(missing)
        )
    if len(config.MCP_PREVIEW_TOKEN_SECRET) < 32:
        raise RuntimeError("MCP_PREVIEW_TOKEN_SECRET must be at least 32 characters in production")


def _parse_scopes(payload: dict[str, Any]) -> list[str]:
    raw_scopes = payload.get("scope", payload.get("scp", []))
    if isinstance(raw_scopes, str):
        return [scope for scope in raw_scopes.split() if scope]
    if isinstance(raw_scopes, list):
        return [str(scope) for scope in raw_scopes]
    return []


def _audience_candidates(audience: str) -> list[str]:
    stripped = audience.rstrip("/")
    return list(dict.fromkeys(value for value in (audience, stripped, f"{stripped}/") if value))


def _optional_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
