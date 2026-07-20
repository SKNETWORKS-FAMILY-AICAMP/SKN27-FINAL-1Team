"""Load provider-generated recipe embeddings from JSONL into Neo4j.

Each line must be ``{"recipeId": 1, "embedding": [..]}``.  This module does
not call an embedding provider, which keeps credential and model choice out of
the ETL contract.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from etl.load_to_neo4j.neo4j_connection import Neo4j_Connection, load_settings

INDEX_NAME = "recipe_semantic_embedding_index"


def load_embeddings(path: Path) -> tuple[list[dict], int]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    dimensions = {len(row.get("embedding") or []) for row in rows}
    if not rows or len(dimensions) != 1 or 0 in dimensions:
        raise ValueError("embeddings must be non-empty and have one consistent dimension")
    if any(not isinstance(row.get("recipeId"), int) for row in rows):
        raise ValueError("every embedding row must contain an integer recipeId")
    if len({row["recipeId"] for row in rows}) != len(rows):
        raise ValueError("duplicate recipeId in embedding input")
    return rows, dimensions.pop()


def write_embeddings(path: Path) -> dict[str, int]:
    rows, dimension = load_embeddings(path)
    settings = load_settings()
    conn = Neo4j_Connection(settings.uri, settings.user, settings.password, database=settings.database)
    try:
        conn.execute_write(
            """
            UNWIND $rows AS row
            MATCH (recipe:Recipe {recipeId: row.recipeId})
            SET recipe.semanticEmbedding = row.embedding
            """,
            {"rows": rows},
        )
        conn.execute_write(
            f"""
            CREATE VECTOR INDEX {INDEX_NAME} IF NOT EXISTS
            FOR (recipe:Recipe) ON recipe.semanticEmbedding
            OPTIONS {{indexConfig: {{
              `vector.dimensions`: {dimension},
              `vector.similarity_function`: 'cosine'
            }}}}
            """
        )
        count = conn.execute_single(
            "MATCH (r:Recipe) WHERE r.semanticEmbedding IS NOT NULL RETURN count(r) AS count"
        )
        return {"dimension": dimension, "embeddedRecipes": int((count or {}).get("count", 0))}
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Load recipe semantic embedding JSONL into Neo4j")
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    print(write_embeddings(args.path))


if __name__ == "__main__":
    main()
