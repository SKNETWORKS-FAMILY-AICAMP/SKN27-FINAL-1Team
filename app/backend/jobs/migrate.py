from __future__ import annotations

from pathlib import Path

import psycopg2

from app.backend.core.config import settings


SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schemas"


def run_migrations() -> None:
    """Bootstrap a fresh database, then apply each versioned SQL migration once."""
    with psycopg2.connect(settings.DATABASE_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass('public.users')")
            if cursor.fetchone()[0] is None:
                cursor.execute((SCHEMA_DIR / "schema.sql").read_text(encoding="utf-8-sig"))

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    filename VARCHAR(255) PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )

        for migration_path in sorted((SCHEMA_DIR / "migrations").glob("*.sql")):
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT 1 FROM schema_migrations WHERE filename = %s",
                    (migration_path.name,),
                )
                if cursor.fetchone():
                    continue
                cursor.execute(migration_path.read_text(encoding="utf-8-sig"))
                cursor.execute(
                    "INSERT INTO schema_migrations (filename) VALUES (%s)",
                    (migration_path.name,),
                )
            connection.commit()


def main() -> None:
    run_migrations()


if __name__ == "__main__":
    main()
