"""review_by_llm.csv 레시피별 리뷰 평균 → recipe_fix.csv 컬럼 덮어쓰기."""

from __future__ import annotations

import pathlib
import sys
from math import isclose, log1p

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent.parent
if __package__ is None:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from etl.recipe.preprocessing.recipe_processing import load_recipe_data, save_recipe_data

RECIPE_FIX_CSV = ROOT / "storage" / "processed" / "recipe" / "recipe_fix.csv"
REVIEW_CSV = ROOT / "storage" / "processed" / "recipe" / "review_by_llm.csv"
STAR_AVG_COL = "REVIEW_STAR_NORM_AVG"
SENTIMENT_AVG_COL = "REVIEW_SENTIMENT_AVG"
RANK_SCORE_COL = "REVIEW_RANK_SCORE"
INQ_CNT_LOG_COL = "INQ_CNT_LOG"
INQ_CNT_LOG_CENTERED_COL = "INQ_CNT_LOG_CENTERED"
SRAP_CNT_LOG_COL = "SRAP_CNT_LOG"
SRAP_CNT_LOG_CENTERED_COL = "SRAP_CNT_LOG_CENTERED"

_COUNT_LOG_SPECS = (
    ("INQ_CNT", INQ_CNT_LOG_COL, INQ_CNT_LOG_CENTERED_COL),
    ("SRAP_CNT", SRAP_CNT_LOG_COL, SRAP_CNT_LOG_CENTERED_COL),
)


def build_recipe_review_aggregate(review_df: pd.DataFrame) -> pd.DataFrame:
    if "recipe_id" not in review_df.columns:
        raise ValueError("필수 컬럼 누락: recipe_id")
    review = review_df.copy()
    review["recipe_id"] = pd.to_numeric(review["recipe_id"], errors="coerce")
    review["star_norm"] = pd.to_numeric(review.get("star_norm"), errors="coerce")
    review["positive"] = pd.to_numeric(review.get("positive"), errors="coerce")
    review["negative"] = pd.to_numeric(review.get("negative"), errors="coerce")
    review[SENTIMENT_AVG_COL] = review["positive"] - review["negative"]
    grouped = (
        review.dropna(subset=["recipe_id"])
        .groupby("recipe_id", as_index=False)
        .agg(
            **{
                STAR_AVG_COL: ("star_norm", "mean"),
                SENTIMENT_AVG_COL: (SENTIMENT_AVG_COL, "mean"),
            }
        )
    )
    grouped["recipe_id"] = grouped["recipe_id"].astype(int)
    return grouped


def apply_review_averages(
    recipe_fix_df: pd.DataFrame,
    review_df: pd.DataFrame,
) -> pd.DataFrame:
    if "RCP_SNO" not in recipe_fix_df.columns:
        raise ValueError("필수 컬럼 누락: RCP_SNO")
    base = recipe_fix_df.copy()
    base["RCP_SNO"] = pd.to_numeric(base["RCP_SNO"], errors="coerce")
    base = base.drop(
        columns=[
            STAR_AVG_COL,
            "REVIEW_STAR_IDF_AVG",
            SENTIMENT_AVG_COL,
            RANK_SCORE_COL,
            "REVIEW_RANK_DISTANCE",
        ],
        errors="ignore",
    )
    agg = build_recipe_review_aggregate(review_df)
    merged = base.merge(agg, how="left", left_on="RCP_SNO", right_on="recipe_id")
    merged = merged.drop(columns=["recipe_id"], errors="ignore")
    return merged


def apply_count_logs(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for source_col, log_col, centered_col in _COUNT_LOG_SPECS:
        if source_col not in out.columns:
            raise ValueError(f"필수 컬럼 누락: {source_col}")
        out = out.drop(columns=[log_col, centered_col], errors="ignore")
        counts = pd.to_numeric(out[source_col], errors="coerce")
        valid = counts.notna() & (counts >= 0)
        out[log_col] = pd.NA
        out.loc[valid, log_col] = counts.loc[valid].map(log1p)
        mean_log = out.loc[valid, log_col].mean()
        out[centered_col] = out[log_col] - mean_log
    return out


def apply_rank_score(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out = out.drop(columns=[RANK_SCORE_COL], errors="ignore")
    valid = (
        out[STAR_AVG_COL].notna()
        & out[SENTIMENT_AVG_COL].notna()
        & out[INQ_CNT_LOG_CENTERED_COL].notna()
        & out[SRAP_CNT_LOG_CENTERED_COL].notna()
    )
    out[RANK_SCORE_COL] = pd.NA
    out.loc[valid, RANK_SCORE_COL] = (
        out.loc[valid, STAR_AVG_COL]
        + out.loc[valid, SENTIMENT_AVG_COL]
        + out.loc[valid, INQ_CNT_LOG_CENTERED_COL]
        + out.loc[valid, SRAP_CNT_LOG_CENTERED_COL]
    )
    return out


def _self_check() -> None:
    review_sample = pd.DataFrame(
        {
            "recipe_id": [100, 100, 101, 101, 102],
            "star_norm": [1.0, 0.5, -0.5, -0.5, 0.5],
            "positive": [0.9, 0.7, 0.2, 0.4, 0.8],
            "negative": [0.1, 0.3, 0.5, 0.2, 0.1],
        }
    )
    agg = build_recipe_review_aggregate(review_sample)
    row100 = agg.loc[agg["recipe_id"] == 100].iloc[0]
    assert isclose(row100[STAR_AVG_COL], 0.75)
    assert isclose(row100[SENTIMENT_AVG_COL], 0.6)
    assert RANK_SCORE_COL not in agg.columns

    recipe_fix_sample = pd.DataFrame(
        {
            "RCP_SNO": [100, 102, 999],
            "CKG_NM": ["a", "b", "c"],
            "INQ_CNT": [100, 200, 50],
            "SRAP_CNT": [10, 20, 5],
        }
    )
    applied = apply_rank_score(
        apply_count_logs(apply_review_averages(recipe_fix_sample, review_sample))
    )
    assert SRAP_CNT_LOG_COL in applied.columns
    assert SRAP_CNT_LOG_CENTERED_COL in applied.columns
    assert "REVIEW_RANK_DISTANCE" not in applied.columns
    assert pd.isna(applied.loc[applied["RCP_SNO"] == 999, RANK_SCORE_COL].iloc[0])

    row100_full = applied.loc[applied["RCP_SNO"] == 100].iloc[0]
    expected_score_100 = (
        float(row100_full[STAR_AVG_COL])
        + float(row100_full[SENTIMENT_AVG_COL])
        + float(row100_full[INQ_CNT_LOG_CENTERED_COL])
        + float(row100_full[SRAP_CNT_LOG_CENTERED_COL])
    )
    assert isclose(float(row100_full[RANK_SCORE_COL]), expected_score_100)

    count_sample = pd.DataFrame(
        {"RCP_SNO": [1, 2, 3], "INQ_CNT": [0, 9, 99], "SRAP_CNT": [0, 9, 99]}
    )
    count_logged = apply_count_logs(count_sample)
    for log_col in (INQ_CNT_LOG_COL, SRAP_CNT_LOG_COL):
        assert isclose(float(count_logged.loc[count_logged["RCP_SNO"] == 1, log_col].iloc[0]), 0.0)
        assert isclose(float(count_logged.loc[count_logged["RCP_SNO"] == 2, log_col].iloc[0]), log1p(9))
    for centered_col in (INQ_CNT_LOG_CENTERED_COL, SRAP_CNT_LOG_CENTERED_COL):
        assert isclose(count_logged[centered_col].astype(float).mean(), 0.0, abs_tol=1e-12)

    bad_count = pd.DataFrame({"RCP_SNO": [1], "INQ_CNT": [-1], "SRAP_CNT": [-1]})
    bad_logged = apply_count_logs(bad_count)
    assert pd.isna(bad_logged[INQ_CNT_LOG_COL].iloc[0])
    assert pd.isna(bad_logged[SRAP_CNT_LOG_CENTERED_COL].iloc[0])


def main() -> None:
    recipe_fix_df = load_recipe_data(RECIPE_FIX_CSV)
    review_df = load_recipe_data(REVIEW_CSV)
    result = apply_review_averages(recipe_fix_df, review_df)
    result = apply_count_logs(result)
    result = apply_rank_score(result)
    save_recipe_data(result, RECIPE_FIX_CSV)
    mapped = int(result[STAR_AVG_COL].notna().sum())
    ranked = int(result[RANK_SCORE_COL].notna().sum())
    inq_mapped = int(result[INQ_CNT_LOG_COL].notna().sum())
    srap_mapped = int(result[SRAP_CNT_LOG_COL].notna().sum())
    print(
        f"리뷰 평균/랭크 컬럼 적재 완료: 평균 {mapped}/{len(result)}행, 랭크 {ranked}/{len(result)}행"
    )
    print(f"조회수 log1p 컬럼 적재 완료: {inq_mapped}/{len(result)}행")
    print(f"스크랩 log1p 컬럼 적재 완료: {srap_mapped}/{len(result)}행")


if __name__ == "__main__":
    _self_check()
    main()
