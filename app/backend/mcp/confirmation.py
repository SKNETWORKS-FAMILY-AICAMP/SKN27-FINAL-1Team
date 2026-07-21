from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from jose import JWTError, jwt
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.backend.core.config import settings
from app.backend.db.models import McpMutation


class PreviewTokenError(ValueError):
    pass


def issue_preview_token(action: str, user_id: int, payload: dict[str, Any]) -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    idempotency_key = uuid4().hex
    token = jwt.encode(
        {
            "type": "mcp_preview",
            "sub": str(user_id),
            "action": action,
            "payload": payload,
            "jti": idempotency_key,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=settings.MCP_PREVIEW_TTL_SECONDS)).timestamp()),
        },
        settings.MCP_PREVIEW_TOKEN_SECRET,
        algorithm="HS256",
    )
    return token, idempotency_key


def verify_preview_token(token: str, action: str, user_id: int) -> tuple[dict[str, Any], str]:
    try:
        claims = jwt.decode(token, settings.MCP_PREVIEW_TOKEN_SECRET, algorithms=["HS256"])
    except JWTError as exc:
        raise PreviewTokenError("The preview token is invalid or expired. Run preview again.") from exc

    if claims.get("type") != "mcp_preview":
        raise PreviewTokenError("The confirmation token is not a Bobbeori preview token.")
    if claims.get("action") != action:
        raise PreviewTokenError(f"This preview token cannot be used for {action}.")
    if claims.get("sub") != str(user_id):
        raise PreviewTokenError("This preview belongs to another Bobbeori account.")
    payload = claims.get("payload")
    idempotency_key = claims.get("jti")
    if not isinstance(payload, dict) or not isinstance(idempotency_key, str):
        raise PreviewTokenError("The preview token payload is incomplete. Run preview again.")
    return payload, idempotency_key


def claim_mutation(
    db: Session,
    *,
    user_id: int,
    action: str,
    idempotency_key: str,
) -> tuple[McpMutation, dict[str, Any] | None]:
    existing = _find_mutation(db, user_id, action, idempotency_key)
    if existing:
        return _reuse_or_retry(db, existing)

    mutation = McpMutation(
        user_id=user_id,
        action=action,
        idempotency_key=idempotency_key,
        status="in_progress",
    )
    try:
        db.add(mutation)
        db.commit()
        db.refresh(mutation)
        return mutation, None
    except IntegrityError:
        db.rollback()
        existing = _find_mutation(db, user_id, action, idempotency_key)
        if existing is None:
            raise
        return _reuse_or_retry(db, existing)


def complete_mutation(db: Session, mutation_id: int, result: dict[str, Any]) -> None:
    mutation = db.query(McpMutation).filter(McpMutation.id == mutation_id).one()
    mutation.status = "completed"
    mutation.result_json = result
    mutation.updated_at = datetime.now(timezone.utc)
    db.commit()


def fail_mutation(db: Session, mutation_id: int, exc: Exception) -> None:
    db.rollback()
    mutation = db.query(McpMutation).filter(McpMutation.id == mutation_id).one_or_none()
    if mutation is None:
        return
    mutation.status = "failed"
    mutation.result_json = {"error": str(exc)[:500]}
    mutation.updated_at = datetime.now(timezone.utc)
    db.commit()


def _find_mutation(db: Session, user_id: int, action: str, idempotency_key: str) -> McpMutation | None:
    return (
        db.query(McpMutation)
        .filter(
            McpMutation.user_id == user_id,
            McpMutation.action == action,
            McpMutation.idempotency_key == idempotency_key,
        )
        .first()
    )


def _reuse_or_retry(db: Session, mutation: McpMutation) -> tuple[McpMutation, dict[str, Any] | None]:
    if mutation.status == "completed":
        return mutation, dict(mutation.result_json or {})
    if mutation.status == "in_progress" and not _is_stale(mutation.updated_at):
        raise PreviewTokenError("This confirmed action is already running. Retry shortly.")

    # ponytail: failed or stale work retries in place; add a durable job queue if writes become long-running.
    mutation.status = "in_progress"
    mutation.result_json = None
    mutation.updated_at = datetime.now(timezone.utc)
    db.commit()
    return mutation, None


def _is_stale(updated_at: datetime | None) -> bool:
    if updated_at is None:
        return True
    aware = updated_at if updated_at.tzinfo else updated_at.replace(tzinfo=timezone.utc)
    return aware < datetime.now(timezone.utc) - timedelta(minutes=5)
