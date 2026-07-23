from __future__ import annotations

import csv
import io
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2 import sql

from app.backend.core.config import settings


_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_FOOD_GUIDE_BATCH_SIZE = 200
_FOOD_GUIDE_NODE_SPECS = {
    "nodes_major_category.csv": ("MajorCategory", "major_id"),
    "nodes_middle_category.csv": ("MiddleCategory", "middle_id"),
    "nodes_ingredient.csv": ("Ingredient", "ingredient_id"),
    "nodes_guide.csv": ("Guide", "guide_id"),
    "nodes_source.csv": ("Source", "source_id"),
    "nodes_alias.csv": ("Alias", "alias_id"),
    "nodes_season_month.csv": ("SeasonMonth", "month_id"),
    "nodes_nutrition.csv": ("Nutrition", "nutrition_id"),
}
_FOOD_GUIDE_RELATION_SPECS = {
    "rel_major_has_middle.csv": (
        "MajorCategory",
        "major_id",
        "HAS_MIDDLE",
        "MiddleCategory",
        "middle_id",
    ),
    "rel_middle_has_ingredient.csv": (
        "MiddleCategory",
        "middle_id",
        "HAS_INGREDIENT",
        "Ingredient",
        "ingredient_id",
    ),
    "rel_ingredient_has_guide.csv": (
        "Ingredient",
        "ingredient_id",
        "HAS_GUIDE",
        "Guide",
        "guide_id",
    ),
    "rel_guide_sourced_from.csv": (
        "Guide",
        "guide_id",
        "SOURCED_FROM",
        "Source",
        "source_id",
    ),
    "rel_ingredient_has_alias.csv": (
        "Ingredient",
        "ingredient_id",
        "HAS_ALIAS",
        "Alias",
        "alias_id",
    ),
    "rel_ingredient_in_season.csv": (
        "Ingredient",
        "ingredient_id",
        "IN_SEASON",
        "SeasonMonth",
        "month_id",
    ),
    "rel_ingredient_has_nutrition.csv": (
        "Ingredient",
        "ingredient_id",
        "HAS_NUTRITION",
        "Nutrition",
        "nutrition_id",
    ),
    "rel_nutrition_sourced_from.csv": (
        "Nutrition",
        "nutrition_id",
        "SOURCED_FROM",
        "Source",
        "source_id",
    ),
}
_FOOD_GUIDE_NUMERIC_COLUMNS = {
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
_FOOD_GUIDE_CONSTRAINTS = tuple(
    f"CREATE CONSTRAINT food_guide_{label.lower()}_id IF NOT EXISTS "
    f"FOR (n:{label}) REQUIRE n.id IS UNIQUE"
    for label, _ in _FOOD_GUIDE_NODE_SPECS.values()
)
_FOOD_GUIDE_CLEAR_QUERY = """
MATCH (n)
WHERE n:FoodGuide OR n:FoodCategory OR n.foodGuideManaged = true
DETACH DELETE n
"""
_FOOD_GUIDE_COMPATIBILITY_QUERIES = (
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


@dataclass(frozen=True)
class S3Object:
    bucket: str
    key: str


class S3SeedSource:
    def __init__(self, bucket: str) -> None:
        import boto3

        self.bucket = bucket
        self.client = boto3.client("s3", region_name=settings.AWS_REGION)

    def read_text(self, key: str) -> str:
        body = self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        return body.decode("utf-8-sig")

    def describe(self, key: str) -> str:
        return f"s3://{self.bucket}/{key}"


class LocalSeedSource:
    def __init__(self, root: str) -> None:
        self.root = Path(root).resolve()

    def read_text(self, key: str) -> str:
        path = (self.root / key).resolve()
        if path != self.root and self.root not in path.parents:
            raise ValueError(f"seed key escapes SEED_DATA_DIR: {key}")
        return path.read_text(encoding="utf-8-sig")

    def describe(self, key: str) -> str:
        return str(self.root / key)


def run_seed_import() -> None:
    source_type = os.getenv("SEED_DATA_SOURCE", "s3").strip().lower()
    if source_type == "s3":
        source = S3SeedSource(_required_env("SEED_DATA_BUCKET"))
        default_prefix = "prod/"
    elif source_type == "local":
        source = LocalSeedSource(_required_env("SEED_DATA_DIR"))
        default_prefix = ""
    else:
        raise RuntimeError("SEED_DATA_SOURCE must be s3 or local")

    prefix = _normalize_prefix(os.getenv("SEED_DATA_PREFIX", default_prefix))
    manifest_key = os.getenv("SEED_MANIFEST_KEY") or f"{prefix}manifest.json"
    manifest = json.loads(source.read_text(manifest_key))

    with psycopg2.connect(settings.DATABASE_URL) as connection:
        for entry in manifest.get("postgres_sql", []):
            _run_postgres_sql(connection, source, prefix, entry)
        for entry in manifest.get("postgres_csv", []):
            _run_postgres_csv(connection, source, prefix, entry)

    neo4j_entries = manifest.get("neo4j_cypher", [])
    if neo4j_entries:
        _run_neo4j_cypher(source, prefix, neo4j_entries)

    food_guide_entries = manifest.get("neo4j_food_guide", [])
    if food_guide_entries:
        _run_neo4j_food_guide(source, prefix, food_guide_entries)


def _run_postgres_sql(connection, source, prefix: str, entry: dict[str, Any]) -> None:
    key = _object_key(prefix, entry["key"])
    statement = source.read_text(key)
    with connection.cursor() as cursor:
        cursor.execute(statement)
    connection.commit()
    print(f"postgres_sql imported: {source.describe(key)}")


def _run_postgres_csv(connection, source, prefix: str, entry: dict[str, Any]) -> None:
    table = _table_name(entry["table"])
    mode = entry.get("mode", "skip_if_not_empty")
    key = _object_key(prefix, entry["key"])
    csv_text = source.read_text(key)
    columns = entry.get("columns") or _csv_header(csv_text)
    _validate_identifiers(columns)

    with connection.cursor() as cursor:
        if mode == "skip_if_not_empty" and _table_has_rows(cursor, table):
            print(f"postgres_csv skipped non-empty table: {table}")
            return
        if mode == "truncate":
            cursor.execute(
                sql.SQL("TRUNCATE TABLE {} RESTART IDENTITY CASCADE").format(
                    _table_sql(table)
                )
            )
        elif mode not in {"append", "skip_if_not_empty"}:
            raise ValueError(f"unsupported postgres_csv mode: {mode}")

        query = sql.SQL("COPY {} ({}) FROM STDIN WITH (FORMAT CSV, HEADER TRUE)").format(
            _table_sql(table),
            sql.SQL(", ").join(sql.Identifier(column) for column in columns),
        )
        cursor.copy_expert(query, io.StringIO(csv_text))
        if "id" in columns:
            _reset_id_sequence(cursor, table)
    connection.commit()
    print(f"postgres_csv imported: {source.describe(key)} -> {table}")


def _run_neo4j_cypher(source, prefix: str, entries: list[dict[str, Any]]) -> None:
    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
    )
    try:
        with driver.session(database=settings.NEO4J_DATABASE) as session:
            for entry in entries:
                key = _object_key(prefix, entry["key"])
                cypher_text = source.read_text(key)
                for statement in _split_cypher_statements(cypher_text):
                    session.run(statement).consume()
                print(f"neo4j_cypher imported: {source.describe(key)}")
    finally:
        driver.close()


def _run_neo4j_food_guide(source, prefix: str, entries: list[dict[str, Any]]) -> None:
    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
    )
    try:
        with driver.session(database=settings.NEO4J_DATABASE) as session:
            for entry in entries:
                _run_neo4j_food_guide_entry(session, source, prefix, entry)
    finally:
        driver.close()


def _run_neo4j_food_guide_entry(session, source, prefix: str, entry: dict[str, Any]) -> None:
    guide_prefix = _normalize_prefix(entry.get("prefix", "food_guide/"))
    tables = {
        filename: _read_seed_csv(source, _object_key(prefix, f"{guide_prefix}{filename}"))
        for filename in (*_FOOD_GUIDE_NODE_SPECS, *_FOOD_GUIDE_RELATION_SPECS)
    }
    _validate_food_guide_tables(tables)

    for query in _FOOD_GUIDE_CONSTRAINTS:
        session.run(query).consume()
    if entry.get("clear"):
        session.run(_FOOD_GUIDE_CLEAR_QUERY).consume()

    for filename, (label, id_column) in _FOOD_GUIDE_NODE_SPECS.items():
        rows = _food_guide_node_records(tables[filename], id_column)
        extra_label = "node:FoodGuide,\n            " if label == "Ingredient" else ""
        query = f"""
        UNWIND $rows AS row
        MERGE (node:{label} {{id: row.id}})
        SET {extra_label}node += row,
            node.foodGuideManaged = true
        """
        _run_neo4j_batches(session, query, rows)
        print(f"neo4j_food_guide nodes imported: {label}={len(rows)}")

    for filename, (from_label, from_column, relation, to_label, to_column) in _FOOD_GUIDE_RELATION_SPECS.items():
        rows = [
            {
                "fromId": _text(row.get(from_column)),
                "toId": _text(row.get(to_column)),
            }
            for row in tables[filename]
        ]
        query = f"""
        UNWIND $rows AS row
        MATCH (source:{from_label} {{id: row.fromId}})
        MATCH (target:{to_label} {{id: row.toId}})
        MERGE (source)-[:{relation}]->(target)
        """
        _run_neo4j_batches(session, query, rows)
        print(f"neo4j_food_guide relationships imported: {relation}={len(rows)}")

    for query in _FOOD_GUIDE_COMPATIBILITY_QUERIES:
        session.run(query).consume()
    print(f"neo4j_food_guide imported from {source.describe(_object_key(prefix, guide_prefix))}")


def _read_seed_csv(source, key: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(source.read_text(key))))


def _read_s3_csv(s3, obj: S3Object) -> list[dict[str, str]]:
    text = _read_s3_text(s3, obj)
    return list(csv.DictReader(io.StringIO(text)))


def _read_s3_text(s3, obj: S3Object) -> str:
    body = s3.get_object(Bucket=obj.bucket, Key=obj.key)["Body"].read()
    return body.decode("utf-8-sig")


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def _normalize_prefix(prefix: str) -> str:
    normalized = prefix.strip().strip("/")
    return f"{normalized}/" if normalized else ""


def _object_key(prefix: str, key: str) -> str:
    cleaned = key.strip().lstrip("/")
    if cleaned.startswith("s3://"):
        raise ValueError("manifest keys must be relative S3 keys")
    return f"{prefix}{cleaned}"


def _table_name(value: str) -> str:
    parts = value.split(".")
    if not 1 <= len(parts) <= 2:
        raise ValueError(f"invalid table name: {value}")
    _validate_identifiers(parts)
    return value


def _validate_identifiers(values: list[str]) -> None:
    for value in values:
        if not _IDENTIFIER.match(value):
            raise ValueError(f"invalid SQL identifier: {value}")


def _table_sql(table: str) -> sql.Composable:
    parts = table.split(".")
    return sql.SQL(".").join(sql.Identifier(part) for part in parts)


def _csv_header(csv_text: str) -> list[str]:
    reader = csv.reader(io.StringIO(csv_text))
    try:
        header = next(reader)
    except StopIteration as exc:
        raise ValueError("CSV file is empty") from exc
    return [column.strip() for column in header]


def _table_has_rows(cursor, table: str) -> bool:
    cursor.execute(sql.SQL("SELECT EXISTS (SELECT 1 FROM {} LIMIT 1)").format(_table_sql(table)))
    return bool(cursor.fetchone()[0])


def _reset_id_sequence(cursor, table: str) -> None:
    cursor.execute("SELECT pg_get_serial_sequence(%s, 'id')", (table,))
    sequence = cursor.fetchone()[0]
    if not sequence:
        return
    cursor.execute(
        sql.SQL(
            "SELECT setval(%s, COALESCE((SELECT MAX(id) FROM {}), 1), "
            "EXISTS (SELECT 1 FROM {}))"
        ).format(_table_sql(table), _table_sql(table)),
        (sequence,),
    )


def _split_cypher_statements(cypher_text: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    for line in cypher_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue
        current.append(line)
        if stripped.endswith(";"):
            statement = "\n".join(current).rstrip().rstrip(";").strip()
            if statement:
                statements.append(statement)
            current = []
    tail = "\n".join(current).strip()
    if tail:
        statements.append(tail)
    return statements


def _validate_food_guide_tables(tables: dict[str, list[dict[str, str]]]) -> None:
    ids_by_column: dict[str, set[str]] = {}
    errors: list[str] = []

    for filename, (_, id_column) in _FOOD_GUIDE_NODE_SPECS.items():
        rows = tables[filename]
        ids: list[str] = []
        for row in rows:
            value = _text(row.get(id_column))
            if value is None:
                errors.append(f"{filename}: blank {id_column}")
            else:
                ids.append(value)
        duplicate_count = len(ids) - len(set(ids))
        if duplicate_count:
            errors.append(f"{filename}: duplicate {id_column} {duplicate_count} rows")
        ids_by_column[id_column] = set(ids)

    for filename, (_, from_column, relation, _, to_column) in _FOOD_GUIDE_RELATION_SPECS.items():
        rows = tables[filename]
        seen: set[tuple[str | None, str | None]] = set()
        duplicate_count = 0
        for row in rows:
            if row.get("relationship", "").strip() != relation:
                errors.append(f"{filename}: invalid relationship {row.get('relationship')}")
            pair = (_text(row.get(from_column)), _text(row.get(to_column)))
            if pair in seen:
                duplicate_count += 1
            seen.add(pair)
            for column, value in ((from_column, pair[0]), (to_column, pair[1])):
                if value is None:
                    errors.append(f"{filename}: blank {column}")
                elif value not in ids_by_column.get(column, set()):
                    errors.append(f"{filename}: unknown {column} {value}")
        if duplicate_count:
            errors.append(f"{filename}: duplicate relationship {duplicate_count} rows")

    if errors:
        raise ValueError("food guide CSV validation failed:\n- " + "\n- ".join(errors[:50]))


def _food_guide_node_records(rows: list[dict[str, str]], id_column: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in rows:
        record: dict[str, Any] = {"id": _text(row[id_column])}
        for column, value in row.items():
            if column == id_column:
                continue
            if column == "month":
                text = _text(value)
                record[column] = int(text) if text is not None else None
            elif column in _FOOD_GUIDE_NUMERIC_COLUMNS:
                record[_camel_case(column)] = _number(value)
            else:
                record[_camel_case(column)] = _text(value)
        records.append(record)
    return records


def _run_neo4j_batches(session, query: str, rows: list[dict[str, Any]]) -> None:
    for index in range(0, len(rows), _FOOD_GUIDE_BATCH_SIZE):
        batch = rows[index : index + _FOOD_GUIDE_BATCH_SIZE]
        session.run(query, {"rows": batch}).consume()


def _text(value: Any) -> str | None:
    if value is None:
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


def main() -> None:
    run_seed_import()


if __name__ == "__main__":
    main()
