from unittest.mock import MagicMock

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.backend.db.models import ExternalIdentity, User
from app.backend.services.auth_service.auth_service import auth_service
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

def test_resolve_or_link_external_user_id_rejects_duplicate_email():
    """동일 이메일 사용자가 여러 명이면 Cognito 계정을 자동 연결하지 않습니다."""
    db = _session()
    db.add_all(
        [
            User(id=7, email="tester@example.com", nickname="kakao", provider="kakao", provider_id="kakao-7"),
            User(id=8, email="tester@example.com", nickname="google", provider="google", provider_id="google-8"),
        ]
    )
    db.commit()

    user_id = resolve_or_link_external_user_id(
        db,
        issuer="https://cognito.example/pool",
        subject="cognito-sub",
        email="tester@example.com",
        email_verified=True,
    )

    assert user_id is None
    assert db.query(ExternalIdentity).first() is None

def test_social_accounts_with_same_email_remain_independent(monkeypatch):
    """동일 이메일이어도 제공자 계정이 다르면 별도 사용자로 가입합니다."""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    users = []

    # 테스트 DB가 신규 사용자 ID를 발급한 것처럼 최소 동작만 재현합니다.
    def assign_user_id(user):
        user.id = len(users) + 1
        users.append(user)

    db.add.side_effect = assign_user_id
    monkeypatch.setattr(
        "app.backend.services.auth_service.auth_service.create_access_token",
        lambda subject: subject,
    )

    kakao_user_id = auth_service.authenticate_social_user(
        db,
        provider="kakao",
        provider_id="kakao-7",
        email="tester@example.com",
        nickname="kakao",
    )
    google_user_id = auth_service.authenticate_social_user(
        db,
        provider="google",
        provider_id="google-8",
        email="tester@example.com",
        nickname="google",
    )

    assert kakao_user_id != google_user_id
    assert [user.provider for user in users] == ["kakao", "google"]
    assert all(user.email == "tester@example.com" for user in users)
