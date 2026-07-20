"""Build reproducible structural recipe embeddings after Neo4j data loading."""

from __future__ import annotations

import logging

from etl.load_to_neo4j.neo4j_connection import Neo4j_Connection, load_settings

logger = logging.getLogger(__name__)

GRAPH_NAME = "recipe-ingredient-graph"
EMBEDDING_PROPERTY = "graphEmbedding"
VECTOR_INDEX_NAME = "recipe_graph_embedding_index"
EMBEDDING_DIMENSION = 64


def prepare_graph_search() -> dict[str, int | str]:
    settings = load_settings()
    conn = Neo4j_Connection(
        settings.uri,
        settings.user,
        settings.password,
        database=settings.database,
    )
    try:
        version = conn.execute_single("RETURN gds.version() AS version")
        if not version:
            raise RuntimeError("GDS is not available")

        exists = conn.execute_single(
            "CALL gds.graph.exists($name) YIELD exists RETURN exists",
            {"name": GRAPH_NAME},
        )
        if exists and exists["exists"]:
            conn.execute_write(
                "CALL gds.graph.drop($name) YIELD graphName RETURN graphName",
                {"name": GRAPH_NAME},
            )

        conn.execute_write(
            """
            CALL gds.graph.project(
              $name,
              ['Recipe', 'Ingredient'],
              {REQUIRES_INGREDIENT: {orientation: 'UNDIRECTED'}}
            )
            YIELD graphName
            RETURN graphName
            """,
            {"name": GRAPH_NAME},
        )
        write_result = conn.execute_single(
            """
            CALL gds.fastRP.write(
              $name,
              {
                embeddingDimension: $dimension,
                iterationWeights: [0.0, 1.0, 1.0],
                randomSeed: 42,
                writeProperty: $property
              }
            )
            YIELD nodePropertiesWritten
            RETURN nodePropertiesWritten
            """,
            {
                "name": GRAPH_NAME,
                "dimension": EMBEDDING_DIMENSION,
                "property": EMBEDDING_PROPERTY,
            },
        )
        conn.execute_write(
            f"""
            CREATE VECTOR INDEX {VECTOR_INDEX_NAME} IF NOT EXISTS
            FOR (recipe:Recipe) ON recipe.{EMBEDDING_PROPERTY}
            OPTIONS {{indexConfig: {{
              `vector.dimensions`: {EMBEDDING_DIMENSION},
              `vector.similarity_function`: 'cosine'
            }}}}
            """
        )
        conn.execute_write(
            "CALL db.awaitIndex($indexName, 60)",
            {"indexName": VECTOR_INDEX_NAME},
        )
        embedded = conn.execute_single(
            f"MATCH (r:Recipe) WHERE r.{EMBEDDING_PROPERTY} IS NOT NULL RETURN count(r) AS count"
        )
        return {
            "gdsVersion": str(version["version"]),
            "nodePropertiesWritten": int((write_result or {}).get("nodePropertiesWritten", 0)),
            "embeddedRecipes": int((embedded or {}).get("count", 0)),
        }
    finally:
        try:
            conn.execute_write(
                "CALL gds.graph.drop($name, false) YIELD graphName RETURN graphName",
                {"name": GRAPH_NAME},
            )
        except Exception:
            logger.debug("GDS graph catalog cleanup skipped", exc_info=True)
        conn.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logger.info("Graph search preparation complete: %s", prepare_graph_search())


if __name__ == "__main__":
    main()
