"""review_by_llm.csv star_count → 전역 CDF upper(star_cdf_upper) 컬럼 적재."""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent.parent
if __package__ is None:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from etl.recipe.preprocessing.recipe_processing import load_recipe_data, save_recipe_data

REVIEW_CSV = ROOT / "storage" / "processed" / "recipe" / "review_by_llm.csv"
OUT_COL = "star_cdf_upper"


def compute_cdf_upper_mapping(star_counts: pd.Series) -> dict[int, float]:
    valid = star_counts.dropna().astype(int)
    valid = valid[valid.between(1, 5)]
    if valid.empty:
        raise ValueError("유효한 star_count(1~5)가 없습니다.")
    counts = valid.value_counts().sort_index().reindex(range(1, 6), fill_value=0)
    cdf = counts.cumsum() / counts.sum()
    return cdf.to_dict()


def apply_star_cdf_upper(
    df: pd.DataFrame,
    *,
    star_col: str = "star_count",
    out_col: str = OUT_COL,
) -> pd.DataFrame:
    mapping = compute_cdf_upper_mapping(df[star_col])
    df[out_col] = df[star_col].map(mapping)
    return df


def _self_check() -> None:
    toy = pd.DataFrame({"star_count": [1, 1, 2, 5, 5, None, 6]})
    out = apply_star_cdf_upper(toy.copy())
    mapping = compute_cdf_upper_mapping(toy["star_count"])
    assert mapping[1] == 0.4
    assert mapping[2] == 0.6
    assert mapping[5] == 1.0
    assert out.loc[out["star_count"] == 1, OUT_COL].iloc[0] == 0.4
    assert out.loc[out["star_count"] == 5, OUT_COL].iloc[0] == 1.0
    assert pd.isna(out.loc[toy["star_count"].isna(), OUT_COL].iloc[0])
    assert pd.isna(out.loc[out["star_count"] == 6, OUT_COL].iloc[0])

    keys = sorted(k for k in mapping if 1 <= k <= 5)
    assert all(mapping[keys[i]] <= mapping[keys[i + 1]] for i in range(len(keys) - 1))
    assert mapping[5] == 1.0

    if REVIEW_CSV.exists():
        df = load_recipe_data(REVIEW_CSV)
        df = apply_star_cdf_upper(df)
        assert (df.loc[df["star_count"] == 5, OUT_COL] == 1.0).all()


def main() -> None:
    df = load_recipe_data(REVIEW_CSV)
    df = apply_star_cdf_upper(df)
    save_recipe_data(df, REVIEW_CSV)
    mapped = int(df[OUT_COL].notna().sum())
    print(f"star_cdf_upper 적재 완료: {mapped}/{len(df)}행")


if __name__ == "__main__":
    _self_check()
    main()
