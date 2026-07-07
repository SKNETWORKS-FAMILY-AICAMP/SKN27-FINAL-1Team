"""레시피 CSV 로드 및 labeled/unlabeled 분리."""

from __future__ import annotations

import warnings

import pandas as pd

from .config import INGREDIENT_ALIAS_CSV, RECIPE_FIX_CSV, TARGET_COL

_ALIAS_DEFAULTS = {
    "ingredients_normalized": "[]",
    "others_count": 0,
    "others_items": "[]",
    "basic_count": 0,
    "basic_items": "[]",
    "aliases_matched": "[]",
}
_ALIAS_REQUIRED_COLS = frozenset(
    {"RCP_SNO", "ingredients_normalized", "others_count", "others_items"}
)


def _normalize_rcp_sno(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["RCP_SNO"] = pd.to_numeric(out["RCP_SNO"], errors="coerce").astype("Int64")
    return out


def _dedupe_alias(alias: pd.DataFrame) -> pd.DataFrame:
    dup_count = int(alias["RCP_SNO"].duplicated().sum())
    if dup_count:
        warnings.warn(
            f"recipe_ingredient_alias.csv: {dup_count} duplicate RCP_SNO rows; keeping last",
            stacklevel=2,
        )
        return alias.drop_duplicates(subset=["RCP_SNO"], keep="last")
    return alias


def _load_alias() -> pd.DataFrame | None:
    if not INGREDIENT_ALIAS_CSV.is_file():
        return None
    alias = pd.read_csv(INGREDIENT_ALIAS_CSV)
    missing = _ALIAS_REQUIRED_COLS - set(alias.columns)
    if missing:
        raise ValueError(
            f"recipe_ingredient_alias.csv is missing required columns: {sorted(missing)}"
        )
    return _normalize_rcp_sno(alias)


def load_and_merge() -> pd.DataFrame:
    recipe = _normalize_rcp_sno(pd.read_csv(RECIPE_FIX_CSV))
    if recipe["RCP_SNO"].isna().any():
        raise ValueError("recipe_fix.csv contains missing or invalid RCP_SNO values")
    if recipe["RCP_SNO"].duplicated().any():
        raise ValueError("recipe_fix.csv contains duplicate RCP_SNO values")
    alias = _load_alias()
    if alias is None:
        merged = recipe.copy()
        for col, default in _ALIAS_DEFAULTS.items():
            merged[col] = default
        return merged

    alias = _dedupe_alias(alias)
    merged = recipe.merge(alias, on="RCP_SNO", how="left", suffixes=("", "_alias"))
    if "CKG_NM_alias" in merged.columns:
        merged = merged.drop(columns=["CKG_NM_alias"])
    for col, default in _ALIAS_DEFAULTS.items():
        if col not in merged.columns:
            merged[col] = default
        merged[col] = merged[col].fillna(default)
    return merged


def split_labeled_unlabeled(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    labeled = df[df[TARGET_COL].notna()].copy()
    unlabeled = df[df[TARGET_COL].isna()].copy()
    return labeled, unlabeled


if __name__ == "__main__":
    merged = load_and_merge()
    for col in _ALIAS_DEFAULTS:
        assert col in merged.columns, col
    assert len(merged) == len(pd.read_csv(RECIPE_FIX_CSV))

    dup_alias = pd.DataFrame(
        {
            "RCP_SNO": [1, 1],
            "ingredients_normalized": ["[]", '[["a", "1", "t"]]'],
            "others_count": [0, 1],
            "others_items": ["[]", "[]"],
        }
    )
    recipe_one = pd.DataFrame({"RCP_SNO": [1], "CKG_NM": ["x"]})
    deduped = _dedupe_alias(dup_alias)
    assert len(recipe_one.merge(deduped, on="RCP_SNO", how="left")) == 1
    print("data_loader self-check OK")
