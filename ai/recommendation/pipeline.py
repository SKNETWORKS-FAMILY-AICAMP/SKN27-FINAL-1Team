"""Data preprocessing, feature construction, scoring, and export (prefer WARP)."""

from __future__ import annotations

import ast

import numpy as np
import pandas as pd

from config import CATALOG_USER_ID, ExperimentConfig

# --- Column constants ---

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
    "recipe_name", "cooking_method", "cooking_category", "main_ingred",
    "dishes", "cooking_level", "cooking_time", "recipe_kind",
]
NUMERIC_COLUMNS = ["others_count", "basic_count"]

BAYESIAN_M_DEFAULT = 3.0


# --- Preprocessing ---


def _str_to_list(value):
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


def _normalize_aliases(values):
    normalized = []
    for item in _str_to_list(values):
        if isinstance(item, dict):
            token = item.get("alias_id") or item.get("name")
            if token:
                normalized.append(str(token))
        elif isinstance(item, str):
            normalized.append(item)
    return sorted(set(normalized))


def _normalize_ingredients(values):
    normalized = []
    for item in _str_to_list(values):
        if isinstance(item, list) and len(item) > 0 and item[0]:
            normalized.append(str(item[0]))
        elif isinstance(item, str):
            normalized.append(item)
    return sorted(set(normalized))


def prepare_training_frames(
    review_df: pd.DataFrame,
    recipe_df: pd.DataFrame,
    alias_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load raw → merged/renamed/filtered recipe + review frames."""
    review_out = review_df.copy()
    review_out["star"] = (review_out["star_count"].astype(float) - 3.0) / 2.0
    review_out = review_out.drop(columns=["content", "positive", "negative", "star_norm"], errors="ignore")

    recipe_base_cols = set(recipe_df.columns)
    alias_merge_cols = [c for c in alias_df.columns if c == "RCP_SNO" or c not in recipe_base_cols]
    recipe_out = recipe_df.merge(alias_df[alias_merge_cols].copy(), on="RCP_SNO", how="left")
    recipe_out = recipe_out.rename(columns=COLUMN_RENAME_MAP)
    recipe_out = recipe_out.drop(columns=[c for c in COLUMNS_TO_DROP if c in recipe_out.columns])
    recipe_out["aliases"] = recipe_out["aliases"].apply(_normalize_aliases)
    recipe_out["ingredients"] = recipe_out["ingredients"].apply(_normalize_ingredients)

    recipe_id_set = set(recipe_out["recipe_id"].astype(str).str.strip())
    review_out = review_out[review_out["recipe_id"].astype(str).str.strip().isin(recipe_id_set)].copy()
    review_out = review_out[review_out["group_id"].notnull() & (review_out["group_id"].astype(str).str.strip() != "")]
    recipe_out = recipe_out[recipe_out["recipe_id"].notnull() & (recipe_out["recipe_id"].astype(str).str.strip() != "")].copy()
    return recipe_out, review_out


def build_lightfm_ids(review_df: pd.DataFrame, recipe_df: pd.DataFrame) -> tuple:
    from lightfm.data import Dataset

    user_ids = review_df["group_id"].astype(str).unique().tolist()
    item_ids = recipe_df["recipe_id"].astype(str).tolist()
    warm_item_ids = set(review_df["recipe_id"].astype(str).unique())
    cold_item_ids = [i for i in item_ids if i not in warm_item_ids]
    dataset = Dataset()
    dataset.fit(users=user_ids + [CATALOG_USER_ID], items=item_ids)
    return dataset, item_ids, warm_item_ids, cold_item_ids, user_ids


def is_five_star_mask(review_df: pd.DataFrame) -> pd.Series:
    return pd.to_numeric(review_df["star_count"], errors="coerce") == 5


def build_prefer_labels(review_df: pd.DataFrame) -> pd.Series:
    """recipe_id -> 1 if n_star5>=2 else 0."""
    rid = review_df["recipe_id"].astype(str)
    n5 = is_five_star_mask(review_df).groupby(rid).sum().rename("n_star5")
    warm = rid.value_counts().rename("review_n")
    out = pd.DataFrame({"review_n": warm, "n_star5": n5.reindex(warm.index).fillna(0)})
    return (out["n_star5"] >= 2).astype(int).rename("y_prefer")


def recipe_n_star5_counts(review_df: pd.DataFrame) -> pd.Series:
    rid = review_df["recipe_id"].astype(str)
    return is_five_star_mask(review_df).groupby(rid).sum().rename("n_star5")


def build_interactions(review_df: pd.DataFrame, dataset, *, recipe_prefer_labels: pd.Series | None = None):
    """WARP interaction matrix: all reviews on y*=1 recipes (prefer_n_star5_ge2)."""
    labels = build_prefer_labels(review_df) if recipe_prefer_labels is None else recipe_prefer_labels
    rid = review_df["recipe_id"].astype(str)
    review_fit = review_df[rid.map(labels).fillna(0).astype(int) == 1].copy()

    users = review_fit["group_id"].astype(str)
    items = review_fit["recipe_id"].astype(str)
    interactions, _ = dataset.build_interactions(zip(users, items))
    return interactions


# --- Item features ---


def _recipe_row_to_features(row, excluded: set[str]):
    features = []
    for col in FIXED_POPULARITY_COLUMNS:
        if col in excluded:
            continue
        val = row.get(col)
        if pd.notna(val):
            features.append(f"{col}_log:{np.log1p(max(0.0, float(val))):.4f}")
    for col in CATEGORICAL_COLUMNS:
        if col in excluded:
            continue
        val = row.get(col)
        if pd.notna(val) and str(val).strip():
            features.append(f"{col}:{str(val).strip()}")
    for col in NUMERIC_COLUMNS:
        if col in excluded:
            continue
        val = row.get(col)
        if pd.notna(val):
            features.append(f"{col}:{int(max(0.0, float(val)))}")
    if "aliases" not in excluded:
        for token in row.get("aliases") or []:
            features.append(f"alias:{token}")
    if "ingredients" not in excluded:
        for token in row.get("ingredients") or []:
            features.append(f"ingredient:{token}")
    return features or ["recipe:unknown"]


def build_item_features(recipe_df: pd.DataFrame, item_ids: list[str], dataset, excluded_recipe_columns: list[str]):
    excluded = set(excluded_recipe_columns)
    recipe_lookup = recipe_df.set_index(recipe_df["recipe_id"].astype(str))
    item_feature_tuples = []
    all_feature_names: set[str] = set()
    for item_id in item_ids:
        feats = _recipe_row_to_features(recipe_lookup.loc[item_id], excluded) if item_id in recipe_lookup.index else ["recipe:unknown"]
        item_feature_tuples.append((item_id, feats))
        all_feature_names.update(feats)
    dataset.fit_partial(item_features=sorted(all_feature_names))
    item_features = dataset.build_item_features(item_feature_tuples)
    return item_features, all_feature_names


# --- Scoring & Export ---


def catalog_predict(model, dataset, item_ids: list[str], item_features, num_threads: int) -> np.ndarray:
    user_id_map, _, item_id_map, _ = dataset.mapping()
    catalog_user_idx = user_id_map[CATALOG_USER_ID]
    item_internal = np.array([item_id_map[i] for i in item_ids], dtype=np.int32)
    user_internal = np.full(len(item_ids), catalog_user_idx, dtype=np.int32)
    return model.predict(user_internal, item_internal, item_features=item_features, num_threads=num_threads).astype(float)


def bayesian_average(R, v, C: float, m: float = BAYESIAN_M_DEFAULT) -> np.ndarray:
    R = np.asarray(R, dtype=np.float64).ravel()
    v = np.asarray(v, dtype=np.float64).ravel()
    denom = v + float(m)
    w = np.where(denom > 0.0, v / denom, 0.0)
    return w * R + (1.0 - w) * float(C)


def star_popularity_scores(review_df: pd.DataFrame, *, m: float = BAYESIAN_M_DEFAULT) -> tuple[pd.Series, float]:
    """recipe_id -> Bayesian WR on 5-star rate."""
    rid = review_df["recipe_id"].astype(str)
    is5 = is_five_star_mask(review_df).astype(int)
    agg = pd.DataFrame({"recipe_id": rid, "is5": is5}).groupby("recipe_id", as_index=True).agg(
        n_star5=("is5", "sum"), review_n=("is5", "size")
    )
    rate = agg["n_star5"] / agg["review_n"].clip(lower=1)
    C = float(is5.mean()) if len(is5) else 0.0
    wr = bayesian_average(rate, agg["review_n"], C, m=m)
    return pd.Series(wr, index=agg.index, name="star_pop"), C


def aggregate_review_for_export(review_raw: pd.DataFrame) -> pd.DataFrame:
    out = review_raw.copy()
    out["recipe_id"] = out["recipe_id"].astype(str)
    return (
        out.groupby("recipe_id", as_index=False)
        .agg(
            positive_avg=("positive", "mean"),
            negative_avg=("negative", "mean"),
            star_count_avg=("star_count", "mean"),
            star_norm_avg=("star_norm", "mean"),
            review_n=("recipe_id", "size"),
        )
        .assign(recipe_id=lambda d: d["recipe_id"].astype(str))
    )


def build_export_dataframe(
    *,
    recipe_df: pd.DataFrame,
    review_agg: pd.DataFrame,
    s_pref: np.ndarray,
    y_prefer: pd.Series,
    n_star5: pd.Series,
    warm_item_ids: set[str],
) -> pd.DataFrame:
    export_df = recipe_df[["recipe_id", "recipe_name"]].copy()
    export_df["recipe_id"] = export_df["recipe_id"].astype(str)
    export_df = export_df.merge(review_agg, on="recipe_id", how="left")
    export_df["y_hat"] = s_pref
    export_df["s_pref"] = s_pref

    warm_mask = export_df["recipe_id"].isin(warm_item_ids).to_numpy()
    warm_y = export_df.loc[warm_mask, "recipe_id"].map(y_prefer).fillna(0).astype(int).to_numpy()
    warm_s = export_df.loc[warm_mask, "s_pref"].to_numpy(dtype=float)
    t_star = float(np.min(warm_s[warm_y == 1])) if (warm_y == 1).any() else float("nan")

    export_df["t_star"] = t_star
    export_df["prefer_hat"] = (export_df["s_pref"] >= t_star).astype(int)
    export_df["y_prefer"] = export_df["recipe_id"].map(y_prefer).fillna(-1).astype(int)
    export_df["n_star5"] = export_df["recipe_id"].map(n_star5).fillna(0).astype(int)
    export_df["is_warm"] = warm_mask.astype(int)
    return (
        export_df.sort_values("s_pref", ascending=False, kind="mergesort")
        .reset_index(drop=True)
        .assign(prefer_rank=lambda d: np.arange(1, len(d) + 1))
    )


if __name__ == "__main__":
    toy = pd.DataFrame({"recipe_id": ["a", "a", "b"], "star_count": [5, 5, 3], "star_norm": [1.0, 1.0, 0.0], "positive": [0.8, 0.6, 0.3], "negative": [0.1, 0.2, 0.4]})
    labels = build_prefer_labels(toy)
    assert int(labels["a"]) == 1 and int(labels["b"]) == 0
    pop, c = star_popularity_scores(toy)
    assert float(pop["a"]) > float(pop["b"])
    print("pipeline ok")
