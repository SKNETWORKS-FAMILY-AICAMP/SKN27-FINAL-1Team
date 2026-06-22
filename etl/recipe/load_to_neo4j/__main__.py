"""`python -m load_to_neo4j` — Neo4j 연결·싱글톤 테스트."""

from __future__ import annotations

import logging

from .connection import Neo4j_Connection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    """Neo4j 연결 스모크 CLI."""
    conn = Neo4j_Connection()
    logger.info(conn.test_conn())

    conn2 = Neo4j_Connection()
    logger.info("싱글톤 동일 인스턴스: %s", conn is conn2)


if __name__ == "__main__":
    main()
