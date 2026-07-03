"""recipe_fix + review/comment LLM CSV → Neo4j Recipe·Reviewer·관계 적재."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd
from tqdm import tqdm

from etl.load_to_neo4j.neo4j_connection import Neo4j_Connection, load_settings

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[3]
RECIPE_FIX_CSV = ROOT / "storage" / "processed" / "recipe" / "recipe_fix.csv"
REVIEW_BY_LLM_CSV = ROOT / "storage" / "processed" / "recipe" / "review_by_llm.csv"
COMMENT_BY_LLM_CSV = ROOT / "storage" / "processed" / "recipe" / "comment_by_llm.csv"

BATCH_SIZE = 100

CONSTRAINT_QUERIES = (
    "CREATE CONSTRAINT recipe_recipe_id IF NOT EXISTS FOR (r:Recipe) REQUIRE r.recipeId IS UNIQUE",
    "CREATE CONSTRAINT reviewer_reviewer_id IF NOT EXISTS FOR (v:Reviewer) REQUIRE v.reviewerId IS UNIQUE",
)

CLEAR_RECIPE_GRAPH_QUERY = """
MATCH (n)
WHERE n:Recipe OR n:Reviewer
DETACH DELETE n
"""

UPSERT_RECIPE_QUERY = """
UNWIND $rows AS row
MERGE (r:Recipe {recipeId: row.recipeId})
SET r.name = row.name,
    r.inqCnt = row.inqCnt,
    r.inqCntRate = row.inqCntRate,
    r.inqCntLogCentered = row.inqCntLogCentered,
    r.reviewStarNormAvg = row.reviewStarNormAvg,
    r.reviewSentimentAvg = row.reviewSentimentAvg,
    r.reviewRankDistance = row.reviewRankDistance,
    r.reviewRankScore = row.reviewRankScore
"""

UPSERT_REVIEWER_QUERY = """
UNWIND $rows AS row
MERGE (v:Reviewer {reviewerId: row.reviewerId})
"""

UPSERT_WROTE_REVIEW_QUERY = """
UNWIND $rows AS row
MERGE (r:Recipe {recipeId: row.recipeId})
MERGE (v:Reviewer {reviewerId: row.reviewerId})
MERGE (v)-[rel:WROTE_REVIEW]->(r)
SET rel.content = row.content,
    rel.starCount = row.starCount,
    rel.starNorm = row.starNorm,
    rel.positive = row.positive,
    rel.negative = row.negative
"""

UPSERT_WROTE_COMMENT_QUERY = """
UNWIND $rows AS row
MERGE (r:Recipe {recipeId: row.recipeId})
MERGE (v:Reviewer {reviewerId: row.reviewerId})
MERGE (v)-[rel:WROTE_COMMENT {commentId: row.commentId}]->(r)
SET rel.content = row.content,
    rel.positive = row.positive,
    rel.negative = row.negative
"""

SUMMARY_QUERY = """
CALL () {
  MATCH (r:Recipe) RETURN "Recipe" AS label, count(r) AS count
  UNION ALL
  MATCH (v:Reviewer) RETURN "Reviewer" AS label, count(v) AS count
  UNION ALL
  MATCH ()-[rel:WROTE_REVIEW]->() RETURN "WROTE_REVIEW" AS label, count(rel) AS count
  UNION ALL
  MATCH ()-[rel:WROTE_COMMENT]->() RETURN "WROTE_COMMENT" AS label, count(rel) AS count
}
RETURN label, count
"""


def _number(value: Any) -> float | int | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if pd.isna(value):
        return None
    if isinstance(value, (int, float)):
        return int(value) if float(value).is_integer() else float(value)
    text = str(value).strip()
    if not text:
        return None
    parsed = float(text)
    return int(parsed) if parsed.is_integer() else parsed


def _text(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def _chunks(rows: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [rows[index : index + size] for index in range(0, len(rows), size)]


def _upsert_batches(
    conn: Neo4j_Connection,
    query: str,
    rows: list[dict[str, Any]],
    *,
    desc: str,
) -> None:
    if not rows:
        return
    for batch in tqdm(_chunks(rows, BATCH_SIZE), desc=desc):
        conn.execute_write(query, {"rows": batch})


def load_recipe_tables(
    *,
    recipe_csv: Path = RECIPE_FIX_CSV,
    review_csv: Path = REVIEW_BY_LLM_CSV,
    comment_csv: Path = COMMENT_BY_LLM_CSV,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    for path in (recipe_csv, review_csv, comment_csv):
        if not path.exists():
            raise FileNotFoundError(f"CSV not found: {path}")
    recipe_df = pd.read_csv(recipe_csv)
    review_df = pd.read_csv(review_csv)
    comment_df = pd.read_csv(comment_csv)
    logger.info(
        "CSV loaded: recipes=%d reviews=%d comments=%d",
        len(recipe_df),
        len(review_df),
        len(comment_df),
    )
    return recipe_df, review_df, comment_df


def build_recipe_rows(recipe_df: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for _, row in recipe_df.iterrows():
        recipe_id = _number(row["RCP_SNO"])
        if recipe_id is None:
            continue
        rows.append(
            {
                "recipeId": int(recipe_id),
                "name": _text(row["CKG_NM"]),
                "inqCnt": _number(row.get("INQ_CNT")),
                "inqCntRate": _number(row.get("INQ_CNT_RATE")),
                "inqCntLogCentered": _number(row.get("INQ_CNT_LOG_CENTERED")),
                "reviewStarNormAvg": _number(row.get("REVIEW_STAR_NORM_AVG")),
                "reviewSentimentAvg": _number(row.get("REVIEW_SENTIMENT_AVG")),
                "reviewRankDistance": _number(row.get("REVIEW_RANK_DISTANCE")),
                "reviewRankScore": _number(row.get("REVIEW_RANK_SCORE")),
            }
        )
    return rows


def build_reviewer_rows(review_df: pd.DataFrame, comment_df: pd.DataFrame) -> list[dict[str, Any]]:
    reviewer_ids = pd.concat(
        [review_df["group_id"], comment_df["group_id"]],
        ignore_index=True,
    ).dropna()
    unique_ids = sorted({int(v) for v in reviewer_ids.astype(int).unique()})
    return [{"reviewerId": reviewer_id} for reviewer_id in unique_ids]


def build_review_rel_rows(review_df: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for _, row in review_df.iterrows():
        recipe_id = _number(row["recipe_id"])
        reviewer_id = _number(row["group_id"])
        if recipe_id is None or reviewer_id is None:
            continue
        rows.append(
            {
                "recipeId": int(recipe_id),
                "reviewerId": int(reviewer_id),
                "content": _text(row.get("content")),
                "starCount": _number(row.get("star_count")),
                "starNorm": _number(row.get("star_norm")),
                "positive": _number(row.get("positive")),
                "negative": _number(row.get("negative")),
            }
        )
    return rows


def build_comment_rel_rows(comment_df: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for _, row in comment_df.iterrows():
        recipe_id = _number(row["recipe_id"])
        reviewer_id = _number(row["group_id"])
        comment_id = _number(row.get("id"))
        if recipe_id is None or reviewer_id is None or comment_id is None:
            continue
        rows.append(
            {
                "recipeId": int(recipe_id),
                "reviewerId": int(reviewer_id),
                "commentId": int(comment_id),
                "content": _text(row.get("content")),
                "positive": _number(row.get("positive")),
                "negative": _number(row.get("negative")),
            }
        )
    return rows


def load_recipe_graph_to_neo4j(
    *,
    clear: bool = False,
    recipe_csv: Path = RECIPE_FIX_CSV,
    review_csv: Path = REVIEW_BY_LLM_CSV,
    comment_csv: Path = COMMENT_BY_LLM_CSV,
) -> dict[str, int]:
    recipe_df, review_df, comment_df = load_recipe_tables(
        recipe_csv=recipe_csv,
        review_csv=review_csv,
        comment_csv=comment_csv,
    )
    recipe_rows = build_recipe_rows(recipe_df)
    reviewer_rows = build_reviewer_rows(review_df, comment_df)
    review_rel_rows = build_review_rel_rows(review_df)
    comment_rel_rows = build_comment_rel_rows(comment_df)

    if not recipe_rows:
        raise ValueError("recipe_fix.csv에서 적재할 Recipe 행이 없습니다.")

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
            conn.execute_write(CLEAR_RECIPE_GRAPH_QUERY)
            logger.info("Existing Recipe/Reviewer subgraph cleared")

        _upsert_batches(conn, UPSERT_RECIPE_QUERY, recipe_rows, desc="Recipe upsert")
        _upsert_batches(conn, UPSERT_REVIEWER_QUERY, reviewer_rows, desc="Reviewer upsert")
        _upsert_batches(conn, UPSERT_WROTE_REVIEW_QUERY, review_rel_rows, desc="WROTE_REVIEW upsert")
        _upsert_batches(conn, UPSERT_WROTE_COMMENT_QUERY, comment_rel_rows, desc="WROTE_COMMENT upsert")

        summary_rows = conn.execute_query(SUMMARY_QUERY)
    finally:
        conn.close()

    result = {row["label"]: int(row["count"]) for row in summary_rows}
    logger.info("Recipe graph Neo4j load complete: %s", result)
    return result


def _self_check() -> None:
    recipe_df, review_df, comment_df = load_recipe_tables()
    recipe_rows = build_recipe_rows(recipe_df)
    reviewer_rows = build_reviewer_rows(review_df, comment_df)
    review_rel_rows = build_review_rel_rows(review_df)
    comment_rel_rows = build_comment_rel_rows(comment_df)

    assert len(recipe_rows) > 3000
    assert recipe_rows[0]["recipeId"] == int(recipe_df.iloc[0]["RCP_SNO"])
    assert isinstance(recipe_rows[0]["inqCntRate"], float)
    assert "inqCntLogCentered" in recipe_rows[0]
    assert any(row["inqCntLogCentered"] is not None for row in recipe_rows)
    assert "reviewStarNormAvg" in recipe_rows[0]
    assert "reviewSentimentAvg" in recipe_rows[0]
    assert "reviewRankDistance" in recipe_rows[0]
    assert "reviewRankScore" in recipe_rows[0]
    assert any(row["reviewStarNormAvg"] is None for row in recipe_rows)
    assert any(row["reviewSentimentAvg"] is None for row in recipe_rows)
    assert any(row["reviewRankDistance"] is None for row in recipe_rows)
    assert any(row["reviewRankScore"] is None for row in recipe_rows)
    assert any(row["reviewRankScore"] is not None for row in recipe_rows)

    assert len(reviewer_rows) > 900
    assert reviewer_rows[0]["reviewerId"] > 0

    assert review_rel_rows
    assert "starNorm" in review_rel_rows[0]
    assert review_rel_rows[0]["starCount"] is not None

    assert comment_rel_rows
    assert "commentId" in comment_rel_rows[0]
    assert comment_rel_rows[0]["commentId"] > 0
