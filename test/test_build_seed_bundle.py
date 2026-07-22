from decimal import Decimal
from io import StringIO
import csv

import pytest

from scripts import build_seed_bundle


def test_recipe_code_maps_to_numeric_recipe_id():
    assert build_seed_bundle._recipe_id("R0001") == 1
    assert build_seed_bundle._recipe_id("R0175") == 175
    with pytest.raises(ValueError):
        build_seed_bundle._recipe_id("recipe-1")


def test_amount_parser_strips_parenthetical_annotations():
    assert build_seed_bundle._parse_amount("1개(180g)") == (Decimal("1"), "개")
    assert build_seed_bundle._parse_amount("1/2큰술") == (Decimal("0.5"), "큰술")
    assert build_seed_bundle._parse_amount("약간") == (None, "약간")
    assert build_seed_bundle._parse_amount("2큰술 또는 1큰술") == (Decimal("2"), "큰술")


def test_nutrition_csv_maps_korean_headers_to_db_columns():
    source = StringIO()
    writer = csv.DictWriter(source, fieldnames=list(build_seed_bundle.NUTRITION_COLUMN_MAP.values()))
    writer.writeheader()
    writer.writerow(
        {
            "식품코드": "F001",
            "식품명": "두부",
            "대표식품명_또는_원재료명": "두부",
            "대분류": "대분류",
            "중분류": "중분류",
            "소분류": "소분류",
            "기준량": "100g",
            "열량(kcal)": "80",
            "탄수화물(g)": "1",
            "단백질(g)": "9",
            "지방(g)": "4",
            "당류(g)": "0.5",
            "나트륨(mg)": "2,026",
            "출처명": "식약처",
            "출처URL_또는_데이터셋명": "url",
            "기준년도": "2026",
            "서비스_대분류": "대",
            "서비스_중분류": "중",
            "서비스_소분류": "소",
            "서비스_매칭상태": "matched",
            "서비스_매칭기준": "name",
            "서비스_원재료ID": "ingredient_1",
            "대표영양점수": "99",
            "대표영양여부": "대표",
            "대표영양선정사유": "reason",
        }
    )

    output, count = build_seed_bundle._build_food_nutrition_facts_csv(source.getvalue())
    row = next(csv.DictReader(output.splitlines()))

    assert count == 1
    assert row["food_code"] == "F001"
    assert row["food_name"] == "두부"
    assert row["sodium_mg"] == "2026"
    assert row["is_representative_nutrition"] == "true"
