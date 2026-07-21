from sqlalchemy.orm import Session

from app.backend.db.models import ExternalIdentity


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
