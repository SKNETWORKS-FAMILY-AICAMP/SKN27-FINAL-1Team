"""Track B catalog metrics: coverage, NDCG@k, Spearman, B0~B3 gates."""

from __future__ import annotations

import numpy as np
import pandas as pd


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


def evaluate_track_b(
    y_hat: np.ndarray,
    score_review: np.ndarray,
    warm_mask: np.ndarray,
    train_item_signal: np.ndarray | None = None,
    *,
    ndcg_k: int = 50,
    spearman_threshold: float = 0.30,
) -> dict[str, float | bool | int]:
    y_hat = np.asarray(y_hat, dtype=np.float64).ravel()
    score_review = np.asarray(score_review, dtype=np.float64).ravel()
    warm_mask = np.asarray(warm_mask, dtype=bool).ravel()
    n_all = y_hat.size

    finite = np.isfinite(y_hat)
    coverage = float(finite.sum() / n_all) if n_all else 0.0
    score_std = float(np.std(y_hat[finite])) if finite.any() else 0.0
    b0_pass = coverage == 1.0 and score_std > 1e-6

    warm_n = int(warm_mask.sum())
    cold_n = int((~warm_mask).sum())

    warm_y = y_hat[warm_mask]
    warm_review = score_review[warm_mask]
    warm_finite = np.isfinite(warm_review)
    warm_y = warm_y[warm_finite]
    warm_review = warm_review[warm_finite]

    ndcg_yhat = ndcg_at_k(warm_y, warm_review, k=ndcg_k) if warm_y.size else 0.0
    ndcg_review = ndcg_at_k(warm_review, warm_review, k=ndcg_k) if warm_review.size else 0.0
    rho_review = spearman_rho(warm_y, warm_review) if warm_y.size >= 2 else 0.0
    b2_pass = rho_review >= spearman_threshold

    rho_train = 0.0
    b3_pass = False
    if train_item_signal is not None:
        signal = np.asarray(train_item_signal, dtype=np.float64).ravel()[warm_mask][warm_finite]
        if signal.size >= 2:
            rho_train = spearman_rho(warm_y, signal)
            b3_pass = rho_train >= spearman_threshold

    top100 = top_k_overlap(warm_y, warm_review, k=100) if warm_y.size else 0.0

    return {
        "coverage": coverage,
        "score_std": score_std,
        "b0_pass": b0_pass,
        "warm_n": warm_n,
        "cold_n": cold_n,
        "warm_ndcg50_yhat": ndcg_yhat,
        "warm_ndcg50_review": ndcg_review,
        "warm_spearman_review": rho_review,
        "b2_pass": b2_pass,
        "warm_spearman_train": rho_train,
        "b3_pass": b3_pass,
        "warm_top100_overlap": top100,
    }


def evaluate_export(
    export_df: pd.DataFrame,
    warm_item_ids: set[str],
    train_matrix,
    *,
    target_mode: str,
    catalog_user_id: str,
) -> tuple[dict, pd.DataFrame]:
    warm_mask = export_df["recipe_id"].isin(warm_item_ids).to_numpy()
    score_review = export_df["review_rank_score"].to_numpy(dtype=float)
    y_hat = export_df["y_hat"].to_numpy(dtype=float)

    lin_slope, lin_intercept = fit_linear_calibration(y_hat, score_review, warm_mask)
    export_df = export_df.copy()
    export_df["y_hat_linear"] = apply_linear_calibration(y_hat, lin_slope, lin_intercept)

    train_item_signal = np.asarray(train_matrix.sum(axis=0)).ravel().astype(float)
    track_b_eval = evaluate_track_b(
        y_hat,
        score_review,
        warm_mask,
        train_item_signal=train_item_signal,
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
    go_no_go = (
        track_b_eval["b0_pass"]
        and track_b_eval["b2_pass"]
        and track_b_eval["b3_pass"]
    )
    return {
        "experiment": "17_track_b_coldstart",
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
            "go": go_no_go,
            "criterion": "b0_pass and b2_pass and b3_pass (Spearman bar/train >= 0.30)",
            "b0_pass": track_b_eval["b0_pass"],
            "b2_pass": track_b_eval["b2_pass"],
            "b3_pass": track_b_eval["b3_pass"],
        },
    }


if __name__ == "__main__":
    rng = np.random.default_rng(0)
    n = 200
    relevance = rng.random(n)
    scores = relevance + rng.normal(0, 0.1, n)
    warm = np.zeros(n, dtype=bool)
    warm[:80] = True

    m = evaluate_track_b(scores, relevance, warm, train_item_signal=relevance * 0.9)
    assert m["coverage"] == 1.0
    assert m["b0_pass"]
    cmp_m = warm_obs_pred_metrics(scores, relevance, warm)
    assert cmp_m["warm_r2_linear"] >= 0.0
    print("evaluation ok", m["b2_pass"], m["b3_pass"], cmp_m["warm_mae_linear"])
