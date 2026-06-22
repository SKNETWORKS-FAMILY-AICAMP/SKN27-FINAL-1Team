"""Neo4j 연결 싱글톤."""

from __future__ import annotations
import logging
from graphdatascience import GraphDataScience
from neo4j import GraphDatabase

from .config import CLEAR_DATABASE_QUERY, TEST_CONNECTION_QUERY, load_settings

logger = logging.getLogger(__name__)

#################################################################
# 싱글톤 클래스 (나중에 파일들 정리되면 공통 부분 묶을 예정)
#################################################################
class Singleton(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]

#################################################################
# Neo4j 연결 
#################################################################
class Neo4j_Connection(metaclass=Singleton):
    """Neo4j DB 연결 객체 (싱글톤)."""

    def __init__(self) -> None:
        settings = load_settings()
        self.settings = settings
        self.driver = GraphDatabase.driver(
            settings.uri,
            auth=(settings.user, settings.password),
        )
        self.gds = GraphDataScience(settings.uri, auth=(settings.user, settings.password))
        # from langchain_ollama import OllamaEmbeddings
        # self.embedding_model = OllamaEmbeddings(model=settings.embedding_model)
        logger.info("Neo4j 연결 성공: %s", settings.uri)

    def close(self) -> None:
        """드라이버 연결을 해제한다."""
        self.driver.close()
        logger.info("Neo4j 드라이버 연결 해제 완료")

    def execute_query(self, query: str = "", parameters: dict | None = None) -> list:
        """session.run을 래핑해 결과를 리스트로 반환한다."""
        with self.driver.session(database=self.settings.database) as session:
            result = session.run(query, parameters)
            return [record for record in result]

    def clear_database(self) -> None:
        """Neo4j의 모든 노드와 관계를 삭제한다."""
        with self.driver.session(database=self.settings.database) as session:
            session.run(CLEAR_DATABASE_QUERY)
        logger.info("=== 기존 데이터 삭제 완료! ===")

    def test_conn(self) -> str:
        """`RETURN 1`로 연결을 확인하고 결과 문자열을 반환한다."""
        try:
            self.execute_query(TEST_CONNECTION_QUERY)
            return "Connection successful"
        except Exception as e:
            return f"Connection failed: {e}"
