"""Load the curated 175-recipe catalogue into the food-guide Neo4j graph.

The food-guide loader owns Ingredient/Alias nodes.  This loader only links to
those nodes; it never creates a second ingredient master.  Legacy recipe ids
are used solely to migrate the cold-start review corpus to the new recipeCode.
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
from tqdm import tqdm

from etl.load_to_neo4j.neo4j_connection import Neo4j_Connection, load_settings

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[3]
RECIPE_CSV = ROOT / "storage" / "processed" / "recipe" / "recipe_175.csv"
REVIEW_CSV = ROOT / "storage" / "processed" / "recipe" / "review_by_llm.csv"
FOOD_GUIDE_DIR = ROOT / "storage" / "processed" / "food_guide"
BATCH_SIZE = 100

CONSTRAINT_QUERIES = (
    "CREATE CONSTRAINT recipe_code IF NOT EXISTS FOR (r:Recipe) REQUIRE r.recipeCode IS UNIQUE",
    "CREATE CONSTRAINT cold_start_user_id IF NOT EXISTS FOR (u:ColdStartUser) REQUIRE u.userId IS UNIQUE",
    "CREATE INDEX recipe_filter IF NOT EXISTS FOR (r:Recipe) ON (r.difficulty, r.totalTimeMinutes)",
    "CREATE FULLTEXT INDEX recipe_name_search IF NOT EXISTS FOR (r:Recipe) ON EACH [r.name]",
)

CLEAR_RECIPE_GRAPH_QUERY = """
MATCH (n)
WHERE n:Recipe OR n:Reviewer OR n:ColdStartUser OR n:RecipeCategory OR n:CookingMethod
   OR n:OccasionTag OR n:MealType OR n:CookingTool
DETACH DELETE n
"""

UPSERT_RECIPE_QUERY = """
UNWIND $rows AS row
MERGE (r:Recipe {recipeCode: row.recipeCode})
SET r += row
"""

UPSERT_INGREDIENT_REL_QUERY = """
UNWIND $rows AS row
MATCH (r:Recipe {recipeCode: row.recipeCode})
MATCH (i:Ingredient {id: row.ingredientId})
MERGE (r)-[rel:REQUIRES_INGREDIENT {position: row.position}]->(i)
SET rel.amount = row.amount,
    rel.isMain = row.isMain, rel.sourceName = row.sourceName,
    rel.matchMethod = row.matchMethod
"""

UPSERT_REVIEW_QUERY = """
UNWIND $rows AS row
MERGE (u:ColdStartUser {userId: row.userId})
MATCH (r:Recipe {recipeCode: row.recipeCode})
MERGE (u)-[rel:REVIEWED {reviewId: row.reviewId}]->(r)
SET rel.content = row.content, rel.positive = row.positive,
    rel.negative = row.negative, rel.sentimentScore = row.sentimentScore,
    rel.starCount = row.starCount,
    rel.starNorm = row.starNorm, rel.source = 'legacy_cold_start'
"""

SUMMARY_QUERY = """
CALL () {
  MATCH (n:Recipe) RETURN 'Recipe' AS label, count(n) AS count
  UNION ALL MATCH (n:ColdStartUser) RETURN 'ColdStartUser' AS label, count(n) AS count
  UNION ALL MATCH ()-[r:REQUIRES_INGREDIENT]->() RETURN 'REQUIRES_INGREDIENT' AS label, count(r) AS count
  UNION ALL MATCH ()-[r:REVIEWED]->() RETURN 'REVIEWED' AS label, count(r) AS count
}
RETURN label, count
"""


def _text(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    value = str(value).strip()
    return value or None


def _number(value: Any) -> float | int | None:
    text = _text(value)
    if text is None:
        return None
    number = float(text)
    return int(number) if number.is_integer() else number


def _json_list(value: Any) -> list[Any]:
    text = _text(value)
    if not text:
        return []
    parsed = json.loads(text)
    if not isinstance(parsed, list):
        raise ValueError("expected a JSON array")
    return parsed


def _chunks(rows: list[dict[str, Any]]) -> Iterable[list[dict[str, Any]]]:
    for index in range(0, len(rows), BATCH_SIZE):
        yield rows[index : index + BATCH_SIZE]


def _upsert_batches(conn: Neo4j_Connection, query: str, rows: list[dict[str, Any]], desc: str) -> None:
    for batch in tqdm(_chunks(rows), desc=desc):
        conn.execute_write(query, {"rows": batch})


def load_recipe_tables(
    recipe_csv: Path = RECIPE_CSV,
    review_csv: Path = REVIEW_CSV,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    for path in (recipe_csv, review_csv):
        if not path.is_file():
            raise FileNotFoundError(f"CSV not found: {path}")
    return tuple(pd.read_csv(path, encoding="utf-8-sig") for path in (recipe_csv, review_csv))  # type: ignore[return-value]


def _recipe_code(value: Any) -> str:
    code = str(value).strip().upper()
    if not re.fullmatch(r"R\d{4}", code):
        raise ValueError(f"invalid recipe_code: {value!r}")
    return code


def build_recipe_rows(recipe_df: pd.DataFrame, review_df: pd.DataFrame | None = None) -> list[dict[str, Any]]:
    review_stats: dict[int, dict[str, float | int]] = {}
    if review_df is not None and not review_df.empty:
        for legacy_id, group in review_df.groupby("recipe_id"):
            review_stats[int(legacy_id)] = {
                "coldStartReviewCount": int(len(group)),
                "coldStartStarAvg": float(pd.to_numeric(group["star_count"]).mean()),
                "coldStartSentimentAvg": float(pd.to_numeric(group["positive"]).mean()),
            }
    rows = []
    array_properties = {
        "main_ingredients": "mainIngredients", "ingredient_names": "ingredientNames",
        "ingredient_amounts": "ingredientAmounts", "cooking_methods": "cookingMethods",
        "occasion_tags": "occasionTags", "meal_types": "mealTypes",
        "required_tools": "requiredTools", "cooking_steps": "cookingSteps",
        "step_times": "stepTimes", "heat_levels": "heatLevels",
        "substitute_ingredients": "substituteIngredients",
        "optional_ingredients": "optionalIngredients", "step_image_urls": "stepImageUrls",
    }
    scalar_properties = {
        "recipe_name": "name", "menu_category": "menuCategory", "sub_category": "subCategory",
        "spice_level": "spiceLevel", "serving_size": "servingSize",
        "ingredient_count": "ingredientCount", "total_time_minutes": "totalTimeMinutes",
        "difficulty": "difficulty", "cleanup_level": "cleanupLevel", "step_count": "stepCount",
        "storage_method": "storageMethod", "reheating_method": "reheatingMethod",
        "beginner_tip": "beginnerTip", "failure_prevention_tip": "failurePreventionTip",
        "beginner_score": "beginnerScore", "single_household_score": "singleHouseholdScore",
        "main_image_url": "mainImageUrl", "legacy_match_method": "legacyMatchMethod",
        "legacy_match_score": "legacyMatchScore",
    }
    for row in recipe_df.to_dict("records"):
        legacy_id = int(row["legacy_recipe_id"])
        item: dict[str, Any] = {
            "recipeCode": _recipe_code(row["recipe_code"]),
            "recipeId": int(str(row["recipe_code"])[1:]),
            "legacyRecipeId": legacy_id,
        }
        for source, target in scalar_properties.items():
            item[target] = _number(row[source]) if source.endswith(("_score", "_count", "_size", "_minutes")) else _text(row[source])
        for source, target in array_properties.items():
            item[target] = _json_list(row[source])
        item.update(review_stats.get(legacy_id, {"coldStartReviewCount": 0}))
        rows.append(item)
    return rows


def _normalise_name(value: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]", "", unicodedata.normalize("NFKC", value).lower())


def _candidate_names(name: str) -> list[str]:
    candidates = [name]
    candidates.extend(re.split(r"\s*또는\s*|\s+or\s+", name))
    removable = r"^(다진|삶은|손질|냉동|조리된|따뜻한|찬|마른|볶음용|국물용|부침용|시판|완숙|깐|동봉)\s*"
    candidates.extend(re.sub(removable, "", item) for item in list(candidates))
    candidates.extend(re.sub(r"\s*(흰 부분|통조림|슬라이스|필렛|가루|용)$", "", item) for item in list(candidates))
    return list(dict.fromkeys(_normalise_name(item) for item in candidates if item))


def load_ingredient_lookup(food_guide_dir: Path = FOOD_GUIDE_DIR) -> dict[str, str]:
    ingredients = pd.read_csv(food_guide_dir / "nodes_ingredient.csv", encoding="utf-8-sig")
    aliases = pd.read_csv(food_guide_dir / "nodes_alias.csv", encoding="utf-8-sig")
    relations = pd.read_csv(food_guide_dir / "rel_ingredient_has_alias.csv", encoding="utf-8-sig")
    alias_to_ingredient = dict(zip(relations["alias_id"], relations["ingredient_id"]))
    lookup: dict[str, str] = {}
    for row in ingredients.to_dict("records"):
        for value in (row.get("name"), row.get("display_name")):
            if _text(value):
                lookup.setdefault(_normalise_name(str(value)), str(row["ingredient_id"]))
    for row in aliases.to_dict("records"):
        ingredient_id = alias_to_ingredient.get(row["alias_id"])
        if ingredient_id and _text(row["name"]):
            lookup.setdefault(_normalise_name(str(row["name"])), ingredient_id)
    return lookup


def build_ingredient_rows(recipe_df: pd.DataFrame, lookup: dict[str, str]) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    links: list[dict[str, Any]] = []
    unresolved: dict[str, list[str]] = defaultdict(list)
    for recipe in recipe_df.to_dict("records"):
        code = _recipe_code(recipe["recipe_code"])
        names, amounts = _json_list(recipe["ingredient_names"]), _json_list(recipe["ingredient_amounts"])
        main_ids = {
            lookup[candidate]
            for value in _json_list(recipe["main_ingredients"])
            for candidate in _candidate_names(str(value))
            if candidate in lookup
        }
        if len(names) != len(amounts):
            raise ValueError(f"{code}: ingredient_names/ingredient_amounts length mismatch")
        for position, (name, amount) in enumerate(zip(names, amounts), start=1):
            matches = [(candidate, lookup[candidate]) for candidate in _candidate_names(str(name)) if candidate in lookup]
            if not matches:
                unresolved[code].append(str(name))
                continue
            candidate, ingredient_id = matches[0]
            links.append({"recipeCode": code, "ingredientId": ingredient_id, "amount": str(amount),
                          "position": position, "isMain": ingredient_id in main_ids,
                          "sourceName": str(name), "matchMethod": "exact" if candidate == _normalise_name(str(name)) else "normalized_variant"})
    return links, dict(unresolved)


def build_review_rows(recipe_df: pd.DataFrame, review_df: pd.DataFrame) -> list[dict[str, Any]]:
    code_by_legacy = {int(row["legacy_recipe_id"]): _recipe_code(row["recipe_code"]) for row in recipe_df.to_dict("records")}
    rows = []
    for index, row in enumerate(review_df.to_dict("records"), start=1):
        code = code_by_legacy.get(int(row["recipe_id"]))
        if not code:
            continue
        positive, negative = _number(row.get("positive")), _number(row.get("negative"))
        sentiment_score = None if positive is None or negative is None else float(positive) - float(negative)
        rows.append({"recipeCode": code, "userId": f"cold:{int(row['group_id'])}",
                     "reviewId": f"review:{int(row['group_id'])}:{index}",
                     "content": _text(row.get("content")), "positive": _number(row.get("positive")),
                     "negative": negative, "sentimentScore": sentiment_score,
                     "starCount": _number(row.get("star_count")),
                     "starNorm": _number(row.get("star_norm"))})
    return rows


def validate_graph_rows(recipe_rows: list[dict[str, Any]], ingredient_rows: list[dict[str, Any]]) -> None:
    codes = [row["recipeCode"] for row in recipe_rows]
    if len(codes) != 175 or len(set(codes)) != 175:
        raise ValueError(f"expected 175 unique recipes, got {len(codes)} rows/{len(set(codes))} unique")
    if any(row["recipeCode"] not in set(codes) for row in ingredient_rows):
        raise ValueError("ingredient relationship references an unknown recipe")


def load_recipe_graph_to_neo4j(*, clear: bool = False, recipe_csv: Path = RECIPE_CSV,
                               review_csv: Path = REVIEW_CSV,
                               food_guide_dir: Path = FOOD_GUIDE_DIR) -> dict[str, int]:
    recipe_df, review_df = load_recipe_tables(recipe_csv, review_csv)
    recipe_rows = build_recipe_rows(recipe_df, review_df)
    ingredient_rows, unresolved = build_ingredient_rows(recipe_df, load_ingredient_lookup(food_guide_dir))
    for row in recipe_rows:
        row["unlinkedIngredients"] = unresolved.get(row["recipeCode"], [])
    reviews = build_review_rows(recipe_df, review_df)
    validate_graph_rows(recipe_rows, ingredient_rows)

    settings = load_settings()
    conn = Neo4j_Connection(settings.uri, settings.user, settings.password, database=settings.database)
    try:
        for query in CONSTRAINT_QUERIES:
            conn.execute_write(query)
        if clear:
            conn.execute_write(CLEAR_RECIPE_GRAPH_QUERY)
        _upsert_batches(conn, UPSERT_RECIPE_QUERY, recipe_rows, "Recipe upsert")
        _upsert_batches(conn, UPSERT_INGREDIENT_REL_QUERY, ingredient_rows, "Ingredient links")
        _upsert_batches(conn, UPSERT_REVIEW_QUERY, reviews, "Cold-start reviews")
        summary = conn.execute_query(SUMMARY_QUERY)
    finally:
        conn.close()
    result = {row["label"]: int(row["count"]) for row in summary}
    result["UnlinkedIngredientOccurrences"] = sum(map(len, unresolved.values()))
    logger.info("Recipe graph load complete: %s", result)
    return result


def _self_check() -> None:
    recipe_df, review_df = load_recipe_tables()
    recipe_rows = build_recipe_rows(recipe_df, review_df)
    ingredient_rows, unresolved = build_ingredient_rows(recipe_df, load_ingredient_lookup())
    validate_graph_rows(recipe_rows, ingredient_rows)
    assert recipe_rows[0]["recipeCode"] == "R0001"
    assert all(row["legacyRecipeId"] for row in recipe_rows)
    assert build_review_rows(recipe_df, review_df)
    assert sum(map(len, unresolved.values())) < sum(len(_json_list(v)) for v in recipe_df["ingredient_names"])
