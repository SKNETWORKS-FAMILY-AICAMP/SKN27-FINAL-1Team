"""review_by_llm.csv 레시피별 리뷰 평균 → recipe_fix.csv 컬럼 덮어쓰기."""

from __future__ import annotations

import pathlib
import sys
from math import isclose

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent.parent
if __package__ is None:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from etl.recipe.preprocessing.recipe_processing import load_recipe_data, save_recipe_data

RECIPE_FIX_CSV = ROOT / "storage" / "processed" / "recipe" / "recipe_fix.csv"
REVIEW_CSV = ROOT / "storage" / "processed" / "recipe" / "review_by_llm.csv"
STAR_AVG_COL = "REVIEW_STAR_IDF_AVG"
SENTIMENT_AVG_COL = "REVIEW_SENTIMENT_AVG"


def build_recipe_review_aggregate(review_df: pd.DataFrame) -> pd.DataFrame:
    if "recipe_id" not in review_df.columns:
        raise ValueError("필수 컬럼 누락: recipe_id")
    review = review_df.copy()
    review["recipe_id"] = pd.to_numeric(review["recipe_id"], errors="coerce")
    review["star_idf"] = pd.to_numeric(review.get("star_idf"), errors="coerce")
    review["positive"] = pd.to_numeric(review.get("positive"), errors="coerce")
    review["negative"] = pd.to_numeric(review.get("negative"), errors="coerce")
    review[SENTIMENT_AVG_COL] = review["positive"] - review["negative"]
    grouped = (
        review.dropna(subset=["recipe_id"])
        .groupby("recipe_id", as_index=False)
        .agg(
            **{
                STAR_AVG_COL: ("star_idf", "mean"),
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
    base = base.drop(columns=[STAR_AVG_COL, SENTIMENT_AVG_COL], errors="ignore")
    agg = build_recipe_review_aggregate(review_df)
    merged = base.merge(agg, how="left", left_on="RCP_SNO", right_on="recipe_id")
    merged = merged.drop(columns=["recipe_id"], errors="ignore")
    return merged


def _self_check() -> None:
    review_sample = pd.DataFrame(
        {
            "recipe_id": [100, 100, 101, 101, 102],
            "star_idf": [0.8, 0.6, -0.4, -0.2, 0.1],
            "positive": [0.9, 0.7, 0.2, 0.4, 0.8],
            "negative": [0.1, 0.3, 0.5, 0.2, 0.1],
        }
    )
    agg = build_recipe_review_aggregate(review_sample)
    row100 = agg.loc[agg["recipe_id"] == 100].iloc[0]
    assert isclose(row100[STAR_AVG_COL], 0.7)
    assert isclose(row100[SENTIMENT_AVG_COL], 0.6)
    row101 = agg.loc[agg["recipe_id"] == 101].iloc[0]
    assert isclose(row101[STAR_AVG_COL], -0.3)
    assert isclose(row101[SENTIMENT_AVG_COL], -0.05)

    recipe_fix_sample = pd.DataFrame({"RCP_SNO": [100, 102, 999], "CKG_NM": ["a", "b", "c"]})
    applied = apply_review_averages(recipe_fix_sample, review_sample)
    assert STAR_AVG_COL in applied.columns
    assert SENTIMENT_AVG_COL in applied.columns
    val100 = applied.loc[applied["RCP_SNO"] == 100, STAR_AVG_COL].iloc[0]
    assert isclose(val100, 0.7)
    assert pd.isna(applied.loc[applied["RCP_SNO"] == 999, STAR_AVG_COL].iloc[0])

    overwrite_sample = recipe_fix_sample.copy()
    overwrite_sample[STAR_AVG_COL] = 999.0
    overwrite_sample[SENTIMENT_AVG_COL] = 999.0
    overwritten = apply_review_averages(overwrite_sample, review_sample)
    overwritten_100 = overwritten.loc[overwritten["RCP_SNO"] == 100].iloc[0]
    assert isclose(overwritten_100[STAR_AVG_COL], 0.7)
    assert isclose(overwritten_100[SENTIMENT_AVG_COL], 0.6)


def main() -> None:
    recipe_fix_df = load_recipe_data(RECIPE_FIX_CSV)
    review_df = load_recipe_data(REVIEW_CSV)
    result = apply_review_averages(recipe_fix_df, review_df)
    save_recipe_data(result, RECIPE_FIX_CSV)
    mapped = int(result[STAR_AVG_COL].notna().sum())
    print(f"리뷰 평균 컬럼 적재 완료: {mapped}/{len(result)}행")


if __name__ == "__main__":
    _self_check()
    main()
