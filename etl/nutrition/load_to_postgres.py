"""Nutrition CSV -> PostgreSQL loader."""

from __future__ import annotations

import argparse
import csv
import io
import os
from pathlib import Path

try:
    import psycopg
except ModuleNotFoundError:
    psycopg = None
    import psycopg2


SCRIPT_PATH = Path(__file__).resolve()
ROOT = SCRIPT_PATH.parents[2] if len(SCRIPT_PATH.parents) > 2 else Path.cwd()
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
    "service_major_category",
    "service_middle_category",
    "service_minor_category",
    "service_match_status",
    "service_match_basis",
    "service_ingredient_id",
    "representative_nutrition_score",
    "is_representative_nutrition",
    "representative_nutrition_reason",
)
CSV_COLUMNS = {
    "food_code": "식품코드",
    "food_name": "식품명",
    "representative_name": "대표식품명_또는_원재료명",
    "major_category": "대분류",
    "middle_category": "중분류",
    "minor_category": "소분류",
    "base_amount": "기준량",
    "energy_kcal": "열량(kcal)",
    "carbohydrate_g": "탄수화물(g)",
    "protein_g": "단백질(g)",
    "fat_g": "지방(g)",
    "sugar_g": "당류(g)",
    "sodium_mg": "나트륨(mg)",
    "source_name": "출처명",
    "source_ref": "출처URL_또는_데이터셋명",
    "reference_year": "기준년도",
    "source_priority": "식품유형코드",
    "service_major_category": "서비스_대분류",
    "service_middle_category": "서비스_중분류",
    "service_minor_category": "서비스_소분류",
    "service_match_status": "서비스_매칭상태",
    "service_match_basis": "서비스_매칭기준",
    "service_ingredient_id": "서비스_원재료ID",
    "representative_nutrition_score": "대표영양점수",
    "is_representative_nutrition": "대표영양여부",
    "representative_nutrition_reason": "대표영양선정사유",
}
SOURCE_PRIORITY = {"R": 1, "F": 2, "P": 3}
NUMERIC_COLUMNS = {"energy_kcal", "carbohydrate_g", "protein_g", "fat_g", "sugar_g", "sodium_mg"}
INTEGER_COLUMNS = {"source_priority", "representative_nutrition_score"}
BOOLEAN_COLUMNS = {"is_representative_nutrition"}


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
        value = (row.get(CSV_COLUMNS[column]) or row.get(column) or "").strip()
        if value == "":
            values.append(None)
        elif column == "source_priority":
            values.append(SOURCE_PRIORITY.get(value, int(value) if value.isdigit() else 9))
        elif column in BOOLEAN_COLUMNS:
            values.append(value.lower() in {"true", "1", "y", "yes", "예"})
        elif column in INTEGER_COLUMNS:
            values.append(int(value))
        elif column in NUMERIC_COLUMNS:
            values.append(float(value.replace(",", "")))
        else:
            values.append(value)
    return tuple(values)


def load(csv_path: Path, schema_path: Path, *, clear: bool) -> int:
    if psycopg is None:
        return load_psycopg2(csv_path, schema_path, clear=clear)

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


def load_psycopg2(csv_path: Path, schema_path: Path, *, clear: bool) -> int:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    count = 0
    for row in csv.DictReader(csv_path.open(encoding="utf-8-sig")):
        writer.writerow(clean(row))
        count += 1
    buffer.seek(0)

    with psycopg2.connect(dsn()) as conn:
        with conn.cursor() as cur:
            cur.execute(schema_path.read_text(encoding="utf-8"))
            if clear:
                cur.execute("TRUNCATE TABLE food_nutrition_facts RESTART IDENTITY")
            cur.copy_expert(f"COPY food_nutrition_facts ({', '.join(COLUMNS)}) FROM STDIN WITH CSV", buffer)
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
