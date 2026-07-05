"""review_by_llm.csv star_count → 선형 정규화(star_norm) 컬럼 적재."""

from __future__ import annotations

import pathlib
import sys
from math import isclose

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent.parent
if __package__ is None:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from etl.recipe.preprocessing.recipe_processing import load_recipe_data, save_recipe_data

REVIEW_CSV = ROOT / "storage" / "processed" / "recipe" / "review_by_llm.csv"
OUT_COL = "star_norm"
STAR_NORM_MAP = {1: -1.0, 2: -0.5, 3: 0.0, 4: 0.5, 5: 1.0}


def _valid_star_counts(star_counts: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(star_counts, errors="coerce")
    integer_only = numeric.where(numeric.mod(1).eq(0))
    valid = integer_only.dropna().astype(int)
    valid = valid[valid.between(1, 5)]
    return valid


def apply_star_norm(
    df: pd.DataFrame,
    *,
    star_col: str = "star_count",
    out_col: str = OUT_COL,
) -> pd.DataFrame:
    valid = _valid_star_counts(df[star_col])
    df[out_col] = pd.NA
    df.loc[valid.index, out_col] = valid.astype(int).map(STAR_NORM_MAP)
    return df


def _self_check() -> None:
    toy = pd.DataFrame({"star_count": [1, 2, 3, 4, 5, 5, None, 6]})
    out = apply_star_norm(toy.copy())
    assert isclose(out.loc[out["star_count"] == 1, OUT_COL].iloc[0], -1.0)
    assert isclose(out.loc[out["star_count"] == 2, OUT_COL].iloc[0], -0.5)
    assert isclose(out.loc[out["star_count"] == 3, OUT_COL].iloc[0], 0.0)
    assert isclose(out.loc[out["star_count"] == 4, OUT_COL].iloc[0], 0.5)
    assert isclose(out.loc[out["star_count"] == 5, OUT_COL].iloc[0], 1.0)
    assert pd.isna(out.loc[toy["star_count"].isna(), OUT_COL].iloc[0])
    assert pd.isna(out.loc[out["star_count"] == 6, OUT_COL].iloc[0])

    if REVIEW_CSV.exists():
        df = load_recipe_data(REVIEW_CSV)
        df = apply_star_norm(df)
        valid_mask = pd.to_numeric(df["star_count"], errors="coerce").between(1, 5)
        assert df.loc[valid_mask, OUT_COL].notna().all()
        five_mask = pd.to_numeric(df["star_count"], errors="coerce").eq(5) & valid_mask
        if five_mask.any():
            assert (df.loc[five_mask, OUT_COL] == 1.0).all()


def main() -> None:
    df = load_recipe_data(REVIEW_CSV)
    df = df.drop(columns=["star_idf"], errors="ignore")
    df = apply_star_norm(df)
    save_recipe_data(df, REVIEW_CSV)
    mapped = int(df[OUT_COL].notna().sum())
    print(f"star_norm 적재 완료: {mapped}/{len(df)}행")


if __name__ == "__main__":
    _self_check()
    main()
