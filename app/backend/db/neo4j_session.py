from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Generator, Iterator

from neo4j import Driver, GraphDatabase, Session

from app.backend.core.config import settings


class Singleton(type):
    _instances: dict[type, object] = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]


class _Neo4jDriverHolder(metaclass=Singleton):
    """프로세스당 Neo4j Driver 1개 (etl Neo4j_Connection과 동일한 싱글톤 패턴)."""

    def __init__(self) -> None:
        self.driver = GraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        )


def _get_driver() -> Driver:
    return _Neo4jDriverHolder().driver


@contextmanager
def graph_session() -> Iterator[Session]:
    session = _get_driver().session(database=settings.NEO4J_DATABASE)
    try:
        yield session
    finally:
        session.close()


def get_graph_session() -> Generator[Session, Any, None]:
    """FastAPI Depends용 Neo4j 세션 (get_db와 대칭)."""
    session = _get_driver().session(database=settings.NEO4J_DATABASE)
    try:
        yield session
    finally:
        session.close()


if __name__ == "__main__":
    h1, h2 = _Neo4jDriverHolder(), _Neo4jDriverHolder()
    assert h1 is h2
    assert h1.driver is h2.driver
    if settings.NEO4J_PASSWORD:
        with graph_session() as session:
            assert session.run("RETURN 1 AS n").single()["n"] == 1
    print("neo4j_session ok")
