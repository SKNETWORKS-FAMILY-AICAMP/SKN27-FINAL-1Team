from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

_ROOT_ENV = Path(__file__).resolve().parents[3] / ".env"
load_dotenv(_ROOT_ENV)


class DbEnv:
    """`.env` 환경변수 키 이름 (백엔드·docker-compose와 동일)."""

    ENGINE = "DB_ENGINE"
    USER = "DB_USER"
    PASSWORD = "DB_PASSWORD"
    HOST = "DB_HOST"
    PORT = "DB_PORT"
    NAME = "DB_NAME"


def require_env(key: str) -> str:
    """`.env`에서 필수 연결 값을 읽는다."""
    value = os.getenv(key)
    if value is None or not str(value).strip():
        raise ValueError(f"환경변수 {key}가 설정되지 않았습니다. 프로젝트 루트 .env를 확인하세요.")
    return str(value).strip()


def build_dsn() -> str:
    """`.env` 연결 변수로 PostgreSQL URI 문자열을 만든다."""
    user = require_env(DbEnv.USER)
    password = require_env(DbEnv.PASSWORD)
    host = require_env(DbEnv.HOST)
    port = require_env(DbEnv.PORT)
    database = require_env(DbEnv.NAME)
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"
