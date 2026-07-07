"""Stratified 5-fold auxiliary validation for the recommendation model."""

from __future__ import annotations

import pathlib
import statistics
import sys
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold

if __name__ == "__main__" and __package__ is None:
    _root = pathlib.Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(_root))

from ai.recommendation import data_loader, evaluator, model
from ai.recommendation.config import (
    ARTIFACTS_DIR,
    HIT_AT_K_VALUES,
    MODEL_NAME,
    MODEL_VERSION,
    RANDOM_STATE,
    TARGET_COL,
    TARGET_FORMULA,
    feature_columns,
)
from ai.recommendation.utils import reset_seeds

N_SPLITS = 5
N_TARGET_BINS = 5
REPORT_PATH = ARTIFACTS_DIR / "stratified_kfold_report.json"
PREDICTIONS_PATH = ARTIFACTS_DIR / "stratified_kfold_predictions.csv"
SUMMARY_METRICS = ("Spearman", "Hit@10", "Hit@20", "Hit@50", "RMSE", "MAE", "R2")


def make_target_bins(
    target: pd.Series,
    *,
    n_bins: int = N_TARGET_BINS,
    n_splits: int = N_SPLITS,
) -> tuple[pd.Series, list[float], dict[int, int]]:
    """Turn a regression target into tie-preserving quantile strata."""
    numeric = pd.to_numeric(target, errors="coerce")
    if numeric.isna().any():
        raise ValueError("Cross-validation target contains missing or invalid values")
    bins, edges = pd.qcut(
        numeric,
        q=n_bins,
        labels=False,
        retbins=True,
        duplicates="drop",
    )
    bins = bins.astype(int)
    counts = {int(k): int(v) for k, v in bins.value_counts().sort_index().items()}
    if len(counts) < 2:
        raise ValueError("Target quantile binning produced fewer than 2 strata")
    too_small = {key: value for key, value in counts.items() if value < n_splits}
    if too_small:
        raise ValueError(
            f"Every target stratum needs at least {n_splits} rows; too small: {too_small}"
        )
    return bins, [float(value) for value in edges], counts


def make_fold_splits(
    labeled_df: pd.DataFrame,
    strata: pd.Series,
    *,
    n_splits: int = N_SPLITS,
    random_state: int = RANDOM_STATE,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Build deterministic folds and validate coverage and Hit@K feasibility."""
    splitter = StratifiedKFold(
        n_splits=n_splits,
        shuffle=True,
        random_state=random_state,
    )
    splits = list(splitter.split(labeled_df, strata))
    validation_positions = np.concatenate([validation for _, validation in splits])
    expected = np.arange(len(labeled_df))
    if not np.array_equal(np.sort(validation_positions), expected):
        raise RuntimeError("Validation folds do not cover every labeled row exactly once")
    max_k = max(HIT_AT_K_VALUES)
    for fold_index, (train_positions, validation_positions) in enumerate(splits, start=1):
        if np.intersect1d(train_positions, validation_positions).size:
            raise RuntimeError(f"Fold {fold_index} has overlapping train/validation rows")
        if len(validation_positions) < max_k:
            raise ValueError(
                f"Fold {fold_index} has {len(validation_positions)} validation rows; "
                f"Hit@{max_k} requires at least {max_k}"
            )
    return splits


def _metric_summary(fold_reports: list[dict[str, Any]], metric: str) -> dict[str, Any]:
    values = [float(report[metric]) for report in fold_reports if report.get(metric) is not None]
    if not values:
        return {"mean": None, "std": None, "min": None, "max": None}
    return {
        "mean": statistics.mean(values),
        "std": statistics.pstdev(values) if len(values) > 1 else 0.0,
        "min": min(values),
        "max": max(values),
    }


def evaluation_report_section(report: dict[str, Any]) -> dict[str, Any]:
    """Return the compact CV mean section embedded in evaluation_report.json."""
    summary = report["summary"]
    return {
        "role": "auxiliary_validation",
        "method": "StratifiedKFold",
        "n_splits": int(report["n_splits"]),
        "random_state": int(report["random_state"]),
        "stratification": report["stratification"],
        "metrics_mean": {
            metric: summary[metric]["mean"] for metric in SUMMARY_METRICS
        },
        "detail_report": REPORT_PATH.name,
        "oof_predictions": PREDICTIONS_PATH.name,
    }


def build_report(labeled_df: pd.DataFrame) -> tuple[dict[str, Any], pd.DataFrame]:
    """Fit five transient models and return report plus OOF predictions."""
    if TARGET_COL not in labeled_df.columns:
        raise ValueError(f"Missing target column: {TARGET_COL}")
    if "RCP_SNO" not in labeled_df.columns:
        raise ValueError("Missing recipe id column: RCP_SNO")
    if labeled_df["RCP_SNO"].duplicated().any():
        raise ValueError("Cross-validation input contains duplicate RCP_SNO values")
    labeled = labeled_df.reset_index(drop=True).copy()
    if len(labeled) < N_SPLITS * max(HIT_AT_K_VALUES):
        raise ValueError(
            f"At least {N_SPLITS * max(HIT_AT_K_VALUES)} labeled rows are required "
            f"for {N_SPLITS}-fold Hit@{max(HIT_AT_K_VALUES)} evaluation"
        )

    strata, edges, bin_counts = make_target_bins(labeled[TARGET_COL])
    splits = make_fold_splits(labeled, strata)
    oof_predictions = np.full(len(labeled), np.nan, dtype=float)
    fold_assignments = np.full(len(labeled), -1, dtype=int)
    fold_reports: list[dict[str, Any]] = []

    for fold_number, (train_positions, validation_positions) in enumerate(splits, start=1):
        reset_seeds(RANDOM_STATE)
        train_df = labeled.iloc[train_positions]
        validation_df = labeled.iloc[validation_positions]
        pipeline = model.build_pipeline(MODEL_NAME, random_state=RANDOM_STATE)
        model.fit_pipeline(pipeline, train_df, train_df[TARGET_COL])
        predictions = np.asarray(model.predict(pipeline, validation_df), dtype=float)
        oof_predictions[validation_positions] = predictions
        fold_assignments[validation_positions] = fold_number

        report = evaluator.evaluate(
            validation_df[TARGET_COL],
            predictions,
            train_row_count=len(train_df),
            test_row_count=len(validation_df),
            model_type=MODEL_NAME,
            feature_columns_override=feature_columns(),
        )
        report["fold"] = fold_number
        report["validation_stratum_counts"] = {
            str(int(key)): int(value)
            for key, value in strata.iloc[validation_positions].value_counts().sort_index().items()
        }
        fold_reports.append(report)

    if np.isnan(oof_predictions).any() or (fold_assignments < 1).any():
        raise RuntimeError("OOF predictions are incomplete")

    oof_report = evaluator.evaluate(
        labeled[TARGET_COL],
        oof_predictions,
        train_row_count=len(labeled),
        test_row_count=len(labeled),
        model_type=f"{MODEL_NAME}_oof_diagnostic",
        feature_columns_override=feature_columns(),
    )
    oof_metrics = {metric: oof_report.get(metric) for metric in SUMMARY_METRICS}
    summary = {metric: _metric_summary(fold_reports, metric) for metric in SUMMARY_METRICS}
    report = {
        "model_version": MODEL_VERSION,
        "model_name": MODEL_NAME,
        "random_state": RANDOM_STATE,
        "n_splits": N_SPLITS,
        "stratification": "target_quantile_bins",
        "requested_target_bins": N_TARGET_BINS,
        "actual_target_bins": len(bin_counts),
        "target_bin_edges": edges,
        "target_bin_counts": {str(key): value for key, value in bin_counts.items()},
        "target_column": TARGET_COL,
        "target_formula": TARGET_FORMULA,
        "feature_columns": feature_columns(),
        "labeled_count": len(labeled),
        "folds": fold_reports,
        "summary": summary,
        "oof_metrics_diagnostic_only": oof_metrics,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    predictions_df = pd.DataFrame(
        {
            "RCP_SNO": labeled["RCP_SNO"].to_numpy(),
            "fold": fold_assignments,
            "target_stratum": strata.to_numpy(dtype=int),
            "y_true": labeled[TARGET_COL].to_numpy(dtype=float),
            "y_pred_oof": oof_predictions,
        }
    )
    return report, predictions_df


def run(labeled_df: pd.DataFrame | None = None) -> dict[str, Any]:
    """Run CV standalone or with an already-loaded labeled DataFrame."""
    if labeled_df is None:
        merged = data_loader.load_and_merge()
        labeled_df, _ = data_loader.split_labeled_unlabeled(merged)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    report, predictions = build_report(labeled_df)
    evaluator.save_json(report, REPORT_PATH)
    predictions.to_csv(PREDICTIONS_PATH, index=False, encoding="utf-8-sig")

    spearman = report["summary"]["Spearman"]
    print(f"Saved stratified 5-fold report -> {REPORT_PATH}")
    print(f"Saved OOF predictions -> {PREDICTIONS_PATH}")
    print(
        "5-Fold Spearman "
        f"mean={spearman['mean']:.4f} std={spearman['std']:.4f} "
        f"min={spearman['min']:.4f}"
    )
    return report


if __name__ == "__main__":
    run()
