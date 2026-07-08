"""Nutrition CSV -> PostgreSQL loader."""

from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path

import psycopg


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CSV = ROOT / "storage" / "processed" / "nutrition" / "food_nutrition_facts.csv"
DEFAULT_SCHEMA = ROOT / "app" / "backend" / "schemas" / "migrations" / "20260708_create_food_nutrition_facts.sql"
COLUMNS = (
    "food_code",
    "food_name",
    "representative_name",
    "major_category",
    "middle_category",
    "minor_category",
    "base_amount",
    "energy_kcal",
    "carbohydrate_g",
    "protein_g",
    "fat_g",
    "sugar_g",
    "sodium_mg",
    "source_name",
    "source_ref",
    "reference_year",
    "source_priority",
)
NUMERIC_COLUMNS = {"energy_kcal", "carbohydrate_g", "protein_g", "fat_g", "sugar_g", "sodium_mg"}
INTEGER_COLUMNS = {"source_priority"}


def dsn() -> str:
    return (
        f"host={os.getenv('DB_HOST', 'localhost')} "
        f"port={os.getenv('DB_PORT', '5432')} "
        f"dbname={os.getenv('DB_NAME', 'bobbeori_db')} "
        f"user={os.getenv('DB_USER', 'bobbeori_user')} "
        f"password={os.getenv('DB_PASSWORD', '')}"
    )


def clean(row: dict[str, str]) -> tuple[object, ...]:
    values = []
    for column in COLUMNS:
        value = (row.get(column) or "").strip()
        if value == "":
            values.append(None)
        elif column in INTEGER_COLUMNS:
            values.append(int(value))
        elif column in NUMERIC_COLUMNS:
            values.append(float(value.replace(",", "")))
        else:
            values.append(value)
    return tuple(values)


def load(csv_path: Path, schema_path: Path, *, clear: bool) -> int:
    count = 0
    with psycopg.connect(dsn()) as conn:
        with conn.cursor() as cur:
            cur.execute(schema_path.read_text(encoding="utf-8"))
            if clear:
                cur.execute("TRUNCATE TABLE food_nutrition_facts RESTART IDENTITY")
            with cur.copy(f"COPY food_nutrition_facts ({', '.join(COLUMNS)}) FROM STDIN") as copy:
                for row in csv.DictReader(csv_path.open(encoding="utf-8-sig")):
                    copy.write_row(clean(row))
                    count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="영양성분 CSV를 PostgreSQL에 적재합니다.")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--append", action="store_true", help="기존 데이터를 지우지 않고 추가 적재")
    args = parser.parse_args()

    count = load(args.csv, args.schema, clear=not args.append)
    print(f"loaded {count} nutrition rows")


if __name__ == "__main__":
    main()
