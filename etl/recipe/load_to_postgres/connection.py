"""PostgreSQL 연결 싱글톤."""

from __future__ import annotations
import logging
import time
import psycopg

from .config import build_dsn

logger = logging.getLogger(__name__)


#################################################################
# 싱글톤 클래스 
#################################################################
class Singleton(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]



#################################################################
# PostgreSQL 연결 
#################################################################
class PostgreDB(metaclass=Singleton):
    """PostgreSQL 싱글톤 연결·쿼리 실행."""

    def __init__(self) -> None:
        last_error = None
        for _ in range(20):
            try:
                self.conn = psycopg.connect(build_dsn(), autocommit=True)
                return
            except psycopg.OperationalError as exc:
                last_error = exc
                time.sleep(1)
        if last_error is not None:
            raise last_error
        raise RuntimeError("PostgreSQL connection failed")

    def get_conn(self):
        """연결된 psycopg 커넥션을 반환한다."""
        return self.conn

    def run_query(self, query: str, **params):
        """이름 기반 파라미터(`%(name)s`) 쿼리를 실행하고 fetchall한다. """

        with self.conn.cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchall()


    def run_query_lst(self, query: str, args: tuple | list | None = None) -> list:
        """위치 기반 파라미터(`%s`) 쿼리를 실행하고 fetchall한다."""
        with self.conn.cursor() as cursor:
            cursor.execute(query, args or ())
            return cursor.fetchall()

    def execute(self, query: str, params: dict | None = None) -> None:
        """이름 기반 파라미터 쿼리를 실행한다."""
        with self.conn.cursor() as cursor:
            cursor.execute(query, params or {})

    def executemany(self, query: str, params_seq: list[dict]) -> None:
        """이름 기반 파라미터 쿼리를 여러 건 실행한다."""
        if not params_seq:
            return
        with self.conn.cursor() as cursor:
            cursor.executemany(query, params_seq)

    def fetch_one(self, query: str, params: dict | None = None):
        """이름 기반 파라미터 쿼리를 실행하고 fetchone 한다."""
        with self.conn.cursor() as cursor:
            cursor.execute(query, params or {})
            return cursor.fetchone()

    def test_conn(self) -> str:
        """`SELECT 1`로 연결을 확인하고 결과 문자열을 반환한다. """
        
        try:
            self.run_query("SELECT 1")
            return "Connection successful"
        except Exception as e:
            return f"Connection failed: {e}"
