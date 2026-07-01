from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd
from tqdm import tqdm

from etl.load_to_neo4j.neo4j_connection import Neo4j_Connection, load_settings

logger = logging.getLogger(__name__)

BATCH_SIZE = 100

NODE_SPECS = {
    "nodes_major_category.csv": ("MajorCategory", "major_id"),
    "nodes_middle_category.csv": ("MiddleCategory", "middle_id"),
    "nodes_ingredient.csv": ("Ingredient", "ingredient_id"),
    "nodes_guide.csv": ("Guide", "guide_id"),
    "nodes_source.csv": ("Source", "source_id"),
    "nodes_alias.csv": ("Alias", "alias_id"),
    "nodes_season_month.csv": ("SeasonMonth", "month_id"),
    "nodes_nutrition.csv": ("Nutrition", "nutrition_id"),
}

RELATION_SPECS = {
    "rel_major_has_middle.csv": (
        "MajorCategory", "major_id", "HAS_MIDDLE", "MiddleCategory", "middle_id"
    ),
    "rel_middle_has_ingredient.csv": (
        "MiddleCategory", "middle_id", "HAS_INGREDIENT", "Ingredient", "ingredient_id"
    ),
    "rel_ingredient_has_guide.csv": (
        "Ingredient", "ingredient_id", "HAS_GUIDE", "Guide", "guide_id"
    ),
    "rel_guide_sourced_from.csv": (
        "Guide", "guide_id", "SOURCED_FROM", "Source", "source_id"
    ),
    "rel_ingredient_has_alias.csv": (
        "Ingredient", "ingredient_id", "HAS_ALIAS", "Alias", "alias_id"
    ),
    "rel_ingredient_in_season.csv": (
        "Ingredient", "ingredient_id", "IN_SEASON", "SeasonMonth", "month_id"
    ),
    "rel_ingredient_has_nutrition.csv": (
        "Ingredient", "ingredient_id", "HAS_NUTRITION", "Nutrition", "nutrition_id"
    ),
    "rel_nutrition_sourced_from.csv": (
        "Nutrition", "nutrition_id", "SOURCED_FROM", "Source", "source_id"
    ),
}

CONSTRAINT_QUERIES = tuple(
    f"CREATE CONSTRAINT food_guide_{label.lower()}_id IF NOT EXISTS "
    f"FOR (n:{label}) REQUIRE n.id IS UNIQUE"
    for label, _ in NODE_SPECS.values()
)

NUMERIC_COLUMNS = {
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

CLEAR_QUERY = """
MATCH (n)
WHERE n:FoodGuide OR n:FoodCategory OR n.foodGuideManaged = true
DETACH DELETE n
"""

COMPATIBILITY_QUERIES = (
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


def _text(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def _number(value: Any) -> float | None:
    text = _text(value)
    if text is None or text in {"-", "Tr", "trace"}:
        return None
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return None


def _camel_case(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


def _chunks(rows: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    return [rows[index : index + BATCH_SIZE] for index in range(0, len(rows), BATCH_SIZE)]


def _read_tables(split_dir: Path) -> dict[str, pd.DataFrame]:
    required_files = (*NODE_SPECS, *RELATION_SPECS)
    missing_files = [name for name in required_files if not (split_dir / name).is_file()]
    if missing_files:
        raise FileNotFoundError(f"Missing split CSV files: {', '.join(missing_files)}")
    return {
        name: pd.read_csv(split_dir / name, dtype=str, keep_default_na=False, encoding="utf-8-sig")
        for name in required_files
    }


def _validate_tables(tables: dict[str, pd.DataFrame]) -> None:
    ids_by_column: dict[str, set[str]] = {}
    errors: list[str] = []

    for filename, (_, id_column) in NODE_SPECS.items():
        table = tables[filename]
        if id_column not in table.columns:
            errors.append(f"{filename}: missing column {id_column}")
            continue
        ids = table[id_column].str.strip()
        if (ids == "").any():
            errors.append(f"{filename}: blank {id_column}")
        if duplicate_count := int(ids.duplicated().sum()):
            errors.append(f"{filename}: duplicate {id_column} {duplicate_count} rows")
        ids_by_column[id_column] = set(ids)

    for filename, (_, from_column, relation, _, to_column) in RELATION_SPECS.items():
        table = tables[filename]
        required_columns = {from_column, to_column, "relationship"}
        missing_columns = required_columns - set(table.columns)
        if missing_columns:
            errors.append(f"{filename}: missing columns {', '.join(sorted(missing_columns))}")
            continue
        if invalid_count := int((table["relationship"].str.strip() != relation).sum()):
            errors.append(f"{filename}: invalid relationship {invalid_count} rows")
        if duplicate_count := int(table.duplicated([from_column, to_column]).sum()):
            errors.append(f"{filename}: duplicate relationship {duplicate_count} rows")
        for column in (from_column, to_column):
            unknown_ids = set(table[column].str.strip()) - ids_by_column.get(column, set())
            if unknown_ids:
                errors.append(f"{filename}: unknown {column} {len(unknown_ids)} values")

    if errors:
        raise ValueError("Split CSV validation failed:\n- " + "\n- ".join(errors))


def _node_records(table: pd.DataFrame, id_column: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for raw in table.to_dict(orient="records"):
        record: dict[str, Any] = {"id": _text(raw[id_column])}
        for column, value in raw.items():
            if column == id_column:
                continue
            if column == "month":
                record[column] = int(value)
            elif column in NUMERIC_COLUMNS:
                record[_camel_case(column)] = _number(value)
            else:
                record[_camel_case(column)] = _text(value)
        records.append(record)
    return records


def _upsert_nodes(conn: Neo4j_Connection, tables: dict[str, pd.DataFrame]) -> None:
    for filename, (label, id_column) in NODE_SPECS.items():
        extra_label = "node:FoodGuide," if label == "Ingredient" else ""
        query = f"""
        UNWIND $rows AS row
        MERGE (node:{label} {{id: row.id}})
        SET {extra_label}
            node += row,
            node.foodGuideManaged = true
        """
        for batch in tqdm(_chunks(_node_records(tables[filename], id_column)), desc=f"{label} upsert"):
            conn.execute_write(query, {"rows": batch})


def _upsert_relationships(conn: Neo4j_Connection, tables: dict[str, pd.DataFrame]) -> None:
    for filename, (from_label, from_column, relation, to_label, to_column) in RELATION_SPECS.items():
        rows = [
            {"fromId": _text(row[from_column]), "toId": _text(row[to_column])}
            for row in tables[filename].to_dict(orient="records")
        ]
        query = f"""
        UNWIND $rows AS row
        MATCH (source:{from_label} {{id: row.fromId}})
        MATCH (target:{to_label} {{id: row.toId}})
        MERGE (source)-[:{relation}]->(target)
        """
        for batch in tqdm(_chunks(rows), desc=f"{relation} upsert"):
            conn.execute_write(query, {"rows": batch})


def load_split_food_guide_to_neo4j(split_dir: str | Path, clear: bool = False) -> dict[str, int]:
    split_dir = Path(split_dir)
    if not split_dir.is_dir():
        raise FileNotFoundError(f"Food guide split CSV directory not found: {split_dir}")

    tables = _read_tables(split_dir)
    _validate_tables(tables)
    logger.info("Split CSV validation complete: %s", split_dir)

    settings = load_settings()
    conn = Neo4j_Connection(
        settings.uri,
        settings.user,
        settings.password,
        database=settings.database,
    )
    try:
        for query in CONSTRAINT_QUERIES:
            conn.execute_write(query)
        if clear:
            conn.execute_write(CLEAR_QUERY)
            logger.info("Existing food guide graph cleared")
        _upsert_nodes(conn, tables)
        _upsert_relationships(conn, tables)
        for query in COMPATIBILITY_QUERIES:
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
