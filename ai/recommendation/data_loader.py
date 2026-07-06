"""레시피 CSV 로드 및 labeled/unlabeled 분리."""

from __future__ import annotations

import pandas as pd

from .config import INGREDIENT_ALIAS_CSV, RECIPE_FIX_CSV, TARGET_COL


def load_and_merge() -> pd.DataFrame:
    recipe = pd.read_csv(RECIPE_FIX_CSV)
    alias = pd.read_csv(INGREDIENT_ALIAS_CSV)
    recipe["RCP_SNO"] = pd.to_numeric(recipe["RCP_SNO"], errors="coerce").astype("Int64")
    alias["RCP_SNO"] = pd.to_numeric(alias["RCP_SNO"], errors="coerce").astype("Int64")
    merged = recipe.merge(alias, on="RCP_SNO", how="left", suffixes=("", "_alias"))
    if "CKG_NM_alias" in merged.columns:
        merged = merged.drop(columns=["CKG_NM_alias"])
    return merged


def split_labeled_unlabeled(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    labeled = df[df[TARGET_COL].notna()].copy()
    unlabeled = df[df[TARGET_COL].isna()].copy()
    return labeled, unlabeled
