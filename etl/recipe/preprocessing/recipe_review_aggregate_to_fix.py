"""review_by_llm.csv 레시피별 리뷰 평균 → recipe_fix.csv 컬럼 덮어쓰기."""

from __future__ import annotations

import pathlib
import sys
from math import isclose, sqrt

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent.parent
if __package__ is None:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from etl.recipe.preprocessing.recipe_processing import load_recipe_data, save_recipe_data

RECIPE_FIX_CSV = ROOT / "storage" / "processed" / "recipe" / "recipe_fix.csv"
REVIEW_CSV = ROOT / "storage" / "processed" / "recipe" / "review_by_llm.csv"
STAR_AVG_COL = "REVIEW_STAR_NORM_AVG"
SENTIMENT_AVG_COL = "REVIEW_SENTIMENT_AVG"
RANK_DISTANCE_COL = "REVIEW_RANK_DISTANCE"
RANK_SCORE_COL = "REVIEW_RANK_SCORE"
TARGET_STAR = 1.0
TARGET_SENTIMENT = 1.0
MAX_DISTANCE = sqrt((TARGET_STAR - (-1.0)) ** 2 + (TARGET_SENTIMENT - (-1.0)) ** 2)


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
    valid_mask = grouped[STAR_AVG_COL].notna() & grouped[SENTIMENT_AVG_COL].notna()
    grouped[RANK_DISTANCE_COL] = pd.NA
    grouped[RANK_SCORE_COL] = pd.NA
    grouped.loc[valid_mask, RANK_DISTANCE_COL] = (
        (TARGET_STAR - grouped.loc[valid_mask, STAR_AVG_COL]) ** 2
        + (TARGET_SENTIMENT - grouped.loc[valid_mask, SENTIMENT_AVG_COL]) ** 2
    ) ** 0.5
    grouped.loc[valid_mask, RANK_SCORE_COL] = 100 * (
        1 - (grouped.loc[valid_mask, RANK_DISTANCE_COL] / MAX_DISTANCE)
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
            RANK_DISTANCE_COL,
            RANK_SCORE_COL,
        ],
        errors="ignore",
    )
    agg = build_recipe_review_aggregate(review_df)
    merged = base.merge(agg, how="left", left_on="RCP_SNO", right_on="recipe_id")
    merged = merged.drop(columns=["recipe_id"], errors="ignore")
    return merged


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
    expected_distance_100 = sqrt((TARGET_STAR - 0.75) ** 2 + (TARGET_SENTIMENT - 0.6) ** 2)
    expected_score_100 = 100 * (1 - expected_distance_100 / MAX_DISTANCE)
    assert isclose(float(row100[RANK_DISTANCE_COL]), expected_distance_100)
    assert isclose(float(row100[RANK_SCORE_COL]), expected_score_100)
    row101 = agg.loc[agg["recipe_id"] == 101].iloc[0]
    assert isclose(row101[STAR_AVG_COL], -0.5)
    assert isclose(row101[SENTIMENT_AVG_COL], -0.05)

    recipe_fix_sample = pd.DataFrame({"RCP_SNO": [100, 102, 999], "CKG_NM": ["a", "b", "c"]})
    applied = apply_review_averages(recipe_fix_sample, review_sample)
    assert STAR_AVG_COL in applied.columns
    assert SENTIMENT_AVG_COL in applied.columns
    assert RANK_DISTANCE_COL in applied.columns
    assert RANK_SCORE_COL in applied.columns
    val100 = applied.loc[applied["RCP_SNO"] == 100, STAR_AVG_COL].iloc[0]
    assert isclose(val100, 0.75)
    assert pd.isna(applied.loc[applied["RCP_SNO"] == 999, STAR_AVG_COL].iloc[0])
    assert pd.isna(applied.loc[applied["RCP_SNO"] == 999, RANK_DISTANCE_COL].iloc[0])
    assert pd.isna(applied.loc[applied["RCP_SNO"] == 999, RANK_SCORE_COL].iloc[0])

    overwrite_sample = recipe_fix_sample.copy()
    overwrite_sample[STAR_AVG_COL] = 999.0
    overwrite_sample[SENTIMENT_AVG_COL] = 999.0
    overwrite_sample[RANK_DISTANCE_COL] = 999.0
    overwrite_sample[RANK_SCORE_COL] = 999.0
    overwritten = apply_review_averages(overwrite_sample, review_sample)
    overwritten_100 = overwritten.loc[overwritten["RCP_SNO"] == 100].iloc[0]
    assert isclose(overwritten_100[STAR_AVG_COL], 0.75)
    assert isclose(overwritten_100[SENTIMENT_AVG_COL], 0.6)
    assert isclose(float(overwritten_100[RANK_DISTANCE_COL]), expected_distance_100)
    assert isclose(float(overwritten_100[RANK_SCORE_COL]), expected_score_100)


def main() -> None:
    recipe_fix_df = load_recipe_data(RECIPE_FIX_CSV)
    review_df = load_recipe_data(REVIEW_CSV)
    result = apply_review_averages(recipe_fix_df, review_df)
    save_recipe_data(result, RECIPE_FIX_CSV)
    mapped = int(result[STAR_AVG_COL].notna().sum())
    ranked = int(result[RANK_SCORE_COL].notna().sum())
    print(f"리뷰 평균/랭크 컬럼 적재 완료: 평균 {mapped}/{len(result)}행, 랭크 {ranked}/{len(result)}행")


if __name__ == "__main__":
    _self_check()
    main()
