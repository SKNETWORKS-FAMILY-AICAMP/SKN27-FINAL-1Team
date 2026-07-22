from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
from collections import OrderedDict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from io import StringIO
from pathlib import Path
from typing import Any


RECIPE_SOURCE_PATH = "storage/processed/recipe/recipe_175.csv"
FOOD_GUIDE_SOURCE_DIR = "storage/processed/food_guide"
NUTRITION_SOURCE_DIR = "storage/processed/nutrition"

FOOD_GUIDE_FILES = (
    "nodes_alias.csv",
    "nodes_guide.csv",
    "nodes_ingredient.csv",
    "nodes_major_category.csv",
    "nodes_middle_category.csv",
    "nodes_nutrition.csv",
    "nodes_season_month.csv",
    "nodes_source.csv",
    "non_ingredient_like_food_candidates.csv",
    "rel_guide_sourced_from.csv",
    "rel_ingredient_has_alias.csv",
    "rel_ingredient_has_guide.csv",
    "rel_ingredient_has_nutrition.csv",
    "rel_ingredient_in_season.csv",
    "rel_major_has_middle.csv",
    "rel_middle_has_ingredient.csv",
    "rel_nutrition_sourced_from.csv",
)

NUTRITION_FILES = (
    "food_nutrition_facts.csv",
    "nutrition_aliases.csv",
)

NUTRITION_COLUMN_MAP = OrderedDict(
    [
        ("food_code", "식품코드"),
        ("food_name", "식품명"),
        ("representative_name", "대표식품명_또는_원재료명"),
        ("major_category", "대분류"),
        ("middle_category", "중분류"),
        ("minor_category", "소분류"),
        ("base_amount", "기준량"),
        ("energy_kcal", "열량(kcal)"),
        ("carbohydrate_g", "탄수화물(g)"),
        ("protein_g", "단백질(g)"),
        ("fat_g", "지방(g)"),
        ("sugar_g", "당류(g)"),
        ("sodium_mg", "나트륨(mg)"),
        ("source_name", "출처명"),
        ("source_ref", "출처URL_또는_데이터셋명"),
        ("reference_year", "기준년도"),
        ("service_major_category", "서비스_대분류"),
        ("service_middle_category", "서비스_중분류"),
        ("service_minor_category", "서비스_소분류"),
        ("service_match_status", "서비스_매칭상태"),
        ("service_match_basis", "서비스_매칭기준"),
        ("service_ingredient_id", "서비스_원재료ID"),
        ("representative_nutrition_score", "대표영양점수"),
        ("is_representative_nutrition", "대표영양여부"),
        ("representative_nutrition_reason", "대표영양선정사유"),
    ]
)
NUTRITION_NUMERIC_COLUMNS = {
    "energy_kcal",
    "carbohydrate_g",
    "protein_g",
    "fat_g",
    "sugar_g",
    "sodium_mg",
    "representative_nutrition_score",
}


@dataclass(frozen=True)
class SeedStats:
    recipes: int
    recipe_ingredients: int
    recipe_seed_ingredients: int
    nutrition_facts: int
    food_guide_files: int


def build_seed_bundle(
    *,
    output_dir: Path,
    source_rev: str,
) -> SeedStats:
    output_dir.mkdir(parents=True, exist_ok=True)
    postgres_dir = output_dir / "postgres"
    food_guide_dir = output_dir / "food_guide"
    raw_dir = output_dir / "raw"
    postgres_dir.mkdir(parents=True, exist_ok=True)
    food_guide_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    recipe_csv = _read_source_text(source_rev, RECIPE_SOURCE_PATH)
    recipe_rows = list(csv.DictReader(recipe_csv.splitlines()))
    sql_text, recipe_ingredient_count, recipe_seed_ingredient_count = _build_recipe_seed_sql(recipe_rows)
    (postgres_dir / "recipes_seed.sql").write_text(sql_text, encoding="utf-8", newline="\n")
    (raw_dir / "recipe_175.csv").write_text(recipe_csv, encoding="utf-8", newline="\n")

    nutrition_source = _read_source_text(source_rev, f"{NUTRITION_SOURCE_DIR}/food_nutrition_facts.csv")
    nutrition_output, nutrition_count = _build_food_nutrition_facts_csv(nutrition_source)
    (postgres_dir / "food_nutrition_facts.csv").write_text(
        nutrition_output,
        encoding="utf-8",
        newline="\n",
    )
    for filename in NUTRITION_FILES:
        text = _read_source_text(source_rev, f"{NUTRITION_SOURCE_DIR}/{filename}")
        (raw_dir / filename).write_text(text, encoding="utf-8", newline="\n")

    copied_food_guide_files = 0
    for filename in FOOD_GUIDE_FILES:
        text = _read_source_text(source_rev, f"{FOOD_GUIDE_SOURCE_DIR}/{filename}")
        (food_guide_dir / filename).write_text(text, encoding="utf-8", newline="\n")
        copied_food_guide_files += 1

    manifest = {
        "postgres_sql": [
            {
                "key": "postgres/recipes_seed.sql",
                "description": "Seed the curated 175 Bobbeori recipes and recipe ingredient links.",
            }
        ],
        "postgres_csv": [
            {
                "table": "food_nutrition_facts",
                "key": "postgres/food_nutrition_facts.csv",
                "mode": "skip_if_not_empty",
                "description": "Seed normalized nutrition facts.",
            }
        ],
        "neo4j_food_guide": [
            {
                "prefix": "food_guide/",
                "description": "Seed food guide graph nodes/relationships from split CSVs.",
            }
        ],
        "raw_files": [
            {
                "key": "raw/recipe_175.csv",
                "source": f"{source_rev}:{RECIPE_SOURCE_PATH}",
            },
            {
                "key": "raw/food_nutrition_facts.csv",
                "source": f"{source_rev}:{NUTRITION_SOURCE_DIR}/food_nutrition_facts.csv",
            },
            {
                "key": "raw/nutrition_aliases.csv",
                "source": f"{source_rev}:{NUTRITION_SOURCE_DIR}/nutrition_aliases.csv",
            },
        ],
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    return SeedStats(
        recipes=len(recipe_rows),
        recipe_ingredients=recipe_ingredient_count,
        recipe_seed_ingredients=recipe_seed_ingredient_count,
        nutrition_facts=nutrition_count,
        food_guide_files=copied_food_guide_files,
    )


def _read_source_text(source_rev: str, source_path: str) -> str:
    local_path = Path(source_path)
    if local_path.exists():
        return local_path.read_text(encoding="utf-8-sig")

    data = subprocess.check_output(["git", "show", f"{source_rev}:{source_path}"])
    return data.decode("utf-8-sig")


def _build_recipe_seed_sql(rows: list[dict[str, str]]) -> tuple[str, int, int]:
    recipe_values: list[str] = []
    recipe_ingredient_values: list[str] = []
    ingredients: OrderedDict[str, dict[str, str | None]] = OrderedDict()

    for row in rows:
        recipe_id = _recipe_id(row["recipe_code"])
        ingredient_names = _json_list(row.get("ingredient_names"))
        ingredient_amounts = _json_list(row.get("ingredient_amounts"))
        main_ingredients = {_normalize_name(name) for name in _json_list(row.get("main_ingredients"))}
        recipe_steps = _recipe_steps(row)

        recipe_values.append(
            "("
            + ", ".join(
                [
                    str(recipe_id),
                    _sql_literal(row.get("recipe_name")),
                    _sql_literal(_recipe_description(row)),
                    _sql_literal(row.get("menu_category")),
                    _sql_int(row.get("serving_size")),
                    _sql_int(row.get("total_time_minutes")),
                    _sql_literal(row.get("difficulty")),
                    _sql_literal(row.get("main_image_url")),
                    _sql_literal(_source_url(row.get("legacy_recipe_id"))),
                    _sql_jsonb(recipe_steps),
                ]
            )
            + ")"
        )

        for idx, ingredient_name in enumerate(ingredient_names):
            clean_name = ingredient_name.strip()
            if not clean_name:
                continue

            normalized = _normalize_name(clean_name)
            amount = ingredient_amounts[idx] if idx < len(ingredient_amounts) else ""
            quantity, unit = _parse_amount(amount)
            ingredients.setdefault(
                normalized,
                {
                    "name": clean_name,
                    "normalized_name": normalized,
                    "category": None,
                    "default_unit": unit,
                },
            )
            if not ingredients[normalized].get("default_unit") and unit:
                ingredients[normalized]["default_unit"] = unit

            recipe_ingredient_values.append(
                "("
                + ", ".join(
                    [
                        str(recipe_id),
                        f"(SELECT id FROM ingredients WHERE normalized_name = {_sql_literal(normalized)} ORDER BY id LIMIT 1)",
                        _sql_literal(clean_name),
                        _sql_decimal(quantity),
                        _sql_literal(unit),
                        "TRUE" if normalized in main_ingredients else "FALSE",
                    ]
                )
                + ")"
            )

    recipe_ids = sorted(_recipe_id(row["recipe_code"]) for row in rows)
    ingredient_values = [
        "("
        + ", ".join(
            [
                _sql_literal(item["name"]),
                _sql_literal(item["normalized_name"]),
                _sql_literal(item["category"]),
                _sql_literal(item["default_unit"]),
            ]
        )
        + ")"
        for item in ingredients.values()
    ]

    sql_lines = [
        "-- Generated by scripts/build_seed_bundle.py. Do not edit by hand.",
        "BEGIN;",
        "",
        "WITH seed_ingredients(name, normalized_name, category, default_unit) AS (",
        "    VALUES",
        _indent_values(ingredient_values),
        ")",
        "INSERT INTO ingredients (name, normalized_name, category, default_unit)",
        "SELECT name, normalized_name, category, default_unit",
        "FROM seed_ingredients",
        "WHERE NOT EXISTS (",
        "    SELECT 1 FROM ingredients i WHERE i.normalized_name = seed_ingredients.normalized_name",
        ");",
        "",
        "WITH seed_ingredients(name, normalized_name, category, default_unit) AS (",
        "    VALUES",
        _indent_values(ingredient_values),
        ")",
        "UPDATE ingredients i",
        "SET",
        "    category = COALESCE(i.category, seed_ingredients.category),",
        "    default_unit = COALESCE(i.default_unit, seed_ingredients.default_unit)",
        "FROM seed_ingredients",
        "WHERE i.normalized_name = seed_ingredients.normalized_name;",
        "",
        "INSERT INTO recipes (",
        "    id, title, description, category, serving_size, cooking_time,",
        "    difficulty, image_url, source_url, recipe_steps",
        ") VALUES",
        _indent_values(recipe_values),
        "ON CONFLICT (id) DO UPDATE SET",
        "    title = EXCLUDED.title,",
        "    description = EXCLUDED.description,",
        "    category = EXCLUDED.category,",
        "    serving_size = EXCLUDED.serving_size,",
        "    cooking_time = EXCLUDED.cooking_time,",
        "    difficulty = EXCLUDED.difficulty,",
        "    image_url = EXCLUDED.image_url,",
        "    source_url = EXCLUDED.source_url,",
        "    recipe_steps = EXCLUDED.recipe_steps;",
        "",
        f"DELETE FROM recipe_ingredients WHERE recipe_id IN ({', '.join(map(str, recipe_ids))});",
        "",
        "INSERT INTO recipe_ingredients (",
        "    recipe_id, ingredient_id, raw_ingredient_name,",
        "    required_quantity, unit, is_main_ingredient",
        ") VALUES",
        _indent_values(recipe_ingredient_values),
        ";",
        "",
        "SELECT setval(pg_get_serial_sequence('ingredients', 'id'), COALESCE((SELECT MAX(id) FROM ingredients), 1), EXISTS (SELECT 1 FROM ingredients));",
        "SELECT setval(pg_get_serial_sequence('recipes', 'id'), COALESCE((SELECT MAX(id) FROM recipes), 1), EXISTS (SELECT 1 FROM recipes));",
        "SELECT setval(pg_get_serial_sequence('recipe_ingredients', 'id'), COALESCE((SELECT MAX(id) FROM recipe_ingredients), 1), EXISTS (SELECT 1 FROM recipe_ingredients));",
        "",
        "COMMIT;",
        "",
    ]

    return "\n".join(sql_lines), len(recipe_ingredient_values), len(ingredients)


def _build_food_nutrition_facts_csv(source_csv: str) -> tuple[str, int]:
    reader = csv.DictReader(source_csv.splitlines())
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=list(NUTRITION_COLUMN_MAP))
    writer.writeheader()

    count = 0
    for row in reader:
        converted: dict[str, str | None] = {}
        for target, source in NUTRITION_COLUMN_MAP.items():
            raw_value = row.get(source)
            if target in NUTRITION_NUMERIC_COLUMNS:
                converted[target] = _normalize_number(raw_value)
            elif target == "is_representative_nutrition":
                converted[target] = _normalize_bool(raw_value)
            else:
                converted[target] = _blank_to_none(raw_value)
        writer.writerow(converted)
        count += 1

    return output.getvalue(), count


def _recipe_id(recipe_code: str) -> int:
    match = re.fullmatch(r"R(\d{4,})", recipe_code.strip())
    if not match:
        raise ValueError(f"unsupported recipe_code: {recipe_code}")
    return int(match.group(1))


def _json_list(value: str | None) -> list[str]:
    if not value:
        return []
    parsed = json.loads(value)
    if not isinstance(parsed, list):
        raise ValueError(f"expected JSON list: {value[:80]}")
    return [str(item) for item in parsed]


def _recipe_steps(row: dict[str, str]) -> list[dict[str, Any]]:
    steps = _json_list(row.get("cooking_steps"))
    times = _json_list(row.get("step_times"))
    heat_levels = _json_list(row.get("heat_levels"))
    return [
        {
            "step_no": idx + 1,
            "title": f"{idx + 1}단계",
            "text": step,
            "time": times[idx] if idx < len(times) else None,
            "heat_level": heat_levels[idx] if idx < len(heat_levels) else None,
        }
        for idx, step in enumerate(steps)
        if step.strip()
    ]


def _recipe_description(row: dict[str, str]) -> str:
    parts = [
        row.get("sub_category"),
        _join_json(row.get("cooking_methods")),
        _join_json(row.get("occasion_tags")),
        row.get("beginner_tip"),
    ]
    return " · ".join(part.strip() for part in parts if part and part.strip())


def _join_json(value: str | None) -> str:
    items = _json_list(value)
    return ", ".join(item for item in items if item.strip())


def _source_url(legacy_recipe_id: str | None) -> str | None:
    value = (legacy_recipe_id or "").strip()
    if not value:
        return None
    return f"https://www.10000recipe.com/recipe/{value}"


def _normalize_name(name: str) -> str:
    return name.strip().replace(" ", "").lower()


def _parse_amount(value: str | None) -> tuple[Decimal | None, str | None]:
    text = (value or "").strip()
    if not text:
        return None, None
    if "~" in text or "±" in text:
        return None, _trim_unit(text)

    match = re.match(r"^(\d+(?:\.\d+)?)(?:/(\d+(?:\.\d+)?))?(.*)$", text)
    if not match:
        return None, _trim_unit(text)

    numerator = Decimal(match.group(1))
    denominator_text = match.group(2)
    try:
        quantity = numerator / Decimal(denominator_text) if denominator_text else numerator
    except (InvalidOperation, ZeroDivisionError):
        quantity = None

    unit = _trim_unit(match.group(3).strip())
    return quantity, unit


def _trim_unit(value: str | None) -> str | None:
    text = (value or "").strip()
    if not text:
        return None
    return text[:30]


def _sql_literal(value: str | None) -> str:
    if value is None:
        return "NULL"
    text = str(value).strip()
    if text == "":
        return "NULL"
    return "'" + text.replace("'", "''") + "'"


def _sql_int(value: str | None) -> str:
    text = (value or "").strip()
    if not text:
        return "NULL"
    return str(int(float(text)))


def _sql_decimal(value: Decimal | None) -> str:
    if value is None:
        return "NULL"
    return format(value.quantize(Decimal("0.01")), "f")


def _sql_jsonb(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return _sql_literal(text) + "::jsonb"


def _blank_to_none(value: str | None) -> str | None:
    text = (value or "").strip()
    return text or None


def _normalize_number(value: str | None) -> str | None:
    text = _blank_to_none(value)
    if text is None or text in {"-", "Tr", "trace"}:
        return None
    return text.replace(",", "")


def _normalize_bool(value: str | None) -> str | None:
    text = _blank_to_none(value)
    if text is None:
        return None
    return "true" if text.lower() in {"true", "1", "y", "yes", "o", "대표", "예"} else "false"


def _indent_values(values: list[str]) -> str:
    if not values:
        raise ValueError("seed values cannot be empty")
    return ",\n".join(f"    {value}" for value in values)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Bobbeori production seed bundle.")
    parser.add_argument("--output", default="seed-prod", help="Output seed bundle directory.")
    parser.add_argument("--source-rev", default="origin/dev", help="Git revision that contains source CSVs.")
    args = parser.parse_args()

    stats = build_seed_bundle(
        output_dir=Path(args.output),
        source_rev=args.source_rev,
    )
    print(
        "seed bundle built: "
        f"recipes={stats.recipes}, "
        f"recipe_ingredients={stats.recipe_ingredients}, "
        f"recipe_seed_ingredients={stats.recipe_seed_ingredients}, "
        f"nutrition_facts={stats.nutrition_facts}, "
        f"food_guide_files={stats.food_guide_files}, "
        f"output={Path(args.output).resolve()}"
    )


if __name__ == "__main__":
    main()
