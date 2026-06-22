"""`python -m load_to_postgres` — DB 연결·샘플 쿼리 테스트."""

from __future__ import annotations

import logging

from .connection import PostgreDB

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    """DB 연결 스모크 CLI.
    """
    db = PostgreDB()
    logger.info(db.test_conn())


if __name__ == "__main__":
    main()
