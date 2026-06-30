"""review_by_llm.csv / comment_by_llm.csv OpenAI 감성분석 배치."""

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
    from ai.recommendation.llm_sentiment_model import LLMSentimentAnalyzer, parse_sentiment_response
else:
    from .llm_sentiment_model import LLMSentimentAnalyzer, parse_sentiment_response

logger = logging.getLogger(__name__)

REVIEW_BY_LLM_CSV = ROOT / "storage" / "processed" / "recipe" / "review_by_llm.csv"
COMMENT_BY_LLM_CSV = ROOT / "storage" / "processed" / "recipe" / "comment_by_llm.csv"

CONTENT_COL = "content"
SENTIMENT_COLS = ("positive", "negative")
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


def _analyze_csv(
    path: Path,
    analyzer: LLMSentimentAnalyzer,
    *,
    limit: int | None = None,
    force: bool = False,
) -> int:
    """단일 CSV에 positive/negative 컬럼을 채우고 동일 경로에 저장한다."""
    df = load_recipe_data(path)
    if CONTENT_COL not in df.columns:
        raise ValueError(f"필수 컬럼 누락: {CONTENT_COL} ({path})")

    _ensure_sentiment_columns(df)

    if force:
        for col in SENTIMENT_COLS:
            df[col] = pd.NA

    needs_mask = df["positive"].isna() | df["negative"].isna()
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

    logger.info("LLM 감성 분석 대상 %s건: %s", len(work), path)

    processed = 0
    for index, row in tqdm(work.iterrows(), total=len(work), desc=path.name):
        text = "" if pd.isna(row[CONTENT_COL]) else str(row[CONTENT_COL])
        result = analyzer.predict_sentiment(text)
        if pd.isna(result["positive"]) or pd.isna(result["negative"]):
            logger.warning("행 스킵 (분석 실패): index=%s", index)
            continue
        df.at[index, "positive"] = result["positive"]
        df.at[index, "negative"] = result["negative"]
        processed += 1

    save_recipe_data(df, path)
    logger.info("저장 완료 (%s건): %s", processed, path)
    return processed


def process_review_by_llm(*, limit: int | None = None, force: bool = False) -> int:
    """review_by_llm.csv 감성분석."""
    analyzer = LLMSentimentAnalyzer()
    return _analyze_csv(REVIEW_BY_LLM_CSV, analyzer, limit=limit, force=force)


def process_comment_by_llm(*, limit: int | None = None, force: bool = False) -> int:
    """comment_by_llm.csv 감성분석."""
    analyzer = LLMSentimentAnalyzer()
    return _analyze_csv(COMMENT_BY_LLM_CSV, analyzer, limit=limit, force=force)


def analyze_sentiment_by_llm(
    *,
    target: str = "all",
    limit: int | None = None,
    force: bool = False,
) -> None:
    """target에 따라 review/comment LLM CSV를 처리한다."""
    analyzer = LLMSentimentAnalyzer()
    total = 0
    if target in ("review", "all"):
        total += _analyze_csv(REVIEW_BY_LLM_CSV, analyzer, limit=limit, force=force)
    if target in ("comment", "all"):
        total += _analyze_csv(COMMENT_BY_LLM_CSV, analyzer, limit=limit, force=force)
    logger.info("전체 처리 완료: %s건", total)


def _self_check() -> None:
    df = pd.DataFrame(
        {
            "content": ["맛있어요", "", "-", "N/A", "별로예요"],
            "positive": [pd.NA, pd.NA, pd.NA, 0.9, pd.NA],
            "negative": [pd.NA, pd.NA, pd.NA, 0.1, pd.NA],
        }
    )
    filtered = _filter_processable_content(df, "content")
    assert len(filtered) == 2
    assert list(filtered["content"]) == ["맛있어요", "별로예요"]

    needs = df["positive"].isna() | df["negative"].isna()
    assert int(needs.sum()) == 4

    parsed = parse_sentiment_response('{"positive": 0.85, "negative": 0.15}')
    assert parsed == {"positive": 0.85, "negative": 0.15}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="레시피 review/comment LLM CSV 감성분석")
    parser.add_argument(
        "--target",
        choices=("review", "comment", "all"),
        default="all",
        help="처리 대상 CSV (기본: all)",
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
        help="기존 감성 컬럼을 비우고 전 행 재처리",
    )
    return parser.parse_args()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    _self_check()
    args = _parse_args()
    analyze_sentiment_by_llm(target=args.target, limit=args.limit, force=args.force)
