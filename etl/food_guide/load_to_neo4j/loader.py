from __future__ import annotations

import logging
import re
from hashlib import sha256
from pathlib import Path
from typing import Any

import pandas as pd
from tqdm import tqdm

from etl.load_to_neo4j.neo4j_connection import Neo4j_Connection, load_settings
from .config import DEFAULT_FOOD_GUIDE_CSV

logger = logging.getLogger(__name__)

# =============================================================================
# 데이터 경로 (구 config.py)
# =============================================================================

BATCH_SIZE = 100

DROP_LEGACY_CONSTRAINT_QUERIES = (
    "DROP CONSTRAINT food_category_key IF EXISTS",
    "DROP CONSTRAINT food_guide_code IF EXISTS",
)

CONSTRAINT_QUERIES = (
    "CREATE CONSTRAINT food_guide_key IF NOT EXISTS FOR (g:FoodGuide) REQUIRE g.key IS UNIQUE",
    "CREATE CONSTRAINT food_category_key IF NOT EXISTS FOR (c:FoodCategory) REQUIRE c.key IS UNIQUE",
    "CREATE CONSTRAINT food_alias_key IF NOT EXISTS FOR (a:Alias) REQUIRE a.key IS UNIQUE",
    "CREATE CONSTRAINT season_month_value IF NOT EXISTS FOR (m:SeasonMonth) REQUIRE m.month IS UNIQUE",
    "CREATE CONSTRAINT food_nutrition_key IF NOT EXISTS FOR (n:Nutrition) REQUIRE n.key IS UNIQUE",
    "CREATE CONSTRAINT food_guide_detail_key IF NOT EXISTS FOR (d:Guide) REQUIRE d.key IS UNIQUE",
    "CREATE CONSTRAINT food_source_key IF NOT EXISTS FOR (s:Source) REQUIRE s.key IS UNIQUE",
)

SPLIT_NODE_SPECS = {
    "nodes_major_category.csv": ("MajorCategory", "major_id"),
    "nodes_middle_category.csv": ("MiddleCategory", "middle_id"),
    "nodes_ingredient.csv": ("Ingredient", "ingredient_id"),
    "nodes_guide.csv": ("Guide", "guide_id"),
    "nodes_source.csv": ("Source", "source_id"),
    "nodes_alias.csv": ("Alias", "alias_id"),
    "nodes_season_month.csv": ("SeasonMonth", "month_id"),
    "nodes_nutrition.csv": ("Nutrition", "nutrition_id"),
}

SPLIT_RELATION_SPECS = {
    "rel_major_has_middle.csv": ("MajorCategory", "major_id", "HAS_MIDDLE", "MiddleCategory", "middle_id"),
    "rel_middle_has_ingredient.csv": ("MiddleCategory", "middle_id", "HAS_INGREDIENT", "Ingredient", "ingredient_id"),
    "rel_ingredient_has_guide.csv": ("Ingredient", "ingredient_id", "HAS_GUIDE", "Guide", "guide_id"),
    "rel_guide_sourced_from.csv": ("Guide", "guide_id", "SOURCED_FROM", "Source", "source_id"),
    "rel_ingredient_has_alias.csv": ("Ingredient", "ingredient_id", "HAS_ALIAS", "Alias", "alias_id"),
    "rel_ingredient_in_season.csv": ("Ingredient", "ingredient_id", "IN_SEASON", "SeasonMonth", "month_id"),
    "rel_ingredient_has_nutrition.csv": ("Ingredient", "ingredient_id", "HAS_NUTRITION", "Nutrition", "nutrition_id"),
    "rel_nutrition_sourced_from.csv": ("Nutrition", "nutrition_id", "SOURCED_FROM", "Source", "source_id"),
}

SPLIT_CONSTRAINT_QUERIES = tuple(
    f"CREATE CONSTRAINT food_guide_{label.lower()}_id IF NOT EXISTS "
    f"FOR (n:{label}) REQUIRE n.id IS UNIQUE"
    for label, _ in SPLIT_NODE_SPECS.values()
)

SPLIT_NUMERIC_COLUMNS = {
    "energy_kcal",
    "water_g",
    "protein_g",
    "fat_g",
    "ash_g",
    "carbohydrate_g",
    "sugar_g",
    "fiber_g",
    "calcium_mg",
    "iron_mg",
    "phosphorus_mg",
    "potassium_mg",
    "sodium_mg",
    "cholesterol_mg",
    "saturated_fat_g",
    "trans_fat_g",
}

# =============================================================================
# Cypher 쿼리
# =============================================================================

CLEAR_FOOD_GUIDE_QUERY = """
MATCH (g:FoodGuide)
DETACH DELETE g
WITH 1 AS _
MATCH (c:FoodCategory)
DETACH DELETE c
"""

CLEAR_MANAGED_DETAIL_NODES_QUERY = """
MATCH (n)
WHERE n.foodGuideManaged = true
  AND (n:Alias OR n:SeasonMonth OR n:Nutrition OR n:Guide OR n:Source)
DETACH DELETE n
"""

CLEAR_SPLIT_FOOD_GUIDE_QUERY = """
MATCH (n)
WHERE n:FoodGuide OR n:FoodCategory OR n.foodGuideManaged = true
DETACH DELETE n
"""

SPLIT_COMPATIBILITY_QUERIES = (
    """
    MATCH (major:MajorCategory)-[:HAS_MIDDLE]->(middle:MiddleCategory)
          -[:HAS_INGREDIENT]->(ingredient:Ingredient)
    SET ingredient:FoodGuide,
        ingredient.key = ingredient.id,
        ingredient.code = ingredient.id,
        ingredient.rawName = ingredient.name,
        ingredient.representativeName = ingredient.displayName,
        ingredient.majorCategory = major.name,
        ingredient.middleCategory = middle.name,
        ingredient.minorCategory = ingredient.name,
        ingredient.level = "minor"
    """,
    """
    MATCH (ingredient:Ingredient)
    OPTIONAL MATCH (ingredient)-[:HAS_ALIAS]->(alias:Alias)
    WITH ingredient, [name IN collect(DISTINCT alias.name) WHERE name IS NOT NULL] AS aliases
    SET ingredient.aliases = aliases
    """,
    """
    MATCH (ingredient:Ingredient)
    OPTIONAL MATCH (ingredient)-[:IN_SEASON]->(month:SeasonMonth)
    WITH ingredient, [value IN collect(DISTINCT month.month) WHERE value IS NOT NULL] AS months
    SET ingredient.seasonalMonths = months
    """,
    """
    MATCH (ingredient:Ingredient)
    OPTIONAL MATCH (ingredient)-[:HAS_GUIDE]->(guide:Guide)
    WITH ingredient, collect(guide) AS guides
    SET ingredient.storageTip = head([item IN guides WHERE item.type = "보관" | item.content]),
        ingredient.prepTip = head([item IN guides WHERE item.type = "손질" | item.content]),
        ingredient.washingTip = head([item IN guides WHERE item.type = "세척" | item.content]),
        ingredient.freshnessTip = head([item IN guides WHERE item.type = "신선도체크" | item.content])
    """,
    """
    MATCH (ingredient:Ingredient)
    OPTIONAL MATCH (ingredient)-[:HAS_GUIDE]->(guide:Guide)-[:SOURCED_FROM]->(source:Source)
    WITH ingredient, collect({type: guide.type, name: source.name, url: source.url}) AS sources
    SET ingredient.storageSourceName = head([item IN sources WHERE item.type = "보관" | item.name]),
        ingredient.storageSourceUrl = head([item IN sources WHERE item.type = "보관" | item.url]),
        ingredient.prepSourceName = head([item IN sources WHERE item.type = "손질" | item.name]),
        ingredient.prepSourceUrl = head([item IN sources WHERE item.type = "손질" | item.url]),
        ingredient.washingSourceName = head([item IN sources WHERE item.type = "세척" | item.name]),
        ingredient.washingSourceUrl = head([item IN sources WHERE item.type = "세척" | item.url]),
        ingredient.freshnessSourceName = head([item IN sources WHERE item.type = "신선도체크" | item.name]),
        ingredient.freshnessSourceUrl = head([item IN sources WHERE item.type = "신선도체크" | item.url])
    """,
    """
    MATCH (ingredient:Ingredient)
    OPTIONAL MATCH (ingredient)-[:HAS_NUTRITION]->(nutrition:Nutrition)
    OPTIONAL MATCH (nutrition)-[:SOURCED_FROM]->(source:Source)
    SET ingredient.nutritionBaseAmount = nutrition.standardAmount,
        ingredient.energyKcal = nutrition.energyKcal,
        ingredient.proteinG = nutrition.proteinG,
        ingredient.fatG = nutrition.fatG,
        ingredient.carbohydrateG = nutrition.carbohydrateG,
        ingredient.calciumMg = nutrition.calciumMg,
        ingredient.potassiumMg = nutrition.potassiumMg,
        ingredient.sodiumMg = nutrition.sodiumMg,
        ingredient.nutritionSourceName = source.name
    """,
)

UPSERT_FOOD_GUIDE_QUERY = """
UNWIND $rows AS row
MERGE (g:FoodGuide {key: row.guideKey})
SET g:FoodCategory:Ingredient,
    g.code = row.code,
    g.level = "minor",
    g.name = row.name,
    g.path = row.minorPath,
    g.displayName = row.minorDisplayName,
    g.majorCategory = row.majorCategory,
    g.middleCategory = row.middleCategory,
    g.minorCategory = row.minorCategory,
    g.representativeName = row.representativeName,
    g.rawName = row.rawName,
    g.aliases = row.aliases,
    g.existingDisplayName = row.existingDisplayName,
    g.dbGroupName = row.dbGroupName,
    g.subdivisionName = row.subdivisionName,
    g.classificationStandard = row.classificationStandard,
    g.dataSourceType = row.dataSourceType,
    g.seasonalMonths = row.seasonalMonths,
    g.seasonalSourceName = row.seasonalSourceName,
    g.seasonalSourceUrl = row.seasonalSourceUrl,
    g.storageTip = row.storageTip,
    g.horticulturalStorageTip = row.horticulturalStorageTip,
    g.prepTip = row.prepTip,
    g.washingTip = row.washingTip,
    g.washingCriteria = row.washingCriteria,
    g.freshnessTip = row.freshnessTip,
    g.intakeTip = row.intakeTip,
    g.nutritionBaseAmount = row.nutritionBaseAmount,
    g.energyKcal = row.energyKcal,
    g.waterG = row.waterG,
    g.proteinG = row.proteinG,
    g.fatG = row.fatG,
    g.ashG = row.ashG,
    g.carbohydrateG = row.carbohydrateG,
    g.sugarG = row.sugarG,
    g.fiberG = row.fiberG,
    g.calciumMg = row.calciumMg,
    g.ironMg = row.ironMg,
    g.phosphorusMg = row.phosphorusMg,
    g.potassiumMg = row.potassiumMg,
    g.sodiumMg = row.sodiumMg,
    g.cholesterolMg = row.cholesterolMg,
    g.saturatedFatG = row.saturatedFatG,
    g.transFatG = row.transFatG,
    g.storageSourceName = row.storageSourceName,
    g.storageSourceUrl = row.storageSourceUrl,
    g.prepSourceName = row.prepSourceName,
    g.prepSourceUrl = row.prepSourceUrl,
    g.washingSourceName = row.washingSourceName,
    g.washingSourceUrl = row.washingSourceUrl,
    g.freshnessSourceName = row.freshnessSourceName,
    g.freshnessSourceUrl = row.freshnessSourceUrl,
    g.nutritionSourceName = row.nutritionSourceName,
    g.loadedAt = datetime()
WITH g, row
FOREACH (_ IN CASE WHEN row.majorKey IS NULL THEN [] ELSE [1] END |
  MERGE (major:FoodCategory {key: row.majorKey})
  SET major.level = "major",
      major.name = row.majorCategory,
      major.path = row.majorPath,
      major.displayName = row.majorCategory
)
FOREACH (_ IN CASE WHEN row.middleKey IS NULL THEN [] ELSE [1] END |
  MERGE (major:FoodCategory {key: row.majorKey})
  SET major.level = "major",
      major.name = row.majorCategory,
      major.path = row.majorPath,
      major.displayName = row.majorCategory
  MERGE (middle:FoodCategory {key: row.middleKey})
  SET middle.level = "middle",
      middle.name = row.middleCategory,
      middle.path = row.middlePath,
      middle.displayName = row.middleDisplayName
  MERGE (major)-[:HAS_SUBCATEGORY]->(middle)
)
FOREACH (_ IN CASE WHEN row.guideKey IS NULL THEN [] ELSE [1] END |
  MERGE (middle:FoodCategory {key: row.middleKey})
  SET middle.level = "middle",
      middle.name = row.middleCategory,
      middle.path = row.middlePath,
      middle.displayName = row.middleDisplayName
  MERGE (middle)-[:HAS_SUBCATEGORY]->(g)
)
WITH g, row
FOREACH (alias IN row.aliasNodes |
  MERGE (a:Alias {key: alias.key})
  SET a.name = alias.name,
      a.foodGuideManaged = true
  MERGE (g)-[:HAS_ALIAS]->(a)
)
FOREACH (month IN row.seasonalMonths |
  MERGE (m:SeasonMonth {month: month})
  SET m.foodGuideManaged = true
  MERGE (g)-[:IN_SEASON]->(m)
)
MERGE (guide:Guide {key: row.guideKey})
SET guide.storageTip = row.storageTip,
    guide.horticulturalStorageTip = row.horticulturalStorageTip,
    guide.prepTip = row.prepTip,
    guide.washingTip = row.washingTip,
    guide.washingCriteria = row.washingCriteria,
    guide.freshnessTip = row.freshnessTip,
    guide.intakeTip = row.intakeTip,
    guide.foodGuideManaged = true
MERGE (g)-[:HAS_GUIDE]->(guide)
FOREACH (source IN row.guideSources |
  MERGE (s:Source {key: source.key})
  SET s.name = source.name,
      s.url = source.url,
      s.foodGuideManaged = true
  MERGE (guide)-[rel:SOURCED_FROM {kind: source.kind}]->(s)
)
MERGE (n:Nutrition {key: row.guideKey})
SET n.baseAmount = row.nutritionBaseAmount,
    n.energyKcal = row.energyKcal,
    n.waterG = row.waterG,
    n.proteinG = row.proteinG,
    n.fatG = row.fatG,
    n.ashG = row.ashG,
    n.carbohydrateG = row.carbohydrateG,
    n.sugarG = row.sugarG,
    n.fiberG = row.fiberG,
    n.calciumMg = row.calciumMg,
    n.ironMg = row.ironMg,
    n.phosphorusMg = row.phosphorusMg,
    n.potassiumMg = row.potassiumMg,
    n.sodiumMg = row.sodiumMg,
    n.cholesterolMg = row.cholesterolMg,
    n.saturatedFatG = row.saturatedFatG,
    n.transFatG = row.transFatG,
    n.sourceName = row.nutritionSourceName,
    n.foodGuideManaged = true
MERGE (g)-[:HAS_NUTRITION]->(n)
FOREACH (source IN row.nutritionSources |
  MERGE (s:Source {key: source.key})
  SET s.name = source.name,
      s.url = source.url,
      s.foodGuideManaged = true
  MERGE (n)-[:SOURCED_FROM]->(s)
)
"""

# =============================================================================
# CSV → Neo4j 레코드 변환
# =============================================================================


def _text(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def _number(value: Any) -> float | None:
    text = _text(value)
    if text is None or text in {"-", "Tr", "trace"}:
        return None
    text = text.replace(",", "")
    try:
        return float(text)
    except ValueError:
        return None


def _seasonal_months(value: Any) -> list[int]:
    text = _text(value)
    if text is None:
        return []
    months: list[int] = []
    for token in re.findall(r"\d{1,2}", text):
        month = int(token)
        if 1 <= month <= 12 and month not in months:
            months.append(month)
    return months


def _aliases(value: Any) -> list[str]:
    text = _text(value)
    if text is None:
        return []
    parts = re.split(r"[,/|;·]", text)
    return [part.strip() for part in parts if part.strip()]


def _normalize_name(value: Any) -> str:
    return re.sub(r"\s+", "", _text(value) or "").lower()


def _source_node(name: Any, url: Any, kind: str) -> dict[str, str | None] | None:
    source_name = _text(name)
    source_url = _text(url)
    if not source_name and not source_url:
        return None
    identity = f"{source_name or ''}|{source_url or ''}"
    return {
        "key": f"source:{sha256(identity.encode('utf-8')).hexdigest()}",
        "name": source_name,
        "url": source_url,
        "kind": kind,
    }


def _get(row: pd.Series, column: str) -> Any:
    return row[column] if column in row else None


def _category_key(level: str, *parts: str | None) -> str | None:
    clean_parts = [part for part in parts if part]
    if not clean_parts:
        return None
    return f"{level}:" + " > ".join(clean_parts)


def build_food_guide_record(row: pd.Series, index: int) -> dict[str, Any]:
    code = _text(_get(row, "영양식품코드")) or f"food-guide-{index + 1}"
    major_category = _text(_get(row, "영양DB대분류"))
    middle_category = _text(_get(row, "영양DB중분류"))
    minor_category = _text(_get(row, "영양DB소분류"))
    major_path = [major_category] if major_category else []
    middle_path = [major_category, middle_category] if major_category and middle_category else []
    minor_path = (
        [major_category, middle_category, minor_category]
        if major_category and middle_category and minor_category
        else []
    )
    guide_key = _category_key("minor", major_category, middle_category, minor_category)
    aliases = _aliases(_get(row, "원재료명이명"))
    existing_display_name = _text(_get(row, "기존표시명"))
    if existing_display_name and existing_display_name not in aliases:
        aliases.append(existing_display_name)
    guide_sources = [
        _source_node(_get(row, "보관출처명"), _get(row, "보관출처URL"), "storage"),
        _source_node(_get(row, "손질출처명"), _get(row, "손질출처URL"), "prep"),
        _source_node(_get(row, "세척출처명"), _get(row, "세척출처URL"), "washing"),
        _source_node(_get(row, "신선도출처명"), _get(row, "신선도출처URL"), "freshness"),
    ]
    nutrition_source = _source_node(_get(row, "영양출처명"), None, "nutrition")
    return {
        "code": code,
        "guideKey": guide_key,
        "majorCategory": major_category,
        "middleCategory": middle_category,
        "minorCategory": minor_category,
        "majorKey": _category_key("major", major_category),
        "middleKey": _category_key("middle", major_category, middle_category),
        "majorPath": major_path,
        "middlePath": middle_path,
        "minorPath": minor_path,
        "middleDisplayName": " > ".join(middle_path) if middle_path else middle_category,
        "minorDisplayName": " > ".join(minor_path) if minor_path else minor_category,
        "name": minor_category or _text(_get(row, "영양식품명")) or code,
        "representativeName": _text(_get(row, "대표식품명")),
        "rawName": _text(_get(row, "원재료명")),
        "aliases": aliases,
        "aliasNodes": [
            {"key": f"{guide_key}::{_normalize_name(alias)}", "name": alias}
            for alias in aliases
            if guide_key and _normalize_name(alias)
        ],
        "existingDisplayName": existing_display_name,
        "dbGroupName": _text(_get(row, "영양DB그룹명")),
        "subdivisionName": _text(_get(row, "영양식품세분류명")),
        "classificationStandard": _text(_get(row, "분류기준")),
        "dataSourceType": _text(_get(row, "데이터출처구분")),
        "seasonalMonths": _seasonal_months(_get(row, "제철시기(월)")),
        "seasonalSourceName": _text(_get(row, "제철시기출처명")),
        "seasonalSourceUrl": _text(_get(row, "제철시기출처URL")),
        "storageTip": _text(_get(row, "보관")),
        "horticulturalStorageTip": _text(_get(row, "원예보관")),
        "prepTip": _text(_get(row, "손질")),
        "washingTip": _text(_get(row, "세척")),
        "washingCriteria": _text(_get(row, "세척법적용기준")),
        "freshnessTip": _text(_get(row, "신선도체크")),
        "intakeTip": _text(_get(row, "섭취방법_정리")),
        "nutritionBaseAmount": _text(_get(row, "영양성분기준량")),
        "energyKcal": _number(_get(row, "에너지_kcal")),
        "waterG": _number(_get(row, "수분_g")),
        "proteinG": _number(_get(row, "단백질_g")),
        "fatG": _number(_get(row, "지방_g")),
        "ashG": _number(_get(row, "회분_g")),
        "carbohydrateG": _number(_get(row, "탄수화물_g")),
        "sugarG": _number(_get(row, "당류_g")),
        "fiberG": _number(_get(row, "식이섬유_g")),
        "calciumMg": _number(_get(row, "칼슘_mg")),
        "ironMg": _number(_get(row, "철_mg")),
        "phosphorusMg": _number(_get(row, "인_mg")),
        "potassiumMg": _number(_get(row, "칼륨_mg")),
        "sodiumMg": _number(_get(row, "나트륨_mg")),
        "cholesterolMg": _number(_get(row, "콜레스테롤_mg")),
        "saturatedFatG": _number(_get(row, "포화지방산_g")),
        "transFatG": _number(_get(row, "트랜스지방산_g")),
        "storageSourceName": _text(_get(row, "보관출처명")),
        "storageSourceUrl": _text(_get(row, "보관출처URL")),
        "prepSourceName": _text(_get(row, "손질출처명")),
        "prepSourceUrl": _text(_get(row, "손질출처URL")),
        "washingSourceName": _text(_get(row, "세척출처명")),
        "washingSourceUrl": _text(_get(row, "세척출처URL")),
        "freshnessSourceName": _text(_get(row, "신선도출처명")),
        "freshnessSourceUrl": _text(_get(row, "신선도출처URL")),
        "nutritionSourceName": _text(_get(row, "영양출처명")),
        "guideSources": [source for source in guide_sources if source],
        "nutritionSources": [nutrition_source] if nutrition_source else [],
    }


# =============================================================================
# 적재 오케스트레이션
# =============================================================================


def _camel_case(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


def _read_split_tables(split_dir: Path) -> dict[str, pd.DataFrame]:
    required_files = (*SPLIT_NODE_SPECS, *SPLIT_RELATION_SPECS)
    missing_files = [name for name in required_files if not (split_dir / name).is_file()]
    if missing_files:
        raise FileNotFoundError(f"Missing split CSV files: {', '.join(missing_files)}")

    return {
        name: pd.read_csv(
            split_dir / name,
            dtype=str,
            keep_default_na=False,
            encoding="utf-8-sig",
        )
        for name in required_files
    }


def _validate_split_tables(tables: dict[str, pd.DataFrame]) -> None:
    ids_by_column: dict[str, set[str]] = {}
    errors: list[str] = []

    for filename, (_, id_column) in SPLIT_NODE_SPECS.items():
        table = tables[filename]
        if id_column not in table.columns:
            errors.append(f"{filename}: missing column {id_column}")
            continue
        ids = table[id_column].str.strip()
        if (ids == "").any():
            errors.append(f"{filename}: blank {id_column}")
        duplicate_count = int(ids.duplicated().sum())
        if duplicate_count:
            errors.append(f"{filename}: duplicate {id_column} {duplicate_count} rows")
        ids_by_column[id_column] = set(ids)

    for filename, (_, from_column, relationship, _, to_column) in SPLIT_RELATION_SPECS.items():
        table = tables[filename]
        required_columns = {from_column, to_column, "relationship"}
        missing_columns = required_columns - set(table.columns)
        if missing_columns:
            errors.append(f"{filename}: missing columns {', '.join(sorted(missing_columns))}")
            continue
        invalid_relationships = table.loc[table["relationship"].str.strip() != relationship]
        if not invalid_relationships.empty:
            errors.append(f"{filename}: invalid relationship {len(invalid_relationships)} rows")
        duplicate_count = int(table.duplicated([from_column, to_column]).sum())
        if duplicate_count:
            errors.append(f"{filename}: duplicate relationship {duplicate_count} rows")
        for column in (from_column, to_column):
            unknown_ids = set(table[column].str.strip()) - ids_by_column.get(column, set())
            if unknown_ids:
                errors.append(f"{filename}: unknown {column} {len(unknown_ids)} values")

    if errors:
        raise ValueError("Split CSV validation failed:\n- " + "\n- ".join(errors))


def _split_node_records(table: pd.DataFrame, id_column: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for raw in table.to_dict(orient="records"):
        record: dict[str, Any] = {"id": _text(raw[id_column])}
        for column, value in raw.items():
            if column == id_column:
                continue
            if column == "month":
                record[column] = int(value)
            elif column in SPLIT_NUMERIC_COLUMNS:
                record[_camel_case(column)] = _number(value)
            else:
                record[_camel_case(column)] = _text(value)
        records.append(record)
    return records


def _upsert_split_nodes(
    conn: Neo4j_Connection,
    tables: dict[str, pd.DataFrame],
) -> None:
    for filename, (label, id_column) in SPLIT_NODE_SPECS.items():
        records = _split_node_records(tables[filename], id_column)
        extra_label_set = "node:FoodGuide," if label == "Ingredient" else ""
        query = f"""
        UNWIND $rows AS row
        MERGE (node:{label} {{id: row.id}})
        SET {extra_label_set}
            node += row,
            node.foodGuideManaged = true
        """
        for batch in tqdm(_chunks(records, BATCH_SIZE), desc=f"{label} upsert"):
            conn.execute_write(query, {"rows": batch})


def _upsert_split_relationships(
    conn: Neo4j_Connection,
    tables: dict[str, pd.DataFrame],
) -> None:
    for filename, (from_label, from_column, relationship, to_label, to_column) in SPLIT_RELATION_SPECS.items():
        rows = [
            {"fromId": _text(row[from_column]), "toId": _text(row[to_column])}
            for row in tables[filename].to_dict(orient="records")
        ]
        query = f"""
        UNWIND $rows AS row
        MATCH (source:{from_label} {{id: row.fromId}})
        MATCH (target:{to_label} {{id: row.toId}})
        MERGE (source)-[:{relationship}]->(target)
        """
        for batch in tqdm(_chunks(rows, BATCH_SIZE), desc=f"{relationship} upsert"):
            conn.execute_write(query, {"rows": batch})


def _chunks(rows: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [rows[index : index + size] for index in range(0, len(rows), size)]


def load_food_guide_to_neo4j(csv_path: str | Path, clear: bool = False) -> dict[str, int]:
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"Food guide CSV not found: {csv_path}")

    settings = load_settings()
    df = pd.read_csv(csv_path)
    records = [build_food_guide_record(row, index) for index, row in df.iterrows()]
    if any(record["guideKey"] is None for record in records):
        raise ValueError("Food guide category path must include major, middle, and minor categories")

    logger.info("Food guide CSV loaded: %s (%d rows)", csv_path, len(records))

    conn = Neo4j_Connection(
        settings.uri,
        settings.user,
        settings.password,
        database=settings.database,
    )
    try:
        for query in DROP_LEGACY_CONSTRAINT_QUERIES:
            conn.execute_write(query)

        for query in CONSTRAINT_QUERIES:
            conn.execute_write(query)

        if clear:
            conn.execute_write(CLEAR_FOOD_GUIDE_QUERY)
            conn.execute_write(CLEAR_MANAGED_DETAIL_NODES_QUERY)
            logger.info("Existing FoodGuide data cleared")

        for batch in tqdm(_chunks(records, BATCH_SIZE), desc="FoodGuide upsert"):
            conn.execute_write(UPSERT_FOOD_GUIDE_QUERY, {"rows": batch})

        summary = conn.execute_single(
            """
            MATCH (g:FoodGuide)
            OPTIONAL MATCH (c:FoodCategory)
            RETURN count(DISTINCT g) AS foodGuides,
                   count(DISTINCT c) AS categories
            """
        )
    finally:
        conn.close()

    result = {
        "food_guides": int(summary["foodGuides"]),
        "categories": int(summary["categories"]),
    }
    logger.info("Food guide Neo4j load complete: %s", result)
    return result


def load_split_food_guide_to_neo4j(
    split_dir: str | Path,
    clear: bool = False,
) -> dict[str, int]:
    split_dir = Path(split_dir)
    if not split_dir.is_dir():
        raise FileNotFoundError(f"Food guide split CSV directory not found: {split_dir}")

    tables = _read_split_tables(split_dir)
    _validate_split_tables(tables)
    logger.info("Split CSV validation complete: %s", split_dir)

    settings = load_settings()
    conn = Neo4j_Connection(
        settings.uri,
        settings.user,
        settings.password,
        database=settings.database,
    )
    try:
        for query in SPLIT_CONSTRAINT_QUERIES:
            conn.execute_write(query)

        if clear:
            conn.execute_write(CLEAR_SPLIT_FOOD_GUIDE_QUERY)
            logger.info("Existing food guide graph cleared")

        _upsert_split_nodes(conn, tables)
        _upsert_split_relationships(conn, tables)
        for query in SPLIT_COMPATIBILITY_QUERIES:
            conn.execute_write(query)

        summary_rows = conn.execute_query(
            """
            CALL () {
              MATCH (n:MajorCategory) RETURN "MajorCategory" AS node, count(n) AS count
              UNION ALL MATCH (n:MiddleCategory) RETURN "MiddleCategory" AS node, count(n) AS count
              UNION ALL MATCH (n:Ingredient) RETURN "Ingredient" AS node, count(n) AS count
              UNION ALL MATCH (n:Guide) RETURN "Guide" AS node, count(n) AS count
              UNION ALL MATCH (n:Source) RETURN "Source" AS node, count(n) AS count
              UNION ALL MATCH (n:Alias) RETURN "Alias" AS node, count(n) AS count
              UNION ALL MATCH (n:SeasonMonth) RETURN "SeasonMonth" AS node, count(n) AS count
              UNION ALL MATCH (n:Nutrition) RETURN "Nutrition" AS node, count(n) AS count
            }
            RETURN node, count
            """
        )
    finally:
        conn.close()

    result = {row["node"]: int(row["count"]) for row in summary_rows}
    logger.info("Split food guide Neo4j load complete: %s", result)
    return result
