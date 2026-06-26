from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import pandas as pd
from neo4j import GraphDatabase
from tqdm import tqdm

from .config import load_settings

logger = logging.getLogger(__name__)

BATCH_SIZE = 100

DROP_LEGACY_CONSTRAINT_QUERIES = (
    "DROP CONSTRAINT food_category_key IF EXISTS",
)

CONSTRAINT_QUERIES = (
    "CREATE CONSTRAINT food_guide_code IF NOT EXISTS FOR (g:FoodGuide) REQUIRE g.code IS UNIQUE",
    "CREATE CONSTRAINT food_category_key IF NOT EXISTS FOR (c:FoodCategory) REQUIRE c.key IS UNIQUE",
)

CLEAR_FOOD_GUIDE_QUERY = """
MATCH (g:FoodGuide)
DETACH DELETE g
WITH 1 AS _
MATCH (c:FoodCategory)
WHERE NOT (c)--()
DELETE c
"""

UPSERT_FOOD_GUIDE_QUERY = """
UNWIND $rows AS row
MERGE (g:FoodGuide {code: row.code})
SET g.name = row.name,
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
  MERGE (g)-[:IN_CATEGORY {level: "major"}]->(major)
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
  MERGE (g)-[:IN_CATEGORY {level: "middle"}]->(middle)
)
FOREACH (_ IN CASE WHEN row.minorKey IS NULL THEN [] ELSE [1] END |
  MERGE (middle:FoodCategory {key: row.middleKey})
  SET middle.level = "middle",
      middle.name = row.middleCategory,
      middle.path = row.middlePath,
      middle.displayName = row.middleDisplayName
  MERGE (minor:FoodCategory {key: row.minorKey})
  SET minor.level = "minor",
      minor.name = row.minorCategory,
      minor.path = row.minorPath,
      minor.displayName = row.minorDisplayName
  MERGE (middle)-[:HAS_SUBCATEGORY]->(minor)
  MERGE (g)-[:IN_CATEGORY {level: "minor"}]->(minor)
)
"""


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
    return {
        "code": code,
        "majorCategory": major_category,
        "middleCategory": middle_category,
        "minorCategory": minor_category,
        "majorKey": _category_key("major", major_category),
        "middleKey": _category_key("middle", major_category, middle_category),
        "minorKey": _category_key("minor", major_category, middle_category, minor_category),
        "majorPath": major_path,
        "middlePath": middle_path,
        "minorPath": minor_path,
        "middleDisplayName": " > ".join(middle_path) if middle_path else middle_category,
        "minorDisplayName": " > ".join(minor_path) if minor_path else minor_category,
        "name": _text(_get(row, "영양식품명")) or _text(_get(row, "대표식품명")) or code,
        "representativeName": _text(_get(row, "대표식품명")),
        "rawName": _text(_get(row, "원재료명")),
        "aliases": _aliases(_get(row, "원재료명이명")),
        "existingDisplayName": _text(_get(row, "기존표시명")),
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
    }


def _chunks(rows: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [rows[index : index + size] for index in range(0, len(rows), size)]


def load_food_guide_to_neo4j(csv_path: str | Path, clear: bool = False) -> dict[str, int]:
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"Food guide CSV not found: {csv_path}")

    settings = load_settings()
    df = pd.read_csv(csv_path)
    records = [build_food_guide_record(row, index) for index, row in df.iterrows()]

    logger.info("Food guide CSV loaded: %s (%d rows)", csv_path, len(records))

    driver = GraphDatabase.driver(settings.uri, auth=(settings.user, settings.password))
    try:
        with driver.session(database=settings.database) as session:
            for query in DROP_LEGACY_CONSTRAINT_QUERIES:
                session.run(query).consume()

            for query in CONSTRAINT_QUERIES:
                session.run(query).consume()

            if clear:
                session.run(CLEAR_FOOD_GUIDE_QUERY).consume()
                logger.info("Existing FoodGuide data cleared")

            for batch in tqdm(_chunks(records, BATCH_SIZE), desc="FoodGuide upsert"):
                session.run(UPSERT_FOOD_GUIDE_QUERY, rows=batch).consume()

            summary = session.run(
                """
                MATCH (g:FoodGuide)
                OPTIONAL MATCH (c:FoodCategory)
                RETURN count(DISTINCT g) AS foodGuides,
                       count(DISTINCT c) AS categories
                """
            ).single()
    finally:
        driver.close()

    result = {
        "food_guides": int(summary["foodGuides"]),
        "categories": int(summary["categories"]),
    }
    logger.info("Food guide Neo4j load complete: %s", result)
    return result
