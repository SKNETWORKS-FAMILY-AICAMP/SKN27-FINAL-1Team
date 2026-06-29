from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from neo4j import GraphDatabase

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Neo4jSettings:
    uri: str
    user: str
    password: str
    database: str


def require_env(key: str) -> str:
    value = os.getenv(key)
    if value is None or not value.strip():
        raise ValueError(f"Required environment variable is missing: {key}")
    return value.strip()


def load_settings() -> Neo4jSettings:
    return Neo4jSettings(
        uri=require_env("NEO4J_URI"),
        user=require_env("NEO4J_USER"),
        password=require_env("NEO4J_PASSWORD"),
        database=os.getenv("NEO4J_DATABASE", "neo4j").strip() or "neo4j",
    )


#####################################################################################
# 싱글톤 패턴
#####################################################################################


class Singleton(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


#####################################################################################
# 싱글톤 클래스 상속받아서 neo4j 연결 객체 생성
#####################################################################################


class Neo4j_Connection(metaclass=Singleton):
    """
    Neo4j DB 연결 객체 생성 및 관련 내장 클래스 정의
    - 클래스는 싱글톤으로 구성
    - 객체에는 공통으로 사용하는 변수와 매서드만 우선적으로 내장한다. (close, 초기화 등...)
    """

    def __init__(
        self,
        uri,
        user,
        password,
        embedding_model="qwen3-embedding:0.6b",
        database: str | None = None,
    ):
        self._uri = uri
        self._user = user
        self._password = password
        self._database = database or os.getenv("NEO4J_DATABASE", "neo4j").strip() or "neo4j"
        self._embedding_model = embedding_model
        self._gds: Any | None = None
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        logger.info("Neo4j 연결 성공: %s", uri)
        logger.info("임베딩 모델: %s", embedding_model)

    @property
    def gds(self):
        if self._gds is None:
            from graphdatascience import GraphDataScience

            self._gds = GraphDataScience(self._uri, auth=(self._user, self._password))
        return self._gds

    def _ensure_driver(self):
        if self.driver is None:
            self.driver = GraphDatabase.driver(self._uri, auth=(self._user, self._password))
        return self.driver

    def close(self):
        """해당 메소드 실행해서 리소스를 놓아주기 위함"""
        if self.driver is not None:
            self.driver.close()
            self.driver = None
        self._gds = None
        logger.info("Neo4j 드라이버 연결 해제 완료")

    def execute_write(self, query: str, parameters: dict[str, Any] | None = None) -> None:
        with self._ensure_driver().session(database=self._database) as session:
            session.run(query, parameters or {}).consume()

    def execute_query(self, query: str = "", parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """session.run을 래핑해서 dict 리스트 형태로 결과를 반환"""
        with self._ensure_driver().session(database=self._database) as session:
            result = session.run(query, parameters or {})
            return [dict(record) for record in result]

    def execute_single(self, query: str, parameters: dict[str, Any] | None = None) -> dict[str, Any] | None:
        with self._ensure_driver().session(database=self._database) as session:
            record = session.run(query, parameters or {}).single()
            return dict(record) if record else None

    def clear_database(self):
        """Neo4j의 모든 노드와 관계를 삭제"""
        self.execute_write("MATCH (n) DETACH DELETE n")
        logger.info("=== 기존 데이터 삭제 완료! ===")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(filename)s %(message)s")
    logger.info("=== Neo4j 연결 테스트 ===")

    settings = load_settings()
    conn1 = Neo4j_Connection(
        uri=settings.uri,
        user=settings.user,
        password=settings.password,
        embedding_model=os.getenv("NEO4J_EMBEDDING_MODEL", "qwen3-embedding:0.6b"),
        database=settings.database,
    )
    conn2 = Neo4j_Connection(
        uri=settings.uri,
        user=settings.user,
        password=settings.password,
        embedding_model=os.getenv("NEO4J_EMBEDDING_MODEL", "qwen3-embedding:0.6b"),
        database=settings.database,
    )

    logger.info("첫 번째 연결: %s", conn1)
    logger.info("두 번째 연결: %s", conn2)

    try:
        if conn1 is conn2:
            logger.info("같은 연결인가? %s", conn1 is conn2)
            logger.info("싱글톤 패턴 적용 완료: 동일한 연결을 재사용합니다.")
        rows = conn1.execute_query("RETURN 1 AS test")
        logger.info("쿼리 smoke: %s", rows)
    except Exception as e:
        logger.error("Neo4j 연결 실패: %s", e)
        raise
