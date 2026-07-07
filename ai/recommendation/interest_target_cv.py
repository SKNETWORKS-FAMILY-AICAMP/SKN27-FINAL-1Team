"""24->26 조회수 로그 변화 타깃 전용 KFold 진단."""

from __future__ import annotations

import pathlib
import sys
import json
from datetime import datetime, timezone
from statistics import mean, pstdev
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

if __name__ == "__main__" and __package__ is None:
    _root = pathlib.Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(_root))

from ai.recommendation import cross_validation, data_loader, evaluator, model
from ai.recommendation.config import (
    ARTIFACTS_DIR,
    HIT_AT_K_VALUES,
    MODEL_NAME,
    MODEL_VERSION,
    RANDOM_STATE,
    feature_columns,
)
from ai.recommendation.utils import reset_seeds

INTEREST_TARGET_COL = "INTEREST_TARGET_LOG_DELTA_2024_2026"
INTEREST_TARGET_FORMULA = "log1p(INQ_CNT_2026) - log1p(INQ_CNT_2024)"
REPORT_PATH = ARTIFACTS_DIR / "interest_target_kfold_report.json"
PREDICTIONS_PATH = ARTIFACTS_DIR / "interest_target_kfold_predictions.csv"
QUALITY_BASELINE_PATH = ARTIFACTS_DIR / "stratified_kfold_report.json"
SUMMARY_METRICS = ("Spearman", "Hit@10", "Hit@20", "Hit@50", "RMSE", "MAE", "R2")

# ponytail: direct target leakage 가능성이 높은 INQ centered 신호만 최소 제외 비교군
VARIANTS: tuple[tuple[str, frozenset[str]], ...] = (
    ("A_current_features", frozenset()),
    ("B_without_inq_centered", frozenset({"INQ_CNT_LOG_CENTERED"})),
)


def _hit_at_k(y_true: np.ndarray, y_pred: np.ndarray, k: int) -> float | None:
    if len(y_true) < k:
        return None
    true_top = set(np.argsort(-y_true)[:k])
    pred_top = set(np.argsort(-y_pred)[:k])
    return len(true_top & pred_top) / k


def _evaluate_arrays(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float | None]:
    sp = spearmanr(y_true, y_pred).correlation
    report: dict[str, float | None] = {
        "RMSE": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "MAE": float(mean_absolute_error(y_true, y_pred)),
        "R2": float(r2_score(y_true, y_pred)),
        "Spearman": None if sp is None or np.isnan(sp) else float(sp),
    }
    for k in HIT_AT_K_VALUES:
        report[f"Hit@{k}"] = _hit_at_k(y_true, y_pred, k)
    return report


def _summary_from_folds(folds: list[dict[str, Any]]) -> dict[str, dict[str, float | None]]:
    summary: dict[str, dict[str, float | None]] = {}
    for key in SUMMARY_METRICS:
        values = [float(f["metrics"][key]) for f in folds if f["metrics"][key] is not None]
        if not values:
            summary[key] = {"mean": None, "std": None, "min": None, "max": None}
            continue
        summary[key] = {
            "mean": mean(values),
            "std": pstdev(values) if len(values) > 1 else 0.0,
            "min": min(values),
            "max": max(values),
        }
    return summary


def _audit_interest_target(merged: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    out = merged.copy()
    c24 = pd.to_numeric(out["INQ_CNT_2024"], errors="coerce")
    c26 = pd.to_numeric(out["INQ_CNT_2026"], errors="coerce")
    valid = c24.notna() & c26.notna() & (c24 >= 0) & (c26 >= 0)
    out[INTEREST_TARGET_COL] = np.nan
    out.loc[valid, INTEREST_TARGET_COL] = np.log1p(c26[valid]) - np.log1p(c24[valid])
    target = out.loc[valid, INTEREST_TARGET_COL].to_numpy(dtype=float)
    audit = {
        "rows_total": int(len(out)),
        "valid_rows": int(valid.sum()),
        "null_2024": int(c24.isna().sum()),
        "null_2026": int(c26.isna().sum()),
        "negative_2024": int((c24 < 0).sum()),
        "negative_2026": int((c26 < 0).sum()),
        "target_p01": float(np.quantile(target, 0.01)),
        "target_p50": float(np.quantile(target, 0.5)),
        "target_p99": float(np.quantile(target, 0.99)),
        "target_mean": float(target.mean()),
        "target_std": float(target.std(ddof=0)),
    }
    return out.loc[valid].copy(), audit


def _quality_baseline_summary() -> dict[str, Any] | None:
    if not QUALITY_BASELINE_PATH.is_file():
        return None
    with open(QUALITY_BASELINE_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return {
        "source": QUALITY_BASELINE_PATH.name,
        "summary": {
            "Spearman": float(data["summary"]["Spearman"]["mean"]),
            "Hit@10": float(data["summary"]["Hit@10"]["mean"]),
            "Hit@20": float(data["summary"]["Hit@20"]["mean"]),
            "Hit@50": float(data["summary"]["Hit@50"]["mean"]),
            "RMSE": float(data["summary"]["RMSE"]["mean"]),
            "MAE": float(data["summary"]["MAE"]["mean"]),
            "R2": float(data["summary"]["R2"]["mean"]),
        },
    }


def run() -> dict[str, Any]:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    merged = data_loader.load_and_merge()
    labeled, audit = _audit_interest_target(merged)
    if len(labeled) < cross_validation.N_SPLITS * max(HIT_AT_K_VALUES):
        raise ValueError("Not enough rows for 5-fold Hit@50 diagnostics")

    strata, edges, bin_counts = cross_validation.make_target_bins(
        labeled[INTEREST_TARGET_COL]
    )
    splits = cross_validation.make_fold_splits(labeled, strata)

    fold_assignments = np.full(len(labeled), -1, dtype=int)
    for fold_no, (_, valid_idx) in enumerate(splits, start=1):
        fold_assignments[valid_idx] = fold_no

    variant_reports: dict[str, Any] = {}
    predictions_df = pd.DataFrame(
        {
            "RCP_SNO": labeled["RCP_SNO"].to_numpy(),
            "fold": fold_assignments,
            "target_stratum": strata.to_numpy(dtype=int),
            "y_true": labeled[INTEREST_TARGET_COL].to_numpy(dtype=float),
        }
    )

    for name, exclude in VARIANTS:
        oof = np.full(len(labeled), np.nan, dtype=float)
        folds: list[dict[str, Any]] = []
        used_features = feature_columns(exclude)
        for fold_no, (train_idx, valid_idx) in enumerate(splits, start=1):
            reset_seeds(RANDOM_STATE)
            train_df = labeled.iloc[train_idx]
            valid_df = labeled.iloc[valid_idx]
            pipeline = model.build_pipeline(MODEL_NAME, exclude=exclude, random_state=RANDOM_STATE)
            model.fit_pipeline(pipeline, train_df, train_df[INTEREST_TARGET_COL])
            pred = np.asarray(model.predict(pipeline, valid_df), dtype=float)
            oof[valid_idx] = pred
            folds.append(
                {
                    "fold": fold_no,
                    "train_row_count": int(len(train_df)),
                    "valid_row_count": int(len(valid_df)),
                    "metrics": _evaluate_arrays(
                        valid_df[INTEREST_TARGET_COL].to_numpy(dtype=float), pred
                    ),
                }
            )
        if np.isnan(oof).any():
            raise RuntimeError(f"{name}: OOF predictions are incomplete")
        predictions_df[f"y_pred_{name}"] = oof
        variant_reports[name] = {
            "exclude": sorted(exclude),
            "feature_columns": used_features,
            "feature_count": int(len(used_features)),
            "folds": folds,
            "summary": _summary_from_folds(folds),
            "oof_metrics_diagnostic_only": _evaluate_arrays(
                labeled[INTEREST_TARGET_COL].to_numpy(dtype=float), oof
            ),
        }

    report: dict[str, Any] = {
        "model_version": MODEL_VERSION,
        "model_name": MODEL_NAME,
        "random_state": RANDOM_STATE,
        "target_column": INTEREST_TARGET_COL,
        "target_formula": INTEREST_TARGET_FORMULA,
        "rows_used_for_target": int(len(labeled)),
        "data_audit": audit,
        "n_splits": cross_validation.N_SPLITS,
        "stratification": "target_quantile_bins",
        "target_bin_edges": [float(v) for v in edges],
        "target_bin_counts": {str(int(k)): int(v) for k, v in bin_counts.items()},
        "variants": variant_reports,
        "quality_target_reference": _quality_baseline_summary(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "notes": "diagnostic only; do not apply to production scoring",
    }
    evaluator.save_json(report, REPORT_PATH)
    predictions_df.to_csv(PREDICTIONS_PATH, index=False, encoding="utf-8-sig")
    print(f"Saved interest-target report -> {REPORT_PATH}")
    print(f"Saved interest-target OOF -> {PREDICTIONS_PATH}")
    for name in variant_reports:
        sp = variant_reports[name]["summary"]["Spearman"]["mean"]
        print(f"{name} 5-Fold Spearman mean={sp:.4f}")
    return report


if __name__ == "__main__":
    run()
