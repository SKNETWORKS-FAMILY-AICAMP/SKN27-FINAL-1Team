"""메타·재료 파생 feature 및 train-only commonness."""

from __future__ import annotations

import ast
import json
from typing import Any

import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin

from etl.recipe.load_to_postgres.loader import (
    parse_cooking_time_minutes,
    parse_serving_size,
)


def _parse_normalized_list(raw: Any) -> list[list[Any]]:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return []
    text = str(raw).strip()
    if not text or text == "[]":
        return []
    try:
        parsed = ast.literal_eval(text)
    except (SyntaxError, ValueError):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return []
    if not isinstance(parsed, list):
        return []
    return [row for row in parsed if isinstance(row, (list, tuple)) and row]


def _ingredient_names(normalized: list[list[Any]]) -> list[str]:
    names: list[str] = []
    for row in normalized:
        name = str(row[0]).strip() if row else ""
        if name:
            names.append(name)
    return names


def build_meta_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["serving_size"] = out["CKG_INBUN_NM"].map(parse_serving_size)
    out["cooking_time_min"] = out["CKG_TIME_NM"].map(parse_cooking_time_minutes)
    return out


def build_basic_ingredient_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    counts: list[int] = []
    unique_counts: list[int] = []
    others: list[int] = []
    others_ratios: list[float] = []
    alias_ratios: list[float] = []

    for _, row in out.iterrows():
        normalized = _parse_normalized_list(row.get("ingredients_normalized"))
        count = len(normalized)
        names = _ingredient_names(normalized)
        unique_count = len(set(names))
        others_count = row.get("others_count")
        if pd.isna(others_count):
            others_items = _parse_normalized_list(row.get("others_items"))
            others_count = len(others_items)
        others_count = int(others_count)
        ratio = others_count / count if count else 0.0
        counts.append(count)
        unique_counts.append(unique_count)
        others.append(others_count)
        others_ratios.append(ratio)
        alias_ratios.append(1.0 - ratio)

    out["ingredient_count"] = counts
    out["unique_ingredient_count"] = unique_counts
    out["others_count"] = others
    out["others_ratio"] = others_ratios
    out["alias_match_ratio"] = alias_ratios
    return out


class IngredientCommonnessLookup:
    """train set 기준 재료 등장 레시피 수 → 레시피별 commonness_mean."""

    def __init__(self) -> None:
        self._counts: dict[str, int] = {}

    def fit(self, train_df: pd.DataFrame) -> IngredientCommonnessLookup:
        counts: dict[str, int] = {}
        for _, row in train_df.iterrows():
            names = set(_ingredient_names(_parse_normalized_list(row.get("ingredients_normalized"))))
            for name in names:
                counts[name] = counts.get(name, 0) + 1
        self._counts = counts
        return self

    def transform(self, df: pd.DataFrame) -> pd.Series:
        means: list[float] = []
        for _, row in df.iterrows():
            names = _ingredient_names(_parse_normalized_list(row.get("ingredients_normalized")))
            if not names:
                means.append(0.0)
                continue
            vals = [float(self._counts.get(n, 0)) for n in names]
            means.append(sum(vals) / len(vals))
        return pd.Series(means, index=df.index, name="commonness_mean")


def build_all_features(df: pd.DataFrame) -> pd.DataFrame:
    return build_basic_ingredient_features(build_meta_features(df))


def apply_commonness(df: pd.DataFrame, lookup: IngredientCommonnessLookup) -> pd.DataFrame:
    out = df.copy()
    out["commonness_mean"] = lookup.transform(out)
    return out


class RecommendationFeatureBuilder(BaseEstimator, TransformerMixin):
    """Build every model feature and retain train-only ingredient statistics."""

    def fit(self, X: pd.DataFrame, y: Any = None) -> RecommendationFeatureBuilder:
        featured = build_all_features(X)
        self.commonness_lookup_ = IngredientCommonnessLookup().fit(featured)
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        if not hasattr(self, "commonness_lookup_"):
            raise RuntimeError("RecommendationFeatureBuilder must be fitted before transform")
        return apply_commonness(build_all_features(X), self.commonness_lookup_)


def run_self_check() -> None:
    sample = pd.DataFrame(
        {
            "RCP_SNO": [1, 2],
            "ingredients_normalized": [
                '[["소금", "1", "t"], ["설탕", "2", "t"]]',
                '[["소금", "1", "t"], ["후추", "1", "t"]]',
            ],
            "others_count": [0, 1],
            "others_items": ["[]", '[{"raw": "x"}]'],
            "CKG_INBUN_NM": ["2인분", "1인분"],
            "CKG_TIME_NM": ["30분", "1시간"],
        }
    )
    featured = build_all_features(sample)
    assert featured.loc[0, "ingredient_count"] == 2
    assert featured.loc[0, "unique_ingredient_count"] == 2
    assert featured.loc[0, "others_ratio"] == 0.0
    assert featured.loc[1, "alias_match_ratio"] == 0.5

    lookup = IngredientCommonnessLookup().fit(featured)
    common = lookup.transform(featured)
    assert common.iloc[0] == 1.5
    assert common.iloc[1] == 1.5

    train = featured.iloc[[0]]
    test = featured.iloc[[1]]
    lookup2 = IngredientCommonnessLookup().fit(train)
    test_common = lookup2.transform(test)
    assert test_common.iloc[0] == 0.5


if __name__ == "__main__":
    run_self_check()
    print("features self-check OK")
