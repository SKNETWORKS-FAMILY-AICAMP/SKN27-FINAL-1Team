from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import time
from pathlib import Path
from typing import Any, Iterable

import psycopg2
from neo4j import GraphDatabase
from psycopg2.extras import execute_values


ROOT = Path(os.getenv("PROJECT_ROOT", "/project"))
FOOD_DIR = ROOT / "storage" / "processed" / "food_guide"
RECIPE_DIR = ROOT / "storage" / "processed" / "recipe"

EXCLUDED_ALIASES = {"야채", "채소", "재료", "소스", "양념"}
COMMON_ALIAS_GROUPS = [
    ("마늘", "양파", "대파"),
    ("마늘", "양파", "고추"),
    ("마늘", "간장", "참기름"),
    ("소금", "후추", "마늘"),
    ("고춧가루", "간장", "마늘"),
]


PG_QUERIES = {
    "simple": """
        SELECT ingredient_id, name, display_name, classification
        FROM bench_ingredients
        WHERE ingredient_id = %s
    """,
    "alias": """
        SELECT i.ingredient_id, i.name AS ingredient_name
        FROM bench_aliases a
        JOIN bench_ingredient_aliases ia ON ia.alias_id = a.alias_id
        JOIN bench_ingredients i ON i.ingredient_id = ia.ingredient_id
        WHERE a.name = %s
        ORDER BY i.ingredient_id
        LIMIT 20
    """,
    "expanded": """
        SELECT i.ingredient_id, i.name AS ingredient_name,
               r.recipe_id, r.name AS recipe_name, r.review_rank_score
        FROM bench_aliases input_alias
        JOIN bench_ingredient_aliases input_ia ON input_ia.alias_id = input_alias.alias_id
        JOIN bench_ingredients i ON i.ingredient_id = input_ia.ingredient_id
        JOIN bench_ingredient_aliases all_ia ON all_ia.ingredient_id = i.ingredient_id
        JOIN bench_recipe_aliases ra ON ra.alias_id = all_ia.alias_id
        JOIN bench_recipes r ON r.recipe_id = ra.recipe_id
        WHERE input_alias.name = %s
        GROUP BY i.ingredient_id, i.name, r.recipe_id, r.name, r.review_rank_score
        ORDER BY r.review_rank_score DESC NULLS LAST, r.recipe_id DESC
        LIMIT 20
    """,
    "common": """
        WITH input_aliases(name) AS (
          VALUES (%s), (%s), (%s)
        ),
        input_ingredients AS (
          SELECT DISTINCT i.ingredient_id
          FROM input_aliases input
          JOIN bench_aliases a ON a.name = input.name
          JOIN bench_ingredient_aliases ia ON ia.alias_id = a.alias_id
          JOIN bench_ingredients i ON i.ingredient_id = ia.ingredient_id
        )
        SELECT 'common' AS ingredient_id,
               r.recipe_id,
               r.name AS recipe_name,
               r.review_rank_score
        FROM input_ingredients ii
        JOIN bench_ingredient_aliases all_ia ON all_ia.ingredient_id = ii.ingredient_id
        JOIN bench_recipe_aliases ra ON ra.alias_id = all_ia.alias_id
        JOIN bench_recipes r ON r.recipe_id = ra.recipe_id
        GROUP BY r.recipe_id, r.name, r.review_rank_score
        HAVING count(DISTINCT ii.ingredient_id) = (SELECT count(*) FROM input_ingredients)
        ORDER BY r.review_rank_score DESC NULLS LAST, r.recipe_id DESC
        LIMIT 20
    """,
}

NEO4J_QUERIES = {
    "simple": """
        MATCH (i:Ingredient {id: $target})
        RETURN i.id AS ingredient_id,
               i.name AS ingredient_name,
               i.displayName AS display_name,
               i.classification AS classification
    """,
    "alias": """
        MATCH (a:Alias {name: $target})<-[:HAS_ALIAS]-(i:Ingredient)
        RETURN i.id AS ingredient_id,
               i.name AS ingredient_name
        ORDER BY ingredient_id
        LIMIT 20
    """,
    "expanded": """
        MATCH (input:Alias {name: $target})<-[:HAS_ALIAS]-(i:Ingredient)
        MATCH (i)-[:HAS_ALIAS]->(:Alias)<-[:USES_ALIAS]-(r:Recipe)
        RETURN DISTINCT
               i.id AS ingredient_id,
               i.name AS ingredient_name,
               r.recipeId AS recipe_id,
               r.name AS recipe_name,
               r.reviewRankScore AS review_rank_score
        ORDER BY CASE WHEN review_rank_score IS NULL THEN 1 ELSE 0 END,
                 review_rank_score DESC,
                 recipe_id DESC
        LIMIT 20
    """,
    "common": """
        MATCH (input:Alias)
        WHERE input.name IN $target
        MATCH (input)<-[:HAS_ALIAS]-(i:Ingredient)
        WITH collect(DISTINCT i) AS ingredients
        UNWIND ingredients AS i
        MATCH (i)-[:HAS_ALIAS]->(:Alias)<-[:USES_ALIAS]-(r:Recipe)
        WITH r, ingredients, count(DISTINCT i) AS matched
        WHERE matched = size(ingredients)
        RETURN DISTINCT
               'common' AS ingredient_id,
               r.recipeId AS recipe_id,
               r.name AS recipe_name,
               r.reviewRankScore AS review_rank_score
        ORDER BY CASE WHEN review_rank_score IS NULL THEN 1 ELSE 0 END,
                 review_rank_score DESC,
                 recipe_id DESC
        LIMIT 20
    """,
}


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _chunks(rows: list[tuple], size: int = 1000) -> Iterable[list[tuple]]:
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


def _pg_conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "postgres"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME", "bobbeori_db"),
        user=os.getenv("DB_USER", "bobbeori_user"),
        password=os.getenv("DB_PASSWORD", "YOUR_SECURE_RDB_PASSWORD_HERE"),
    )


def setup_postgres() -> None:
    ingredients = _read_csv(FOOD_DIR / "nodes_ingredient.csv")
    aliases = _read_csv(FOOD_DIR / "nodes_alias.csv")
    ingredient_aliases = _read_csv(FOOD_DIR / "rel_ingredient_has_alias.csv")
    recipes = _read_csv(RECIPE_DIR / "recipe_fix.csv")
    recipe_alias_rows = _read_csv(RECIPE_DIR / "recipe_ingredient_alias.csv")

    recipe_rows = [
        (
            int(row["RCP_SNO"]),
            row.get("CKG_NM") or None,
            float(row["REVIEW_RANK_SCORE"]) if row.get("REVIEW_RANK_SCORE") else None,
        )
        for row in recipes
        if row.get("RCP_SNO")
    ]

    recipe_aliases: set[tuple[int, str]] = set()
    for row in recipe_alias_rows:
        recipe_id = row.get("RCP_SNO")
        if not recipe_id:
            continue
        for alias in json.loads(row.get("aliases_matched") or "[]"):
            alias_id = alias.get("alias_id") if isinstance(alias, dict) else None
            if alias_id:
                recipe_aliases.add((int(recipe_id), alias_id))

    with _pg_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            DROP TABLE IF EXISTS bench_recipe_aliases;
            DROP TABLE IF EXISTS bench_ingredient_aliases;
            DROP TABLE IF EXISTS bench_recipes;
            DROP TABLE IF EXISTS bench_aliases;
            DROP TABLE IF EXISTS bench_ingredients;

            CREATE TABLE bench_ingredients (
                ingredient_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                display_name TEXT,
                classification TEXT
            );
            CREATE TABLE bench_aliases (
                alias_id TEXT PRIMARY KEY,
                name TEXT NOT NULL
            );
            CREATE TABLE bench_recipes (
                recipe_id BIGINT PRIMARY KEY,
                name TEXT,
                review_rank_score DOUBLE PRECISION
            );
            CREATE TABLE bench_ingredient_aliases (
                ingredient_id TEXT NOT NULL REFERENCES bench_ingredients(ingredient_id),
                alias_id TEXT NOT NULL REFERENCES bench_aliases(alias_id),
                PRIMARY KEY (ingredient_id, alias_id)
            );
            CREATE TABLE bench_recipe_aliases (
                recipe_id BIGINT NOT NULL REFERENCES bench_recipes(recipe_id),
                alias_id TEXT NOT NULL REFERENCES bench_aliases(alias_id),
                PRIMARY KEY (recipe_id, alias_id)
            );
            """
        )
        execute_values(
            cur,
            "INSERT INTO bench_ingredients VALUES %s",
            [
                (
                    row["ingredient_id"],
                    row["name"],
                    row.get("display_name") or None,
                    row.get("classification") or None,
                )
                for row in ingredients
            ],
        )
        execute_values(cur, "INSERT INTO bench_aliases VALUES %s", [(row["alias_id"], row["name"]) for row in aliases])
        execute_values(cur, "INSERT INTO bench_recipes VALUES %s", recipe_rows)
        execute_values(
            cur,
            "INSERT INTO bench_ingredient_aliases VALUES %s ON CONFLICT DO NOTHING",
            [(row["ingredient_id"], row["alias_id"]) for row in ingredient_aliases],
        )
        for batch in _chunks(sorted(recipe_aliases)):
            execute_values(cur, "INSERT INTO bench_recipe_aliases VALUES %s ON CONFLICT DO NOTHING", batch)

        cur.execute(
            """
            CREATE INDEX idx_bench_aliases_name ON bench_aliases(name);
            CREATE INDEX idx_bench_ingredient_aliases_alias ON bench_ingredient_aliases(alias_id);
            CREATE INDEX idx_bench_ingredient_aliases_ingredient ON bench_ingredient_aliases(ingredient_id);
            CREATE INDEX idx_bench_recipe_aliases_alias ON bench_recipe_aliases(alias_id);
            CREATE INDEX idx_bench_recipe_aliases_recipe ON bench_recipe_aliases(recipe_id);
            CREATE INDEX idx_bench_recipes_score ON bench_recipes(review_rank_score DESC);
            ANALYZE bench_ingredients;
            ANALYZE bench_aliases;
            ANALYZE bench_recipes;
            ANALYZE bench_ingredient_aliases;
            ANALYZE bench_recipe_aliases;
            """
        )


def _percentile(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * pct)))
    return ordered[index]


def _stats(values: list[float]) -> dict[str, float]:
    return {
        "avg_ms": statistics.mean(values),
        "median_ms": statistics.median(values),
        "min_ms": min(values),
        "max_ms": max(values),
        "p95_ms": _percentile(values, 0.95),
    }


def _row_value(row: tuple | dict, key: str, index: int) -> Any:
    return row.get(key) if isinstance(row, dict) else row[index]


def _result_key(row: tuple | dict, scenario: str) -> tuple:
    if scenario == "simple":
        return (str(_row_value(row, "ingredient_id", 0)),)
    if scenario == "alias":
        return (str(_row_value(row, "ingredient_id", 0)),)
    if scenario == "common":
        return (int(_row_value(row, "recipe_id", 1)),)
    return (str(_row_value(row, "ingredient_id", 0)), int(_row_value(row, "recipe_id", 2)))


def select_aliases(limit: int) -> list[str]:
    with _pg_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT a.name, count(DISTINCT ra.recipe_id) AS recipe_count
            FROM bench_aliases a
            JOIN bench_ingredient_aliases ia ON ia.alias_id = a.alias_id
            JOIN bench_recipe_aliases ra ON ra.alias_id = a.alias_id
            WHERE a.name <> ALL(%s)
            GROUP BY a.name
            HAVING count(DISTINCT ra.recipe_id) >= 20
            ORDER BY recipe_count DESC, a.name
            LIMIT %s
            """,
            (list(EXCLUDED_ALIASES), limit),
        )
        return [row[0] for row in cur.fetchall()]


def select_ingredient_ids(limit: int) -> list[str]:
    with _pg_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT i.ingredient_id
            FROM bench_ingredients i
            JOIN bench_ingredient_aliases ia ON ia.ingredient_id = i.ingredient_id
            JOIN bench_recipe_aliases ra ON ra.alias_id = ia.alias_id
            GROUP BY i.ingredient_id
            ORDER BY count(DISTINCT ra.recipe_id) DESC, i.ingredient_id
            LIMIT %s
            """,
            (limit,),
        )
        return [row[0] for row in cur.fetchall()]


def scenario_targets(scenario: str, limit: int) -> list[Any]:
    if scenario == "simple":
        return select_ingredient_ids(limit)
    if scenario in {"alias", "expanded"}:
        return select_aliases(limit)
    if scenario == "common":
        return COMMON_ALIAS_GROUPS[:limit]
    raise ValueError(f"unknown scenario: {scenario}")


def _pg_params(scenario: str, target: Any) -> tuple:
    return tuple(target) if scenario == "common" else (target,)


def benchmark_pg(scenario: str, target: Any, runs: int, warmup: int) -> tuple[list[tuple], dict[str, float], list[float]]:
    timings: list[float] = []
    result_rows: list[tuple] = []
    with _pg_conn() as conn, conn.cursor() as cur:
        for i in range(runs + warmup):
            start = time.perf_counter()
            cur.execute(PG_QUERIES[scenario], _pg_params(scenario, target))
            rows = cur.fetchall()
            elapsed = (time.perf_counter() - start) * 1000
            if i >= warmup:
                timings.append(elapsed)
                result_rows = rows
    return result_rows, _stats(timings), timings


def benchmark_neo4j(scenario: str, target: Any, runs: int, warmup: int) -> tuple[list[dict], dict[str, float], list[float]]:
    uri = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "YOUR_SECURE_NEO4J_PASSWORD_HERE")
    database = os.getenv("NEO4J_DATABASE", "neo4j")
    timings: list[float] = []
    result_rows: list[dict] = []
    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with driver.session(database=database) as session:
            for i in range(runs + warmup):
                start = time.perf_counter()
                rows = [dict(record) for record in session.run(NEO4J_QUERIES[scenario], target=target)]
                elapsed = (time.perf_counter() - start) * 1000
                if i >= warmup:
                    timings.append(elapsed)
                    result_rows = rows
    finally:
        driver.close()
    return result_rows, _stats(timings), timings


def print_counts() -> None:
    with _pg_conn() as conn, conn.cursor() as cur:
        for table in (
            "bench_ingredients",
            "bench_aliases",
            "bench_recipes",
            "bench_ingredient_aliases",
            "bench_recipe_aliases",
        ):
            cur.execute(f"SELECT count(*) FROM {table}")
            print(f"{table}: {cur.fetchone()[0]}")


def run_scenario(scenario: str, runs: int, warmup: int, limit: int) -> bool:
    targets = scenario_targets(scenario, limit)
    print(f"scenario: {scenario}")
    print("targets:", ", ".join("/".join(t) if isinstance(t, tuple) else str(t) for t in targets))
    print("query,target,rows,avg_ms,p95_ms,min_ms,max_ms")
    pg_all_timings: list[float] = []
    neo4j_all_timings: list[float] = []
    validation_failures: list[str] = []

    for target in targets:
        pg_rows, pg, pg_timings = benchmark_pg(scenario, target, runs, warmup)
        neo_rows, neo, neo_timings = benchmark_neo4j(scenario, target, runs, warmup)
        pg_all_timings.extend(pg_timings)
        neo4j_all_timings.extend(neo_timings)

        pg_keys = [_result_key(row, scenario) for row in pg_rows]
        neo_keys = [_result_key(row, scenario) for row in neo_rows]
        target_label = "/".join(target) if isinstance(target, tuple) else str(target)
        if pg_keys != neo_keys:
            validation_failures.append(target_label)

        print(f"postgres,{target_label},{len(pg_rows)},{pg['avg_ms']:.3f},{pg['p95_ms']:.3f},{pg['min_ms']:.3f},{pg['max_ms']:.3f}")
        print(f"neo4j,{target_label},{len(neo_rows)},{neo['avg_ms']:.3f},{neo['p95_ms']:.3f},{neo['min_ms']:.3f},{neo['max_ms']:.3f}")

    pg_overall = _stats(pg_all_timings)
    neo4j_overall = _stats(neo4j_all_timings)
    print("overall,query,runs,avg_ms,median_ms,p95_ms,min_ms,max_ms")
    print(
        f"overall,postgres,{len(pg_all_timings)},{pg_overall['avg_ms']:.3f},"
        f"{pg_overall['median_ms']:.3f},{pg_overall['p95_ms']:.3f},"
        f"{pg_overall['min_ms']:.3f},{pg_overall['max_ms']:.3f}"
    )
    print(
        f"overall,neo4j,{len(neo4j_all_timings)},{neo4j_overall['avg_ms']:.3f},"
        f"{neo4j_overall['median_ms']:.3f},{neo4j_overall['p95_ms']:.3f},"
        f"{neo4j_overall['min_ms']:.3f},{neo4j_overall['max_ms']:.3f}"
    )
    if validation_failures:
        print("validation: failed targets=" + ", ".join(validation_failures))
        return False
    print("validation: ok")
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--setup", action="store_true")
    parser.add_argument("--runs", type=int, default=100)
    parser.add_argument("--warmup", type=int, default=10)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--scenario", choices=["simple", "alias", "expanded", "common", "all"], default="expanded")
    # Kept for backward compatibility with earlier report commands.
    parser.add_argument("--expanded", action="store_true")
    args = parser.parse_args()

    if args.setup:
        setup_postgres()

    print_counts()
    scenarios = ["simple", "alias", "expanded", "common"] if args.scenario == "all" else [args.scenario]
    if args.expanded and args.scenario == "expanded":
        scenarios = ["expanded"]

    ok = True
    for scenario in scenarios:
        ok = run_scenario(scenario, args.runs, args.warmup, args.limit) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
