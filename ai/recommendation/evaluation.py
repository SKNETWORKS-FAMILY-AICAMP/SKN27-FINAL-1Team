"""Track B catalog metrics: L0~L5 gates, baselines, Spearman subsets."""

from __future__ import annotations

import numpy as np
import pandas as pd

COHEN_SMALL = 0.10
COHEN_MEDIUM = 0.30
NULL_PERMUTATIONS = 1000
L1_POP_WINS_REQUIRED = 4
L1_POP_SEEDS = 5


def ndcg_at_k(scores: np.ndarray, relevance: np.ndarray, k: int = 50) -> float:
    scores = np.asarray(scores, dtype=np.float64).ravel()
    relevance = np.asarray(relevance, dtype=np.float64).ravel()
    if scores.shape != relevance.shape:
        raise ValueError("scores and relevance must have the same shape")
    if scores.size == 0:
        return 0.0

    k = min(k, scores.size)
    order = np.argsort(-scores, kind="stable")[:k]
    gains = np.maximum(relevance[order], 0.0)
    discounts = np.log2(np.arange(2, k + 2, dtype=np.float64))
    dcg = float(np.sum(gains / discounts))

    ideal_order = np.argsort(-relevance, kind="stable")[:k]
    ideal_gains = np.maximum(relevance[ideal_order], 0.0)
    idcg = float(np.sum(ideal_gains / discounts))
    if idcg <= 0.0:
        return 0.0
    return dcg / idcg


def spearman_rho(scores_a: np.ndarray, scores_b: np.ndarray) -> float:
    a = np.asarray(scores_a, dtype=np.float64).ravel()
    b = np.asarray(scores_b, dtype=np.float64).ravel()
    if a.shape != b.shape:
        raise ValueError("scores_a and scores_b must have the same shape")
    if a.size < 2:
        return 0.0
    from scipy.stats import spearmanr

    rho, _ = spearmanr(a, b)
    if np.isnan(rho):
        return 0.0
    return float(rho)


def legacy_review_rank(export_df: pd.DataFrame) -> np.ndarray:
    star = pd.to_numeric(export_df["star_norm_avg"], errors="coerce").fillna(0.0)
    sent = pd.to_numeric(export_df["positive_avg"], errors="coerce").fillna(0.0) - pd.to_numeric(
        export_df["negative_avg"], errors="coerce"
    ).fillna(0.0)
    return (star + sent).to_numpy(dtype=float)


def build_warm_subsets(export_df: pd.DataFrame, warm_mask: np.ndarray) -> dict[str, np.ndarray]:
    """Subset masks on warm rows only (experiment 14 definitions)."""
    warm_mask = np.asarray(warm_mask, dtype=bool).ravel()
    star_norm = pd.to_numeric(export_df["star_norm_avg"], errors="coerce").fillna(1.0).to_numpy()
    legacy = legacy_review_rank(export_df)

    ceiling = warm_mask & (star_norm >= 1.0)
    star_varies = warm_mask & (star_norm < 1.0)
    low_tail = warm_mask & (legacy < 1.5)
    informative = star_varies | low_tail

    return {
        "ceiling": ceiling,
        "star_varies": star_varies,
        "low_tail": low_tail,
        "informative": informative,
        "warm": warm_mask,
    }


def popularity_baseline_scores(recipe_df: pd.DataFrame) -> pd.Series:
    out = recipe_df[["recipe_id"]].copy()
    out["recipe_id"] = out["recipe_id"].astype(str)
    view = pd.to_numeric(recipe_df["view_count"], errors="coerce").fillna(0.0).clip(lower=0.0)
    scrap = pd.to_numeric(recipe_df["scrap_count"], errors="coerce").fillna(0.0).clip(lower=0.0)
    out["popularity_score"] = np.log1p(view) + np.log1p(scrap)
    return out.set_index("recipe_id")["popularity_score"]


def null_spearman_pvalue(
    y_hat: np.ndarray,
    bar: np.ndarray,
    *,
    n_perm: int = NULL_PERMUTATIONS,
    seed: int = 42,
) -> tuple[float, float]:
    """Return (observed_rho, two-sided permutation p vs null ~0)."""
    y_hat = np.asarray(y_hat, dtype=np.float64).ravel()
    bar = np.asarray(bar, dtype=np.float64).ravel()
    obs = spearman_rho(y_hat, bar)
    if y_hat.size < 2:
        return obs, 1.0
    rng = np.random.default_rng(seed)
    null_rhos = np.empty(n_perm, dtype=np.float64)
    for i in range(n_perm):
        null_rhos[i] = spearman_rho(rng.permutation(y_hat), bar)
    # ponytail: two-sided vs null; ceiling at 1/n_perm
    p = float(np.mean(np.abs(null_rhos) >= abs(obs)))
    return obs, max(p, 1.0 / n_perm)


def _mask_spearman(
    y_hat: np.ndarray, bar: np.ndarray, mask: np.ndarray
) -> tuple[float, int]:
    mask = np.asarray(mask, dtype=bool).ravel()
    y = y_hat[mask]
    b = bar[mask]
    finite = np.isfinite(y) & np.isfinite(b)
    y, b = y[finite], b[finite]
    n = int(y.size)
    if n < 2:
        return 0.0, n
    return spearman_rho(y, b), n


def fit_linear_calibration(
    y_hat: np.ndarray, score_review: np.ndarray, warm_mask: np.ndarray
) -> tuple[float, float]:
    y_hat = np.asarray(y_hat, dtype=np.float64).ravel()
    score_review = np.asarray(score_review, dtype=np.float64).ravel()
    warm_mask = np.asarray(warm_mask, dtype=bool).ravel()
    obs = score_review[warm_mask]
    pred = y_hat[warm_mask]
    finite = np.isfinite(obs) & np.isfinite(pred)
    obs = obs[finite]
    pred = pred[finite]
    if obs.size < 2:
        return 0.0, float(obs.mean()) if obs.size else 0.0
    slope, intercept = np.polyfit(pred, obs, 1)
    return float(slope), float(intercept)


def apply_linear_calibration(
    y_hat: np.ndarray, slope: float, intercept: float
) -> np.ndarray:
    y_hat = np.asarray(y_hat, dtype=np.float64).ravel()
    return slope * y_hat + intercept


def _regression_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    err = y_true - y_pred
    mae = float(np.mean(np.abs(err)))
    rmse = float(np.sqrt(np.mean(err**2)))
    ss_res = float(np.sum(err**2))
    ss_tot = float(np.sum((y_true - y_true.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0.0 else 0.0
    return {"mae": mae, "rmse": rmse, "r2": r2}


def warm_obs_pred_metrics(
    y_hat: np.ndarray, score_review: np.ndarray, warm_mask: np.ndarray
) -> dict[str, float]:
    from scipy.stats import pearsonr

    y_hat = np.asarray(y_hat, dtype=np.float64).ravel()
    score_review = np.asarray(score_review, dtype=np.float64).ravel()
    warm_mask = np.asarray(warm_mask, dtype=bool).ravel()
    obs = score_review[warm_mask]
    pred = y_hat[warm_mask]
    finite = np.isfinite(obs) & np.isfinite(pred)
    obs = obs[finite]
    pred = pred[finite]
    if obs.size == 0:
        return {}

    raw = _regression_metrics(obs, pred)
    slope, intercept = fit_linear_calibration(y_hat, score_review, warm_mask)
    scaled = apply_linear_calibration(pred, slope, intercept)
    linear = _regression_metrics(obs, scaled)
    pearson_raw = float(pearsonr(obs, pred)[0]) if obs.size >= 2 else 0.0

    return {
        "warm_mae_raw": raw["mae"],
        "warm_rmse_raw": raw["rmse"],
        "warm_mae_linear": linear["mae"],
        "warm_rmse_linear": linear["rmse"],
        "warm_r2_linear": linear["r2"],
        "warm_pearson_raw": pearson_raw,
        "warm_spearman_raw": spearman_rho(obs, pred),
        "warm_spearman_linear": spearman_rho(obs, scaled),
        "linear_slope": slope,
        "linear_intercept": intercept,
        "warm_top50_in_pred_top100": _top_k_subset_overlap(
            obs, pred, k_obs=50, k_pred=100
        ),
    }


def _top_k_subset_overlap(
    obs: np.ndarray, pred: np.ndarray, *, k_obs: int, k_pred: int
) -> float:
    k_obs = min(k_obs, obs.size)
    k_pred = min(k_pred, pred.size)
    if k_obs == 0:
        return 0.0
    top_obs = set(np.argsort(-obs, kind="stable")[:k_obs].tolist())
    top_pred = set(np.argsort(-pred, kind="stable")[:k_pred].tolist())
    return len(top_obs & top_pred) / k_obs


def top_k_overlap(scores_a: np.ndarray, scores_b: np.ndarray, k: int = 100) -> float:
    a = np.asarray(scores_a, dtype=np.float64).ravel()
    b = np.asarray(scores_b, dtype=np.float64).ravel()
    k = min(k, a.size, b.size)
    if k == 0:
        return 0.0
    top_a = set(np.argsort(-a, kind="stable")[:k].tolist())
    top_b = set(np.argsort(-b, kind="stable")[:k].tolist())
    return len(top_a & top_b) / k


def aggregate_l1_multi_seed(seed_rows: list[dict]) -> dict:
    """seed_rows: each has l1_spearman_model, l1_spearman_pop (informative, vs bar)."""
    wins = sum(
        1
        for r in seed_rows
        if r.get("l1_spearman_model", 0.0) > r.get("l1_spearman_pop", 0.0)
    )
    n = len(seed_rows)
    return {
        "l1_pop_wins": wins,
        "l1_pop_seeds": n,
        "l1_pass": wins >= L1_POP_WINS_REQUIRED if n >= L1_POP_SEEDS else False,
    }


def evaluate_track_b(
    y_hat: np.ndarray,
    score_review: np.ndarray,
    warm_mask: np.ndarray,
    train_item_signal: np.ndarray | None = None,
    *,
    ndcg_k: int = 50,
    spearman_threshold: float = COHEN_MEDIUM,
) -> dict[str, float | bool | int]:
    """Legacy B0~B3 fields; prefer evaluate_track_b_v2."""
    v2 = evaluate_track_b_v2(
        y_hat,
        score_review,
        warm_mask,
        train_item_signal=train_item_signal,
        ndcg_k=ndcg_k,
        spearman_threshold=spearman_threshold,
    )
    return {
        "coverage": v2["coverage"],
        "score_std": v2["score_std"],
        "b0_pass": v2["l0_pass"],
        "warm_n": v2["warm_n"],
        "cold_n": v2["cold_n"],
        "warm_ndcg50_yhat": v2["warm_ndcg50_yhat"],
        "warm_ndcg50_review": v2["warm_ndcg50_review"],
        "warm_spearman_review": v2["l4_spearman_all_warm"],
        "b2_pass": v2["l2_pass"],
        "warm_spearman_train": v2["l3_spearman_train"],
        "b3_pass": v2["l3_pass"],
        "warm_top100_overlap": v2["warm_top100_overlap"],
    }


def evaluate_track_b_v2(
    y_hat: np.ndarray,
    score_review: np.ndarray,
    warm_mask: np.ndarray,
    train_item_signal: np.ndarray | None = None,
    *,
    export_df: pd.DataFrame | None = None,
    popularity_scores: np.ndarray | None = None,
    cold_mask: np.ndarray | None = None,
    ndcg_k: int = 50,
    spearman_threshold: float = COHEN_MEDIUM,
    null_seed: int = 42,
) -> dict[str, float | bool | int]:
    y_hat = np.asarray(y_hat, dtype=np.float64).ravel()
    score_review = np.asarray(score_review, dtype=np.float64).ravel()
    warm_mask = np.asarray(warm_mask, dtype=bool).ravel()
    n_all = y_hat.size

    finite = np.isfinite(y_hat)
    coverage = float(finite.sum() / n_all) if n_all else 0.0
    score_std = float(np.std(y_hat[finite])) if finite.any() else 0.0
    l0_pass = coverage == 1.0 and score_std > 1e-6

    warm_n = int(warm_mask.sum())
    cold_n = int((~warm_mask).sum()) if cold_mask is None else int(np.asarray(cold_mask).sum())

    warm_y = y_hat[warm_mask]
    warm_review = score_review[warm_mask]
    warm_finite = np.isfinite(warm_review)
    warm_y_f = warm_y[warm_finite]
    warm_review_f = warm_review[warm_finite]

    ndcg_yhat = ndcg_at_k(warm_y_f, warm_review_f, k=ndcg_k) if warm_y_f.size else 0.0
    ndcg_review = (
        ndcg_at_k(warm_review_f, warm_review_f, k=ndcg_k) if warm_review_f.size else 0.0
    )
    l4_rho, _ = _mask_spearman(y_hat, score_review, warm_mask)
    top100 = top_k_overlap(warm_y_f, warm_review_f, k=100) if warm_y_f.size else 0.0

    # legacy all-warm (exp18 contrast; not Go)
    null_p_all = 1.0
    if warm_y_f.size >= 2:
        _, null_p_all = null_spearman_pvalue(warm_y_f, warm_review_f, seed=null_seed)

    pop = (
        np.asarray(popularity_scores, dtype=np.float64).ravel()
        if popularity_scores is not None
        else None
    )
    # pop vs bar (same axis as model); not Spearman(y_hat, pop)
    pop_rho_all, _ = (
        _mask_spearman(pop, score_review, warm_mask) if pop is not None else (0.0, 0)
    )

    subset_rhos: dict[str, float] = {}
    subset_ns: dict[str, int] = {}
    informative_mask = warm_mask
    if export_df is not None:
        subsets = build_warm_subsets(export_df, warm_mask)
        informative_mask = subsets["informative"]
        for name, mask in subsets.items():
            if name == "warm":
                continue
            rho, n = _mask_spearman(y_hat, score_review, mask)
            subset_rhos[f"l2_spearman_{name}"] = rho
            subset_ns[f"l2_n_{name}"] = n

    l2_rho = subset_rhos.get("l2_spearman_informative", 0.0)
    l2_pass = l2_rho >= spearman_threshold

    # L1 Go: informative, Spearman(*, bar)
    rho_model, n_inf = _mask_spearman(y_hat, score_review, informative_mask)
    rho_pop, _ = (
        _mask_spearman(pop, score_review, informative_mask) if pop is not None else (0.0, 0)
    )
    null_p = 1.0
    if n_inf >= 2:
        inf_y = y_hat[informative_mask]
        inf_bar = score_review[informative_mask]
        finite_inf = np.isfinite(inf_y) & np.isfinite(inf_bar)
        if finite_inf.sum() >= 2:
            rho_model, null_p = null_spearman_pvalue(
                inf_y[finite_inf], inf_bar[finite_inf], seed=null_seed
            )

    l1_single_pass = (
        rho_model > COHEN_SMALL and null_p < 0.05 and rho_model > rho_pop
    )

    # diagnostic Top-K on informative (not Go)
    top10_model = 0.0
    top20_model = 0.0
    top10_pop = 0.0
    top20_pop = 0.0
    if n_inf >= 2:
        inf_y = y_hat[informative_mask]
        inf_bar = score_review[informative_mask]
        finite_inf = np.isfinite(inf_y) & np.isfinite(inf_bar)
        iy, ib = inf_y[finite_inf], inf_bar[finite_inf]
        if iy.size >= 2:
            top10_model = _top_k_subset_overlap(ib, iy, k_obs=10, k_pred=10)
            top20_model = _top_k_subset_overlap(ib, iy, k_obs=20, k_pred=20)
            if pop is not None:
                ip = pop[informative_mask][finite_inf]
                top10_pop = _top_k_subset_overlap(ib, ip, k_obs=10, k_pred=10)
                top20_pop = _top_k_subset_overlap(ib, ip, k_obs=20, k_pred=20)

    l3_rho = 0.0
    l3_pass = False
    if train_item_signal is not None:
        signal = np.asarray(train_item_signal, dtype=np.float64).ravel()[warm_mask][warm_finite]
        if signal.size >= 2:
            l3_rho = spearman_rho(warm_y_f, signal)
            l3_pass = l3_rho >= spearman_threshold

    l5_rho = 0.0
    cold_std = 0.0
    if cold_mask is not None and pop is not None:
        cold_mask = np.asarray(cold_mask, dtype=bool).ravel()
        cold_y = y_hat[cold_mask]
        cold_pop = pop[cold_mask]
        finite_c = np.isfinite(cold_y) & np.isfinite(cold_pop)
        if finite_c.sum() >= 2:
            l5_rho = spearman_rho(cold_y[finite_c], cold_pop[finite_c])
        if cold_y.size:
            cold_std = float(np.std(cold_y[np.isfinite(cold_y)]))

    return {
        "metrics_version": "L0-L5",
        "coverage": coverage,
        "score_std": score_std,
        "l0_pass": l0_pass,
        "warm_n": warm_n,
        "cold_n": cold_n,
        "warm_ndcg50_yhat": ndcg_yhat,
        "warm_ndcg50_review": ndcg_review,
        "l4_spearman_all_warm": l4_rho,
        "l4_pass": l4_rho >= spearman_threshold,
        "l4_dataset_exception": True,
        "warm_top100_overlap": top100,
        "warm_spearman_review": l4_rho,
        # L1 Go (informative, vs bar)
        "l1_spearman_model": rho_model,
        "l1_spearman_pop": rho_pop,
        "null_spearman_p": null_p,
        "l1_n_informative": n_inf,
        "l1_single_pass": l1_single_pass,
        "l1_pass": False,
        # legacy all-warm contrast (exp18; not Go)
        "l1_legacy_spearman_model_all": l4_rho,
        "l1_legacy_spearman_pop_all": pop_rho_all,
        "l1_legacy_null_p_all": null_p_all,
        "warm_spearman_popularity": rho_pop,
        "l2_spearman_informative": l2_rho,
        "l2_pass": l2_pass,
        "l2_spearman_threshold": spearman_threshold,
        "l1_top10_overlap_model": top10_model,
        "l1_top20_overlap_model": top20_model,
        "l1_top10_overlap_pop": top10_pop,
        "l1_top20_overlap_pop": top20_pop,
        **subset_rhos,
        **subset_ns,
        "l3_spearman_train": l3_rho,
        "l3_pass": l3_pass,
        "l5_spearman_cold_popularity": l5_rho,
        "cold_score_std": cold_std,
        "b0_pass": l0_pass,
        "b2_pass": l2_pass,
        "b3_pass": l3_pass,
        "warm_spearman_train": l3_rho,
    }


def evaluate_export(
    export_df: pd.DataFrame,
    warm_item_ids: set[str],
    train_matrix,
    *,
    target_mode: str,
    catalog_user_id: str,
    recipe_df: pd.DataFrame | None = None,
    seed: int = 42,
) -> tuple[dict, pd.DataFrame]:
    warm_mask = export_df["recipe_id"].isin(warm_item_ids).to_numpy()
    cold_mask = ~warm_mask
    score_review = export_df["review_rank_score"].to_numpy(dtype=float)
    y_hat = export_df["y_hat"].to_numpy(dtype=float)

    lin_slope, lin_intercept = fit_linear_calibration(y_hat, score_review, warm_mask)
    export_df = export_df.copy()
    export_df["y_hat_linear"] = apply_linear_calibration(y_hat, lin_slope, lin_intercept)

    train_item_signal = np.asarray(train_matrix.sum(axis=0)).ravel().astype(float)

    pop_scores = None
    if recipe_df is not None:
        pop_series = popularity_baseline_scores(recipe_df)
        pop_scores = export_df["recipe_id"].astype(str).map(pop_series).to_numpy(dtype=float)

    track_b_eval = evaluate_track_b_v2(
        y_hat,
        score_review,
        warm_mask,
        train_item_signal=train_item_signal,
        export_df=export_df,
        popularity_scores=pop_scores,
        cold_mask=cold_mask,
        null_seed=seed,
    )
    track_b_eval.update(warm_obs_pred_metrics(y_hat, score_review, warm_mask))
    track_b_eval["target"] = "review_only"
    track_b_eval["y_train"] = target_mode
    track_b_eval["linear_formula"] = (
        f"review_rank_score ~= {lin_slope:.6f} * y_hat + {lin_intercept:.6f} (warm fit)"
    )
    track_b_eval["catalog_user"] = catalog_user_id
    track_b_eval["export_csv"] = "outputs/recipe_lightfm.csv"
    return track_b_eval, export_df


def build_experiment_report(
    cfg,
    track_b_eval: dict,
    *,
    interactions,
    train,
    item_features,
    all_feature_names: set,
    warm_item_ids: set,
    cold_item_ids: list,
    log_numeric_columns: list[str],
) -> dict:
    go_single = (
        track_b_eval["l0_pass"]
        and track_b_eval["l1_single_pass"]
        and track_b_eval["l2_pass"]
    )
    return {
        "experiment": "19_l1_eval_refine",
        "metrics_version": "L0-L5",
        "data_files": {name: str(path) for name, path in cfg.data_files.items()},
        "mode": cfg.model_mode,
        "target_mode": cfg.target_mode,
        "star_weight": cfg.star_weight,
        "sentiment_weight": cfg.sentiment_weight,
        "excluded_recipe_columns": cfg.excluded_recipe_columns,
        "seed": cfg.seed,
        "epochs": cfg.epochs,
        "loss": "warp",
        "train": "full_interactions",
        "log_numeric_columns": log_numeric_columns,
        "matrix": {
            "num_users": int(interactions.shape[0]),
            "num_items": int(interactions.shape[1]),
            "nnz": int(interactions.nnz),
            "train_nnz": int(train.nnz),
            "item_feature_nnz": int(item_features.nnz),
            "unique_features": len(all_feature_names),
            "warm_items": len(warm_item_ids),
            "cold_items": len(cold_item_ids),
        },
        "track_b_eval": track_b_eval,
        "decision": {
            "go": go_single,
            "go_note": (
                "single-seed; L1 final requires 4/5 "
                "l1_spearman_model > l1_spearman_pop on informative"
            ),
            "criterion": (
                "l0_pass and l1_single_pass and l2_pass "
                "(informative: rho_model>0.10, null p<0.05, rho_model>rho_pop; "
                "L2 Spearman >= 0.30)"
            ),
            "l0_pass": track_b_eval["l0_pass"],
            "l1_single_pass": track_b_eval["l1_single_pass"],
            "l1_pass": track_b_eval.get("l1_pass", False),
            "l2_pass": track_b_eval["l2_pass"],
            "l3_pass": track_b_eval["l3_pass"],
            "l4_pass": track_b_eval["l4_pass"],
            "l4_dataset_exception": track_b_eval["l4_dataset_exception"],
            "b0_pass": track_b_eval["l0_pass"],
            "b2_pass": track_b_eval["l2_pass"],
            "b3_pass": track_b_eval["l3_pass"],
        },
    }


if __name__ == "__main__":
    rng = np.random.default_rng(0)
    n = 200
    relevance = rng.random(n)
    scores = relevance + rng.normal(0, 0.1, n)
    warm = np.zeros(n, dtype=bool)
    warm[:80] = True
    # force some informative rows (star_norm < 1)
    star = np.ones(n)
    star[:40] = rng.uniform(0.0, 0.99, 40)

    toy_export = pd.DataFrame(
        {
            "star_norm_avg": star,
            "positive_avg": 0.5,
            "negative_avg": 0.2,
        }
    )
    pop = relevance + rng.normal(0, 0.2, n)
    m = evaluate_track_b_v2(
        scores,
        relevance,
        warm,
        train_item_signal=relevance * 0.9,
        export_df=toy_export,
        popularity_scores=pop,
    )
    assert m["coverage"] == 1.0
    assert m["l0_pass"]
    assert "l1_spearman_model" in m and "l1_spearman_pop" in m
    assert "l1_legacy_spearman_pop_all" in m
    cmp_m = warm_obs_pred_metrics(scores, relevance, warm)
    assert cmp_m["warm_r2_linear"] >= 0.0
    agg = aggregate_l1_multi_seed(
        [{"l1_spearman_model": 0.2, "l1_spearman_pop": 0.1}] * 5
    )
    assert agg["l1_pass"]
    print(
        "evaluation ok",
        m["l1_single_pass"],
        m["l2_pass"],
        m["l3_pass"],
        cmp_m["warm_mae_linear"],
    )
