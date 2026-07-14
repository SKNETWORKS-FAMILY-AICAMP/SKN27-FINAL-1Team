"""DataFrame preprocessing and LightFM feature construction (prefer WARP)."""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from config import CATALOG_USER_ID

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

PREFER_RECIPE_MODES = ("prefer_n_star5_ge2", "prefer_n_star5_ge2_five_star_rows")
FIVE_STAR_ONLY_MODE = "five_star_reviews_only"


def prepare_review_frame(review_df: pd.DataFrame) -> pd.DataFrame:
    out = review_df.copy()
    out["star"] = (out["star_count"].astype(float) - 3.0) / 2.0
    return out.drop(
        columns=["content", "positive", "negative", "star_norm"],
        errors="ignore",
    )


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
    review_out = prepare_review_frame(review_df)
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


def is_five_star_mask(review_df: pd.DataFrame) -> pd.Series:
    if "star_count" in review_df.columns:
        return pd.to_numeric(review_df["star_count"], errors="coerce") == 5
    if "star" in review_df.columns:
        return pd.to_numeric(review_df["star"], errors="coerce") >= 0.999
    raise ValueError("need star_count or star for five-star mask")


def build_prefer_labels(review_df: pd.DataFrame) -> pd.Series:
    """recipe_id -> 1 if n_star5≥2 else 0."""
    rid = review_df["recipe_id"].astype(str)
    n5 = is_five_star_mask(review_df).groupby(rid).sum().rename("n_star5")
    warm = rid.value_counts().rename("review_n")
    out = pd.DataFrame({"review_n": warm, "n_star5": n5.reindex(warm.index).fillna(0)})
    return (out["n_star5"] >= 2).astype(int).rename("y_prefer")


def recipe_n_star5_counts(review_df: pd.DataFrame) -> pd.Series:
    rid = review_df["recipe_id"].astype(str)
    return is_five_star_mask(review_df).groupby(rid).sum().rename("n_star5")


def add_prefer_label_column(
    review_df: pd.DataFrame,
    recipe_labels: pd.Series | None = None,
) -> pd.DataFrame:
    out = review_df.copy()
    rid = out["recipe_id"].astype(str)
    if recipe_labels is None:
        recipe_labels = build_prefer_labels(out)
    out["prefer_label"] = rid.map(recipe_labels).fillna(0).astype(int)
    return out


def build_interactions(
    review_df: pd.DataFrame,
    dataset,
    cfg: ExperimentConfig,
    *,
    recipe_prefer_labels: pd.Series | None = None,
):
    """Return (interactions, review_with_labels, None).

    WARP matrix = implicit (user, item) pairs only:
    - prefer_n_star5_ge2: all reviews on y*=1 recipes
    - prefer_n_star5_ge2_five_star_rows: five-star rows on y*=1 recipes
    - five_star_reviews_only: all five-star review rows (y* ignored)
    """
    positive_mode = getattr(cfg, "positive_mode", "prefer_n_star5_ge2")
    labels = (
        build_prefer_labels(review_df)
        if recipe_prefer_labels is None
        else recipe_prefer_labels
    )
    review_with_iv = add_prefer_label_column(review_df, labels)

    if positive_mode == FIVE_STAR_ONLY_MODE:
        review_fit = review_with_iv[is_five_star_mask(review_with_iv)].copy()
    else:
        review_fit = review_with_iv[review_with_iv["prefer_label"] == 1].copy()
        if positive_mode == "prefer_n_star5_ge2_five_star_rows":
            review_fit = review_fit[is_five_star_mask(review_fit)].copy()

    users = review_fit["group_id"].astype(str)
    items = review_fit["recipe_id"].astype(str)
    interactions, _ = dataset.build_interactions(zip(users, items))
    return interactions, review_with_iv, None


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
        if col in excluded:
            continue
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
    dataset,
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
            "star_count": [5],
            "content": ["ok"],
            "positive": [0.8],
            "negative": [0.1],
            "star_norm": [1.0],
        }
    )
    r, rev = prepare_training_frames(review, recipe, alias)
    assert "star_count" in rev.columns and str(r["recipe_id"].iloc[0]) == "1"
    feats = recipe_row_to_features(
        {"view_count": 10, "scrap_count": 5, "method": "볶음"},
        excluded={"view_count", "scrap_count", "ingredients"},
        log_numeric_columns={"view_count", "scrap_count"},
    )
    assert not any(t.startswith("view_count") or t.startswith("scrap_count") for t in feats)

    rev3 = pd.DataFrame(
        {"recipe_id": ["p", "p", "q"], "star_count": [5, 5, 5], "group_id": ["u1", "u2", "u3"]}
    )
    labels = build_prefer_labels(rev3)
    assert int(labels["p"]) == 1 and int(labels["q"]) == 0
    tagged = add_prefer_label_column(rev3, labels)
    assert tagged["prefer_label"].tolist() == [1, 1, 0]

    rev4 = pd.DataFrame(
        {
            "recipe_id": ["p", "p", "p", "q"],
            "star_count": [5, 5, 3, 5],
            "group_id": ["u1", "u2", "u3", "u4"],
        }
    )
    lbl4 = build_prefer_labels(rev4)
    tagged4 = add_prefer_label_column(rev4, lbl4)
    base_fit = tagged4[tagged4["prefer_label"] == 1]
    assert len(base_fit) == 3
    five_star_fit = base_fit[is_five_star_mask(base_fit)]
    assert len(five_star_fit) == 2
    print("preprocess ok")
