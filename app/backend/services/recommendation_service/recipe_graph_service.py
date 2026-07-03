"""Neo4j Recipe 노드 부가 점수 조회."""

from __future__ import annotations

from neo4j.exceptions import Neo4jError

from app.backend.db.neo4j_session import graph_session

_REVIEW_RANK_SCORE_QUERY = """
UNWIND $recipe_ids AS recipeId
OPTIONAL MATCH (r:Recipe {recipeId: recipeId})
RETURN recipeId, r.reviewRankScore AS review_rank_score
"""


def _normalize_score(value: object) -> float:
    if value is None:
        return 0.0
    return float(value)


def fetch_review_rank_scores(recipe_ids: list[int]) -> dict[int, float]:
    if not recipe_ids:
        return {}
    try:
        with graph_session() as session:
            records = session.run(_REVIEW_RANK_SCORE_QUERY, recipe_ids=recipe_ids)
            return {
                int(record["recipeId"]): _normalize_score(record["review_rank_score"])
                for record in records
            }
    except Neo4jError:
        return {}


def _self_check() -> None:
    assert _normalize_score(None) == 0.0
    assert _normalize_score(91.34) == 91.34
    assert fetch_review_rank_scores([]) == {}


if __name__ == "__main__":
    _self_check()
    print("ok")
