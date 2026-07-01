"""review.csv / comment.csv BERT 감성분석 배치."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd
from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[2]
if __package__ is None:
    sys.path.insert(0, str(ROOT))

from etl.recipe.preprocessing.recipe_processing import load_recipe_data, save_recipe_data

if __package__ is None:
    from ai.recommendation.sentiment_model import SentimentClassifier
else:
    from .sentiment_model import SentimentClassifier

logger = logging.getLogger(__name__)

REVIEW_CSV = ROOT / "storage" / "processed" / "recipe" / "review.csv"
COMMENT_CSV = ROOT / "storage" / "processed" / "recipe" / "comment.csv"

CONTENT_COL = "content"
SENTIMENT_COLS = ("sentimental", "score", "positive_score", "negative_score")
CONTENT_EMPTY_PLACEHOLDERS = ("", "-", "N/A")


def _filter_processable_content(df: pd.DataFrame, content_col: str) -> pd.DataFrame:
    """본문이 없거나 placeholder인 행을 제외한다."""
    empty_map = {k: pd.NA for k in CONTENT_EMPTY_PLACEHOLDERS}
    content = df[content_col].replace(empty_map)
    valid = content.notna() & content.astype(str).str.strip().ne("")
    excluded = int((~valid).sum())
    if excluded:
        logger.info("본문 없음/placeholder 제외: %s건", excluded)
    return df.loc[valid].copy()


def _ensure_sentiment_columns(df: pd.DataFrame) -> None:
    for col in SENTIMENT_COLS:
        if col not in df.columns:
            df[col] = pd.NA


def analyze_csv(path: Path, *, limit: int | None = None, force: bool = False) -> int:
    """단일 CSV에 감성 컬럼을 채우고 동일 경로에 저장한다. 처리 건수를 반환."""
    df = load_recipe_data(path)
    if CONTENT_COL not in df.columns:
        raise ValueError(f"필수 컬럼 누락: {CONTENT_COL} ({path})")

    _ensure_sentiment_columns(df)

    if force:
        for col in SENTIMENT_COLS:
            df[col] = pd.NA

    needs_mask = df["sentimental"].isna() | df["score"].isna()
    pending = int(needs_mask.sum())
    if pending == 0:
        logger.info("처리 대상 없음 (이미 채워짐): %s", path)
        return 0

    work = df.loc[needs_mask].copy()
    work = _filter_processable_content(work, CONTENT_COL)
    if work.empty:
        logger.info("유효 본문 없음: %s", path)
        return 0

    if limit is not None:
        work = work.head(limit)

    logger.info("감성 분석 대상 %s건: %s", len(work), path)

    classifier = SentimentClassifier()
    for index, row in tqdm(work.iterrows(), total=len(work), desc=path.name):
        text = "" if pd.isna(row[CONTENT_COL]) else str(row[CONTENT_COL])
        result = classifier.predict_sentiment(text)
        df.at[index, "sentimental"] = result["sentimental"]
        df.at[index, "score"] = result["score"]
        df.at[index, "positive_score"] = result["positive_score"]
        df.at[index, "negative_score"] = result["negative_score"]

    save_recipe_data(df, path)
    logger.info("저장 완료 (%s건): %s", len(work), path)
    return len(work)


def resolve_paths(target: str, path: str | None) -> list[Path]:
    if path:
        return [Path(path).resolve()]
    if target == "review":
        return [REVIEW_CSV]
    if target == "comment":
        return [COMMENT_CSV]
    return [REVIEW_CSV, COMMENT_CSV]


def analyze_sentiment(
    *,
    target: str = "all",
    path: str | None = None,
    limit: int | None = None,
    force: bool = False,
) -> None:
    paths = resolve_paths(target, path)
    total = 0
    for csv_path in paths:
        total += analyze_csv(csv_path, limit=limit, force=force)
    logger.info("전체 처리 완료: %s건", total)


def _self_check() -> None:
    df = pd.DataFrame(
        {
            "content": ["맛있어요", "", "-", "N/A", "별로예요"],
            "sentimental": [pd.NA, pd.NA, pd.NA, "positive", pd.NA],
            "score": [pd.NA, pd.NA, pd.NA, 0.9, pd.NA],
        }
    )
    filtered = _filter_processable_content(df, "content")
    assert len(filtered) == 2
    assert list(filtered["content"]) == ["맛있어요", "별로예요"]

    needs = df["sentimental"].isna() | df["score"].isna()
    assert int(needs.sum()) == 4

    assert resolve_paths("review", None) == [REVIEW_CSV]
    assert resolve_paths("all", None) == [REVIEW_CSV, COMMENT_CSV]
    assert resolve_paths("all", "foo.csv") == [Path("foo.csv").resolve()]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="레시피 review/comment CSV BERT 감성분석")
    parser.add_argument(
        "--target",
        choices=("review", "comment", "all"),
        default="all",
        help="처리 대상 CSV (기본: all)",
    )
    parser.add_argument(
        "--path",
        default=None,
        help="단일 CSV 경로 (--target보다 우선)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="처리 행 상한 (스모크·개발용)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="기존 감성 컬럼을 비우고 전 행 재처리 (모델 교체 시)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    _self_check()
    args = _parse_args()
    analyze_sentiment(target=args.target, path=args.path, limit=args.limit, force=args.force)
