from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.types import ToolAnnotations
from sqlalchemy.orm import Session

from app.backend.db.session import SessionLocal
from app.backend.mcp.contracts import ToolResult
from app.backend.core.config import settings
from app.backend.services.auth_service.external_identity_service import resolve_external_user_id


READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)


def oauth_scope(scope: str) -> str:
    return f"{settings.MCP_SCOPE_PREFIX}/{scope.replace(':', '.')}"


def security(scope: str) -> dict[str, Any]:
    return {"securitySchemes": [{"type": "oauth2", "scopes": [oauth_scope(scope)]}]}


def require_user(scope: str) -> int:
    token = get_access_token()
    if token is None or token.subject is None:
        raise PermissionError("Bobbeori account authentication is required.")
    required_scope = oauth_scope(scope)
    if required_scope not in token.scopes:
        raise PermissionError(f"The access token is missing the {required_scope} scope.")

    if not settings.MCP_DEV_TOKEN_AUTH:
        claims = token.claims or {}
        issuer = str(claims.get("iss") or "")
        with db_session() as db:
            user_id = resolve_external_user_id(db, issuer=issuer, subject=str(token.subject))
        if user_id is None:
            raise PermissionError("Link this OAuth account from Bobbeori before using MCP tools.")
        return user_id

    try:
        user_id = int(token.subject)
    except (TypeError, ValueError) as exc:
        raise PermissionError("The token subject is not a Bobbeori user ID.") from exc
    if user_id <= 0:
        raise PermissionError("The token subject is not a valid Bobbeori user ID.")
    return user_id


@contextmanager
def db_session() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def success(
    data: dict[str, Any],
    *,
    warnings: list[str] | None = None,
    requires_confirmation: bool = False,
    next_actions: list[str] | None = None,
) -> ToolResult:
    return ToolResult(
        success=True,
        data=jsonable_encoder(data),
        warnings=warnings or [],
        requires_confirmation=requires_confirmation,
        next_actions=next_actions or [],
    )


def failure(exc: Exception, *, next_actions: list[str] | None = None) -> ToolResult:
    if isinstance(exc, HTTPException):
        message = str(exc.detail)
    elif isinstance(exc, (LookupError, ValueError)):
        message = str(exc)
    else:
        message = "Bobbeori could not complete the operation. Please try again."
    return ToolResult(
        success=False,
        warnings=[message],
        next_actions=next_actions or [],
    )
