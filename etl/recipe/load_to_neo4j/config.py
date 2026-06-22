from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

_ROOT_ENV = Path(__file__).resolve().parents[3] / ".env"
load_dotenv(_ROOT_ENV)


class Neo4jEnv:
    """`.env` 환경변수 키 이름 (루트 .env.sample과 동일)."""

    URI = "NEO4J_URI"
    USER = "NEO4J_USER"
    PASSWORD = "NEO4J_PASSWORD"
    DATABASE = "NEO4J_DATABASE"


DEFAULT_EMBEDDING_MODEL = "qwen3-embedding:0.6b"
CLEAR_DATABASE_QUERY = "MATCH (n) DETACH DELETE n"
TEST_CONNECTION_QUERY = "RETURN 1 AS n"


def require_env(key: str) -> str:
    """`.env`에서 필수 연결 값을 읽는다."""
    value = os.getenv(key)
    if value is None or not str(value).strip():
        raise ValueError(f"환경변수 {key}가 설정되지 않았습니다. 프로젝트 루트 .env를 확인하세요.")
    return str(value).strip()


@dataclass(frozen=True)
class Neo4jSettings:
    uri: str
    user: str
    password: str
    database: str
    embedding_model: str = DEFAULT_EMBEDDING_MODEL


def load_settings() -> Neo4jSettings:
    """`.env` 연결 변수로 Neo4j 설정을 만든다."""
    return Neo4jSettings(
        uri=require_env(Neo4jEnv.URI),
        user=require_env(Neo4jEnv.USER),
        password=require_env(Neo4jEnv.PASSWORD),
        database=require_env(Neo4jEnv.DATABASE),
    )
