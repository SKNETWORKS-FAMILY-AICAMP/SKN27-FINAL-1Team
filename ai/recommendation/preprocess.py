"""DataFrame preprocessing and LightFM feature construction."""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from config import CATALOG_USER_ID
from scoring import add_interaction_column, sentiment_02_from_sentiment, star_02_from_star

if TYPE_CHECKING:
    from config import ExperimentConfig

COLUMN_RENAME_MAP = {
    "RCP_SNO": "recipe_id",
    "CKG_NM": "recipe_name",
    "INQ_CNT": "view_count",
    "SRAP_CNT": "scrap_count",
    "CKG_MTH_ACTO_NM": "cooking_method",
    "CKG_STA_ACTO_NM": "cooking_category",
    "CKG_MTRL_ACTO_NM": "main_ingred",
    "CKG_KND_ACTO_NM": "recipe_kind",
    "CKG_INBUN_NM": "dishes",
    "CKG_DODF_NM": "cooking_level",
    "CKG_TIME_NM": "cooking_time",
    "aliases_matched": "aliases",
    "ingredients_normalized": "ingredients",
}
COLUMNS_TO_DROP = ["ingredients_raw", "others_items", "basic_items"]

FIXED_POPULARITY_COLUMNS = ["view_count", "scrap_count"]
LOG_NUMERIC_COLUMNS = set(FIXED_POPULARITY_COLUMNS)
CATEGORICAL_COLUMNS = [
    "recipe_name",
    "cooking_method",
    "cooking_category",
    "main_ingred",
    "dishes",
    "cooking_level",
    "cooking_time",
    "recipe_kind",
]
NUMERIC_COLUMNS = ["others_count", "basic_count"]


def preprocess_review_star(review_df: pd.DataFrame) -> pd.DataFrame:
    out = review_df.copy()
    out["star"] = out["star_count"].astype(float).apply(lambda x: (x - 3) / 2)
    return out.drop(columns=["star_count", "star_norm"], errors="ignore")


def preprocess_review_sentiment(review_df: pd.DataFrame) -> pd.DataFrame:
    out = review_df.copy()
    out["sentiment"] = out["positive"].astype(float) - out["negative"].astype(float)
    out = out.drop(columns=["positive", "negative", "neutral", "compound"], errors="ignore")
    out["star_02"] = star_02_from_star(out["star"])
    out["sentiment_02"] = sentiment_02_from_sentiment(out["sentiment"])
    return out


def drop_review_content(review_df: pd.DataFrame) -> pd.DataFrame:
    return review_df.drop(columns=["content"], errors="ignore")


def merge_recipe_alias(recipe_df: pd.DataFrame, alias_df: pd.DataFrame) -> pd.DataFrame:
    recipe_base_cols = set(recipe_df.columns)
    alias_merge_cols = [
        col for col in alias_df.columns if col == "RCP_SNO" or col not in recipe_base_cols
    ]
    return recipe_df.merge(alias_df[alias_merge_cols].copy(), on="RCP_SNO", how="left")


def rename_recipe_columns(recipe_df: pd.DataFrame) -> pd.DataFrame:
    out = recipe_df.rename(columns=COLUMN_RENAME_MAP)
    return out.drop(columns=[c for c in COLUMNS_TO_DROP if c in out.columns])


def str_to_list(value):
    if pd.isna(value):
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = ast.literal_eval(value)
            return parsed if isinstance(parsed, list) else []
        except (ValueError, SyntaxError):
            return []
    return []


def normalize_aliases(values):
    normalized = []
    for item in str_to_list(values):
        if isinstance(item, dict):
            token = item.get("alias_id") or item.get("name")
            if token:
                normalized.append(str(token))
        elif isinstance(item, str):
            normalized.append(item)
    return sorted(set(normalized))


def normalize_ingredients(values):
    normalized = []
    for item in str_to_list(values):
        if isinstance(item, list) and len(item) > 0 and item[0]:
            normalized.append(str(item[0]))
        elif isinstance(item, str):
            normalized.append(item)
    return sorted(set(normalized))


def apply_recipe_token_columns(recipe_df: pd.DataFrame) -> pd.DataFrame:
    out = recipe_df.copy()
    out["aliases"] = out["aliases"].apply(normalize_aliases)
    out["ingredients"] = out["ingredients"].apply(normalize_ingredients)
    return out


def validate_id_integrity(recipe_df: pd.DataFrame, review_df: pd.DataFrame) -> dict:
    recipe_id_set = set(recipe_df["recipe_id"].astype(str).str.strip())
    review_recipe_id_set = set(review_df["recipe_id"].astype(str).str.strip())
    unmatched = review_recipe_id_set - recipe_id_set
    return {
        "missing_recipe_ids": int(
            recipe_df["recipe_id"].isnull().sum()
            + (recipe_df["recipe_id"].astype(str).str.strip() == "").sum()
        ),
        "missing_review_recipe_ids": int(
            review_df["recipe_id"].isnull().sum()
            + (review_df["recipe_id"].astype(str).str.strip() == "").sum()
        ),
        "missing_review_group_ids": int(
            review_df["group_id"].isnull().sum()
            + (review_df["group_id"].astype(str).str.strip() == "").sum()
        ),
        "unmatched_recipe_ids": len(unmatched),
        "duplicated_pairs": int(
            review_df.duplicated(subset=["group_id", "recipe_id"], keep=False).sum()
        ),
        "matched_reviews": int(
            review_df[review_df["recipe_id"].astype(str).str.strip().isin(recipe_id_set)].shape[0]
        ),
        "total_reviews": int(review_df.shape[0]),
    }


def filter_valid_ids(
    recipe_df: pd.DataFrame, review_df: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    recipe_id_set = set(recipe_df["recipe_id"].astype(str).str.strip())
    review_out = review_df[
        review_df["recipe_id"].astype(str).str.strip().isin(recipe_id_set)
    ].copy()
    review_out = review_out[
        review_out["group_id"].notnull()
        & (review_out["group_id"].astype(str).str.strip() != "")
    ]
    recipe_out = recipe_df[
        recipe_df["recipe_id"].notnull()
        & (recipe_df["recipe_id"].astype(str).str.strip() != "")
    ].copy()
    return recipe_out, review_out


def prepare_training_frames(
    review_df: pd.DataFrame,
    recipe_df: pd.DataFrame,
    alias_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    review_out = preprocess_review_star(review_df)
    review_out = preprocess_review_sentiment(review_out)
    review_out = drop_review_content(review_out)
    recipe_out = merge_recipe_alias(recipe_df, alias_df)
    recipe_out = rename_recipe_columns(recipe_out)
    recipe_out = apply_recipe_token_columns(recipe_out)
    validate_id_integrity(recipe_out, review_out)
    return filter_valid_ids(recipe_out, review_out)


def build_lightfm_ids(
    review_df: pd.DataFrame, recipe_df: pd.DataFrame
) -> tuple:
    from lightfm.data import Dataset

    user_ids = review_df["group_id"].astype(str).unique().tolist()
    item_ids = recipe_df["recipe_id"].astype(str).tolist()
    warm_item_ids = set(review_df["recipe_id"].astype(str).unique())
    cold_item_ids = [i for i in item_ids if i not in warm_item_ids]
    dataset = Dataset()
    dataset.fit(users=user_ids + [CATALOG_USER_ID], items=item_ids)
    return dataset, item_ids, warm_item_ids, cold_item_ids, user_ids


def build_interactions(
    review_df: pd.DataFrame, dataset: Dataset, cfg: ExperimentConfig
):
    review_with_iv = add_interaction_column(review_df, cfg)
    triples = list(
        zip(
            review_with_iv["group_id"].astype(str),
            review_with_iv["recipe_id"].astype(str),
            review_with_iv["interaction_value"].astype(float),
        )
    )
    interactions, _ = dataset.build_interactions(triples)
    return interactions, review_with_iv


def transform_numeric_feature(col: str, value, log_numeric_columns: set[str]):
    if pd.isna(value):
        return None
    v = max(0.0, float(value))
    if col in log_numeric_columns:
        return f"{col}_log:{np.log1p(v):.4f}"
    return f"{col}:{int(v)}"


def recipe_row_to_features(row, excluded: set[str], log_numeric_columns: set[str]):
    features = []
    for col in FIXED_POPULARITY_COLUMNS:
        token = transform_numeric_feature(col, row.get(col), log_numeric_columns)
        if token:
            features.append(token)
    for col in CATEGORICAL_COLUMNS:
        if col in excluded:
            continue
        val = row.get(col)
        if pd.notna(val) and str(val).strip():
            features.append(f"{col}:{str(val).strip()}")
    for col in NUMERIC_COLUMNS:
        if col in excluded:
            continue
        token = transform_numeric_feature(col, row.get(col), log_numeric_columns)
        if token:
            features.append(token)
    if "aliases" not in excluded:
        for token in row.get("aliases") or []:
            features.append(f"alias:{token}")
    if "ingredients" not in excluded:
        for token in row.get("ingredients") or []:
            features.append(f"ingredient:{token}")
    return features or ["recipe:unknown"]


def build_item_features(
    recipe_df: pd.DataFrame,
    item_ids: list[str],
    dataset: Dataset,
    excluded_recipe_columns: list[str],
):
    excluded = set(excluded_recipe_columns)
    recipe_lookup = recipe_df.set_index(recipe_df["recipe_id"].astype(str))
    item_feature_tuples = []
    all_feature_names: set[str] = set()
    for item_id in item_ids:
        if item_id in recipe_lookup.index:
            feats = recipe_row_to_features(
                recipe_lookup.loc[item_id], excluded, LOG_NUMERIC_COLUMNS
            )
        else:
            feats = ["recipe:unknown"]
        item_feature_tuples.append((item_id, feats))
        all_feature_names.update(feats)
    dataset.fit_partial(item_features=sorted(all_feature_names))
    item_features = dataset.build_item_features(item_feature_tuples)
    return item_features, all_feature_names


if __name__ == "__main__":
    recipe = pd.DataFrame(
        {
            "RCP_SNO": [1],
            "CKG_NM": ["test"],
            "INQ_CNT": [10],
            "SRAP_CNT": [5],
            "CKG_MTH_ACTO_NM": ["볶음"],
            "CKG_STA_ACTO_NM": ["일반"],
            "CKG_MTRL_ACTO_NM": ["돼지"],
            "CKG_KND_ACTO_NM": ["한식"],
            "CKG_INBUN_NM": ["2인분"],
            "CKG_DODF_NM": ["초급"],
            "CKG_TIME_NM": ["30분"],
        }
    )
    alias = pd.DataFrame(
        {
            "RCP_SNO": [1],
            "CKG_NM": ["test"],
            "ingredients_raw": ["[]"],
            "aliases_matched": ["[]"],
            "ingredients_normalized": ["[]"],
            "others_count": [0],
            "others_items": ["[]"],
            "basic_count": [0],
            "basic_items": ["[]"],
        }
    )
    review = pd.DataFrame(
        {
            "recipe_id": [1],
            "group_id": ["u1"],
            "star_count": [4],
            "content": ["ok"],
            "positive": [0.8],
            "negative": [0.1],
            "star_norm": [0.5],
        }
    )
    r, rev = prepare_training_frames(review, recipe, alias)
    assert "star_02" in rev.columns and str(r["recipe_id"].iloc[0]) == "1"
    print("preprocess ok")
