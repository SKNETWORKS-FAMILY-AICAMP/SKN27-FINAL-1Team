"""review_by_llm.csv star_count → 정규화×IDF(star_idf) 컬럼 적재."""

from __future__ import annotations

import pathlib
import sys
from math import isclose, log

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent.parent
if __package__ is None:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from etl.recipe.preprocessing.recipe_processing import load_recipe_data, save_recipe_data

REVIEW_CSV = ROOT / "storage" / "processed" / "recipe" / "review_by_llm.csv"
OUT_COL = "star_idf"
NORMALIZED_STAR_MAP = {1: -1.0, 2: -0.5, 3: 0.0, 4: 0.5, 5: 1.0}
STAR_BAND_MAP = {
    1: (-1.0, -0.75),
    2: (-0.75, -0.25),
    3: (-0.25, 0.25),
    4: (0.25, 0.75),
    5: (0.75, 1.0),
}


def _valid_star_counts(star_counts: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(star_counts, errors="coerce")
    integer_only = numeric.where(numeric.mod(1).eq(0))
    valid = integer_only.dropna().astype(int)
    valid = valid[valid.between(1, 5)]
    return valid


def compute_idf_mapping(star_counts: pd.Series) -> dict[int, float]:
    valid = _valid_star_counts(star_counts)
    if valid.empty:
        raise ValueError("유효한 star_count(1~5)가 없습니다.")
    counts = valid.value_counts().sort_index().reindex(range(1, 6), fill_value=0)
    total = int(counts.sum())
    return {star: log(total / int(df)) for star, df in counts.items() if df > 0}


def _idf_scale(idf_mapping: dict[int, float]) -> dict[int, float]:
    values = list(idf_mapping.values())
    min_idf = min(values)
    max_idf = max(values)
    if isclose(min_idf, max_idf):
        return {star: 0.5 for star in idf_mapping}
    return {star: (value - min_idf) / (max_idf - min_idf) for star, value in idf_mapping.items()}


def _adjust_score_within_band(star: int, scale: float) -> float:
    low, high = STAR_BAND_MAP[star]
    base = NORMALIZED_STAR_MAP[star]
    if base < 0:
        inner = high
        outer = low
    elif base > 0:
        inner = low
        outer = high
    else:
        return 0.0
    bounded_scale = 0.05 + 0.9 * scale
    # ponytail: IDF 영향은 구간 내부로 제한해 별점 순서 역전을 방지. upgrade: 데이터 기반 비선형 보정식 적용
    return inner + (outer - inner) * bounded_scale


def apply_star_idf(
    df: pd.DataFrame,
    *,
    star_col: str = "star_count",
    out_col: str = OUT_COL,
) -> pd.DataFrame:
    idf_mapping = compute_idf_mapping(df[star_col])
    scale_mapping = _idf_scale(idf_mapping)
    valid = _valid_star_counts(df[star_col])
    adjusted_scores = valid.apply(lambda star: _adjust_score_within_band(int(star), scale_mapping[int(star)]))
    df[out_col] = pd.NA
    df.loc[valid.index, out_col] = adjusted_scores
    return df


def _self_check() -> None:
    toy = pd.DataFrame({"star_count": [1, 1, 2, 3, 4, 5, 5, None, 6]})
    out = apply_star_idf(toy.copy())
    idf_mapping = compute_idf_mapping(toy["star_count"])
    scale_mapping = _idf_scale(idf_mapping)
    assert NORMALIZED_STAR_MAP == {1: -1.0, 2: -0.5, 3: 0.0, 4: 0.5, 5: 1.0}
    assert idf_mapping[2] > idf_mapping[1]
    assert isclose(scale_mapping[2], 1.0)

    mapped = {star: _adjust_score_within_band(star, scale_mapping[star]) for star in range(1, 6)}
    assert -1.0 <= mapped[1] <= -0.75
    assert -0.75 <= mapped[2] <= -0.25
    assert mapped[3] == 0.0
    assert 0.25 <= mapped[4] <= 0.75
    assert 0.75 <= mapped[5] <= 1.0
    assert mapped[1] < mapped[2] < mapped[3] < mapped[4] < mapped[5]

    assert isclose(out.loc[out["star_count"] == 1, OUT_COL].iloc[0], mapped[1])
    assert isclose(out.loc[out["star_count"] == 5, OUT_COL].iloc[0], mapped[5])
    assert pd.isna(out.loc[toy["star_count"].isna(), OUT_COL].iloc[0])
    assert pd.isna(out.loc[out["star_count"] == 6, OUT_COL].iloc[0])

    if REVIEW_CSV.exists():
        df = load_recipe_data(REVIEW_CSV)
        df = apply_star_idf(df)
        valid_mask = pd.to_numeric(df["star_count"], errors="coerce").between(1, 5)
        assert df.loc[valid_mask, OUT_COL].notna().all()


def main() -> None:
    df = load_recipe_data(REVIEW_CSV)
    df = apply_star_idf(df)
    save_recipe_data(df, REVIEW_CSV)
    mapped = int(df[OUT_COL].notna().sum())
    print(f"star_idf 적재 완료: {mapped}/{len(df)}행")


if __name__ == "__main__":
    _self_check()
    main()
