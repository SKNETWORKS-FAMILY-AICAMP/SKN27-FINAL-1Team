"""Catalog prefer scores: predict, export, review observables."""

from __future__ import annotations

import numpy as np
import pandas as pd

from config import CATALOG_USER_ID, ExperimentConfig
from preprocess import build_interactions, is_five_star_mask

BAYESIAN_M_DEFAULT = 3.0


def bayesian_average(
    R: pd.Series | np.ndarray,
    v: pd.Series | np.ndarray,
    C: float,
    m: float = BAYESIAN_M_DEFAULT,
) -> np.ndarray:
    """IMDb-style WR = v/(v+m)*R + m/(v+m)*C."""
    R = np.asarray(R, dtype=np.float64).ravel()
    v = np.asarray(v, dtype=np.float64).ravel()
    denom = v + float(m)
    w = np.where(denom > 0.0, v / denom, 0.0)
    return w * R + (1.0 - w) * float(C)


def star_popularity_scores(
    review_df: pd.DataFrame,
    *,
    m: float = BAYESIAN_M_DEFAULT,
) -> tuple[pd.Series, float]:
    """recipe_id -> Bayesian WR on 5-star rate (n_star5/review_n). Returns (scores, global_C)."""
    rid = review_df["recipe_id"].astype(str)
    is5 = is_five_star_mask(review_df).astype(int)
    agg = (
        pd.DataFrame({"recipe_id": rid, "is5": is5})
        .groupby("recipe_id", as_index=True)
        .agg(n_star5=("is5", "sum"), review_n=("is5", "size"))
    )
    rate = agg["n_star5"] / agg["review_n"].clip(lower=1)
    C = float(is5.mean()) if len(is5) else 0.0
    wr = bayesian_average(rate, agg["review_n"], C, m=m)
    return pd.Series(wr, index=agg.index, name="star_pop"), C


def catalog_predict(
    model,
    dataset,
    item_ids: list[str],
    item_features,
    num_threads: int,
) -> np.ndarray:
    user_id_map, _, item_id_map, _ = dataset.mapping()
    catalog_user_idx = user_id_map[CATALOG_USER_ID]
    item_internal = np.array([item_id_map[i] for i in item_ids], dtype=np.int32)
    user_internal = np.full(len(item_ids), catalog_user_idx, dtype=np.int32)
    return model.predict(
        user_internal,
        item_internal,
        item_features=item_features,
        num_threads=num_threads,
    ).astype(float)


def aggregate_review_for_export(review_raw: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    out = review_raw.copy()
    out["recipe_id"] = out["recipe_id"].astype(str)
    review_agg = (
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
    review_agg["review_rank_score"] = review_agg["star_norm_avg"]
    formula = "star_norm_avg (export observable)"
    return review_agg, formula


def prefer_threshold_min(true_scores: np.ndarray) -> float:
    s = np.asarray(true_scores, dtype=np.float64).ravel()
    s = s[np.isfinite(s)]
    return float(np.min(s)) if s.size else float("nan")


def _linear_calibration(
    s_pref: np.ndarray, bar: np.ndarray, warm_mask: np.ndarray
) -> tuple[float, float]:
    obs = bar[warm_mask]
    pred = s_pref[warm_mask]
    finite = np.isfinite(obs) & np.isfinite(pred)
    obs, pred = obs[finite], pred[finite]
    if obs.size < 2:
        return 0.0, float(obs.mean()) if obs.size else 0.0
    slope, intercept = np.polyfit(pred, obs, 1)
    return float(slope), float(intercept)


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
    bar = export_df["review_rank_score"].to_numpy(dtype=float)
    slope, intercept = _linear_calibration(s_pref, bar, warm_mask)
    export_df["y_hat_linear"] = slope * s_pref + intercept

    warm_y = export_df.loc[warm_mask, "recipe_id"].map(y_prefer).fillna(0).astype(int).to_numpy()
    warm_s = export_df.loc[warm_mask, "s_pref"].to_numpy(dtype=float)
    t_star = prefer_threshold_min(warm_s[warm_y == 1])

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


def full_fit_export(
    cfg: ExperimentConfig,
    *,
    recipe_df: pd.DataFrame,
    review_df: pd.DataFrame,
    dataset,
    item_ids: list[str],
    warm_item_ids: set[str],
    item_features,
    y_prefer: pd.Series,
    review_agg: pd.DataFrame,
    n_star5: pd.Series,
) -> pd.DataFrame:
    from lightfm import LightFM

    interactions, _, _ = build_interactions(
        review_df, dataset, cfg, recipe_prefer_labels=y_prefer
    )
    model = LightFM(loss="warp", random_state=cfg.seed)
    model.fit(
        interactions,
        item_features=item_features,
        epochs=cfg.epochs,
        num_threads=cfg.num_threads,
    )
    s_pref = catalog_predict(model, dataset, item_ids, item_features, cfg.num_threads)
    return build_export_dataframe(
        recipe_df=recipe_df,
        review_agg=review_agg,
        s_pref=s_pref,
        y_prefer=y_prefer,
        n_star5=n_star5,
        warm_item_ids=warm_item_ids,
    )


if __name__ == "__main__":
    toy = pd.DataFrame(
        {
            "recipe_id": ["a", "a", "a", "b", "b"],
            "star_count": [5, 5, 3, 5, 3],
            "star_norm": [1.0, 1.0, 0.0, 1.0, 0.0],
            "positive": [0.8, 0.6, 0.3, 0.3, 0.4],
            "negative": [0.1, 0.2, 0.4, 0.4, 0.2],
        }
    )
    agg, formula = aggregate_review_for_export(toy)
    assert float(agg.loc[agg["recipe_id"] == "a", "star_norm_avg"].iloc[0]) == 2 / 3
    y = pd.Series({"a": 1, "b": 0}, name="y_prefer")
    n5 = pd.Series({"a": 2, "b": 0}, name="n_star5")
    recipe = pd.DataFrame(
        {"recipe_id": ["a", "b", "c"], "recipe_name": ["A", "B", "C"]}
    )
    df = build_export_dataframe(
        recipe_df=recipe,
        review_agg=agg,
        s_pref=np.array([0.9, 0.1, 0.05]),
        y_prefer=y,
        n_star5=n5,
        warm_item_ids={"a", "b"},
    )
    assert df.iloc[0]["recipe_id"] == "a" and int(df.iloc[0]["prefer_rank"]) == 1
    assert int(df.loc[df["recipe_id"] == "c", "is_warm"].iloc[0]) == 0
    pop, c = star_popularity_scores(toy)
    assert float(pop["a"]) > float(pop["b"]) and c > 0
    print("scoring ok", formula, float(df.iloc[0]["t_star"]), float(pop["a"]))
