from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.backend.db.models import ExternalIdentity, User
from app.backend.services.auth_service.external_identity_service import (
    resolve_or_link_external_user_id,
)


def _session():
    engine = create_engine("sqlite:///:memory:")
    User.__table__.create(engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE external_identities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id BIGINT NOT NULL,
                    issuer VARCHAR(500) NOT NULL,
                    subject VARCHAR(255) NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    UNIQUE (issuer, subject),
                    UNIQUE (user_id, issuer)
                )
                """
            )
        )
    return sessionmaker(bind=engine)()


def test_resolve_or_link_external_user_id_links_verified_email():
    db = _session()
    db.add(User(id=7, email="Tester@Example.com", nickname="tester", provider="google"))
    db.commit()

    user_id = resolve_or_link_external_user_id(
        db,
        issuer="https://cognito.example/pool/",
        subject="cognito-sub",
        email="tester@example.com",
        email_verified=True,
    )

    assert user_id == 7
    assert db.query(ExternalIdentity).first().user_id == 7


def test_resolve_or_link_external_user_id_ignores_unverified_email():
    db = _session()
    db.add(User(id=7, email="tester@example.com", nickname="tester", provider="google"))
    db.commit()

    user_id = resolve_or_link_external_user_id(
        db,
        issuer="https://cognito.example/pool",
        subject="cognito-sub",
        email="tester@example.com",
        email_verified=False,
    )

    assert user_id is None
    assert db.query(ExternalIdentity).first() is None
