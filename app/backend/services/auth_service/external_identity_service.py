from sqlalchemy import func
from sqlalchemy.orm import Session

from app.backend.db.models import ExternalIdentity, User


class ExternalIdentityConflictError(ValueError):
    pass


def normalize_issuer(value: str) -> str:
    issuer = value.strip().rstrip("/")
    if not issuer or len(issuer) > 500:
        raise ValueError("The OAuth token issuer is invalid.")
    return issuer


def resolve_external_user_id(db: Session, *, issuer: str, subject: str) -> int | None:
    identity = (
        db.query(ExternalIdentity)
        .filter(
            ExternalIdentity.issuer == normalize_issuer(issuer),
            ExternalIdentity.subject == subject,
        )
        .first()
    )
    return int(identity.user_id) if identity else None


def resolve_or_link_external_user_id(
    db: Session,
    *,
    issuer: str,
    subject: str,
    email: str | None = None,
    email_verified: bool | str | None = None,
) -> int | None:
    user_id = resolve_external_user_id(db, issuer=issuer, subject=subject)
    if user_id is not None or not email or not _is_truthy(email_verified):
        return user_id

    # 동일 이메일의 소셜 계정이 여러 개면 자동 선택하지 않고 명시적 MCP 연결을 요구합니다.
    users = db.query(User).filter(func.lower(User.email) == email.strip().lower()).limit(2).all()
    if len(users) != 1:
        return None
    user = users[0]

    try:
        return int(link_external_identity(db, user_id=int(user.id), issuer=issuer, subject=subject).user_id)
    except ExternalIdentityConflictError:
        return None


def link_external_identity(db: Session, *, user_id: int, issuer: str, subject: str) -> ExternalIdentity:
    normalized_issuer = normalize_issuer(issuer)
    normalized_subject = subject.strip()
    if not normalized_subject or len(normalized_subject) > 255:
        raise ValueError("The OAuth token subject is invalid.")

    by_subject = (
        db.query(ExternalIdentity)
        .filter(
            ExternalIdentity.issuer == normalized_issuer,
            ExternalIdentity.subject == normalized_subject,
        )
        .first()
    )
    if by_subject:
        if int(by_subject.user_id) != user_id:
            raise ExternalIdentityConflictError("This OAuth account is linked to another Bobbeori user.")
        return by_subject

    by_user = (
        db.query(ExternalIdentity)
        .filter(
            ExternalIdentity.user_id == user_id,
            ExternalIdentity.issuer == normalized_issuer,
        )
        .first()
    )
    if by_user:
        raise ExternalIdentityConflictError("This Bobbeori user already linked another OAuth account.")

    identity = ExternalIdentity(user_id=user_id, issuer=normalized_issuer, subject=normalized_subject)
    db.add(identity)
    db.commit()
    db.refresh(identity)
    return identity


def _is_truthy(value: bool | str | None) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return False
