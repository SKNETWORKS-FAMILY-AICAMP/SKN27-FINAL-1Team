from __future__ import annotations

from etl.load_to_neo4j.neo4j_connection import Neo4j_Connection, load_settings


NODE_COUNT_QUERY = """
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
ORDER BY node
"""


MISSING_RELATIONSHIP_QUERY = """
CALL () {
  OPTIONAL MATCH (middle:MiddleCategory)
  WHERE NOT EXISTS { MATCH (:MajorCategory)-[:HAS_MIDDLE]->(middle) }
  RETURN "MiddleCategory missing MajorCategory" AS check, count(middle) AS count
  UNION ALL
  OPTIONAL MATCH (ingredient:Ingredient)
  WHERE NOT EXISTS { MATCH (:MiddleCategory)-[:HAS_INGREDIENT]->(ingredient) }
  RETURN "Ingredient missing MiddleCategory" AS check, count(ingredient) AS count
  UNION ALL
  OPTIONAL MATCH (ingredient:Ingredient)
  WHERE NOT ingredient:FoodGuide
  RETURN "Ingredient missing FoodGuide compatibility label" AS check, count(ingredient) AS count
  UNION ALL
  OPTIONAL MATCH (guide:Guide)
  WHERE NOT EXISTS { MATCH (:Ingredient)-[:HAS_GUIDE]->(guide) }
  RETURN "Guide missing Ingredient" AS check, count(guide) AS count
  UNION ALL
  OPTIONAL MATCH (guide:Guide)
  WHERE NOT EXISTS { MATCH (guide)-[:SOURCED_FROM]->(:Source) }
  RETURN "Guide missing Source" AS check, count(guide) AS count
  UNION ALL
  OPTIONAL MATCH (nutrition:Nutrition)
  WHERE NOT EXISTS { MATCH (:Ingredient)-[:HAS_NUTRITION]->(nutrition) }
  RETURN "Nutrition missing Ingredient" AS check, count(nutrition) AS count
  UNION ALL
  OPTIONAL MATCH (nutrition:Nutrition)
  WHERE NOT EXISTS { MATCH (nutrition)-[:SOURCED_FROM]->(:Source) }
  RETURN "Nutrition missing Source" AS check, count(nutrition) AS count
}
RETURN check, count
ORDER BY check
"""


ORPHAN_NODE_QUERY = """
CALL () {
  OPTIONAL MATCH (n:MajorCategory)
  WHERE NOT EXISTS { MATCH (n)-[:HAS_MIDDLE]->(:MiddleCategory) }
  RETURN "MajorCategory" AS node, count(n) AS count
  UNION ALL
  OPTIONAL MATCH (n:MiddleCategory)
  WHERE NOT EXISTS { MATCH (:MajorCategory)-[:HAS_MIDDLE]->(n) }
     OR NOT EXISTS { MATCH (n)-[:HAS_INGREDIENT]->(:Ingredient) }
  RETURN "MiddleCategory" AS node, count(n) AS count
  UNION ALL
  OPTIONAL MATCH (n:Ingredient)
  WHERE NOT EXISTS { MATCH (:MiddleCategory)-[:HAS_INGREDIENT]->(n) }
  RETURN "Ingredient" AS node, count(n) AS count
  UNION ALL
  OPTIONAL MATCH (n:Alias)
  WHERE NOT EXISTS { MATCH (:Ingredient)-[:HAS_ALIAS]->(n) }
  RETURN "Alias" AS node, count(n) AS count
  UNION ALL
  OPTIONAL MATCH (n:SeasonMonth)
  WHERE NOT EXISTS { MATCH (:Ingredient)-[:IN_SEASON]->(n) }
  RETURN "SeasonMonth" AS node, count(n) AS count
  UNION ALL
  OPTIONAL MATCH (n:Nutrition)
  WHERE NOT EXISTS { MATCH (:Ingredient)-[:HAS_NUTRITION]->(n) }
  RETURN "Nutrition" AS node, count(n) AS count
  UNION ALL
  OPTIONAL MATCH (n:Guide)
  WHERE NOT EXISTS { MATCH (:Ingredient)-[:HAS_GUIDE]->(n) }
  RETURN "Guide" AS node, count(n) AS count
  UNION ALL
  OPTIONAL MATCH (n:Source)
  WHERE NOT EXISTS { MATCH (:Guide)-[:SOURCED_FROM]->(n) }
    AND NOT EXISTS { MATCH (:Nutrition)-[:SOURCED_FROM]->(n) }
  RETURN "Source" AS node, count(n) AS count
}
RETURN node, count
ORDER BY node
"""


def _print_rows(title: str, rows: list[dict]) -> None:
    print(f"\n[{title}]")
    for row in rows:
        label = row.get("node") or row.get("check")
        print(f"- {label}: {row['count']}")


def main() -> int:
    settings = load_settings()
    conn = Neo4j_Connection(
        settings.uri,
        settings.user,
        settings.password,
        database=settings.database,
    )
    try:
        node_counts = conn.execute_query(NODE_COUNT_QUERY)
        missing_relationships = conn.execute_query(MISSING_RELATIONSHIP_QUERY)
        orphan_nodes = conn.execute_query(ORPHAN_NODE_QUERY)
    finally:
        conn.close()

    _print_rows("노드 개수", node_counts)
    _print_rows("누락 관계", missing_relationships)
    _print_rows("고아 노드", orphan_nodes)

    issue_count = sum(row["count"] for row in missing_relationships + orphan_nodes)
    print(f"\n검증 완료: 문제 {issue_count}건")
    return 1 if issue_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
