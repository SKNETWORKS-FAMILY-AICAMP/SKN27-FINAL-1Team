"""Neo4j Recipe 노드 부가 점수 조회."""

from __future__ import annotations

from neo4j.exceptions import Neo4jError

from app.backend.db.neo4j_session import graph_session

_REVIEW_RANK_SCORE_QUERY = """
UNWIND $recipe_ids AS recipeId
OPTIONAL MATCH (r:Recipe {recipeId: recipeId})
RETURN recipeId, r.reviewRankScore AS review_rank_score
"""


def fetch_review_rank_scores(recipe_ids: list[int]) -> dict[int, float]:
    if not recipe_ids:
        return {}
    try:
        with graph_session() as session:
            records = session.run(_REVIEW_RANK_SCORE_QUERY, recipe_ids=recipe_ids)
            return {
                int(record["recipeId"]): float(record["review_rank_score"])
                for record in records
                if record["review_rank_score"] is not None
            }
    except Neo4jError:
        return {}


def _self_check() -> None:
    assert fetch_review_rank_scores([]) == {}

    records = [
        {"recipeId": 1, "review_rank_score": 3.5},
        {"recipeId": 2, "review_rank_score": None},
        {"recipeId": 3, "review_rank_score": -1.0},
        {"recipeId": 4, "review_rank_score": 0.0},
    ]
    scores = {
        int(record["recipeId"]): float(record["review_rank_score"])
        for record in records
        if record["review_rank_score"] is not None
    }
    assert scores == {1: 3.5, 3: -1.0, 4: 0.0}
    assert 2 not in scores

    recipe_ids = [1, 2, 3]
    included = [recipe_id for recipe_id in recipe_ids if recipe_id in scores]
    assert included == [1, 3]


if __name__ == "__main__":
    _self_check()
    print("ok")
