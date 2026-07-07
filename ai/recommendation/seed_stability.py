"""Holdout 지표 random_state 안정성 — 42 baseline vs 다중 시드."""

from __future__ import annotations

import json
import pathlib
import statistics
import sys
from datetime import datetime, timezone
from typing import Any

import pandas as pd
from sklearn.model_selection import train_test_split

if __name__ == "__main__" and __package__ is None:
    _root = pathlib.Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(_root))

from ai.recommendation import data_loader, evaluator, model
from ai.recommendation.config import (
    ARTIFACTS_DIR,
    MODEL_NAME,
    MODEL_VERSION,
    RANDOM_STATE,
    TARGET_COL,
    TEST_SIZE,
    feature_columns,
)
from ai.recommendation.utils import reset_seeds

REPORT_PATH = ARTIFACTS_DIR / "seed_stability_report.json"
EVAL_PATH = ARTIFACTS_DIR / "evaluation_report.json"
BASELINE_SEED = 42
OTHER_SEEDS = (0, 1, 7, 13, 99, 123, 256, 512, 999)
ALL_SEEDS = (BASELINE_SEED, *OTHER_SEEDS)
_SUMMARY_METRICS = ("Spearman", "Hit@10", "Hit@20", "Hit@50", "RMSE", "MAE", "R2")
_SELF_CHECK_EPS = 1e-3


def holdout_for_seed(seed: int) -> dict[str, Any]:
    merged = data_loader.load_and_merge()
    reset_seeds(seed)
    labeled, _ = data_loader.split_labeled_unlabeled(merged)
    train_df, test_df = train_test_split(
        labeled,
        test_size=TEST_SIZE,
        random_state=seed,
    )
    pipeline = model.build_pipeline(MODEL_NAME, random_state=seed)
    model.fit_pipeline(pipeline, train_df, train_df[TARGET_COL])
    y_pred = model.predict(pipeline, test_df)
    report = evaluator.evaluate(
        test_df[TARGET_COL],
        y_pred,
        train_row_count=len(train_df),
        test_row_count=len(test_df),
        model_type=MODEL_NAME,
        feature_columns_override=feature_columns(),
    )
    report["random_state"] = seed
    return report


def _metric_values(reports: list[dict[str, Any]], key: str) -> list[float]:
    out: list[float] = []
    for row in reports:
        value = row.get(key)
        if value is not None:
            out.append(float(value))
    return out


def _summarize_metric(
    baseline: float | None,
    others: list[float],
) -> dict[str, Any]:
    if not others:
        return {
            "others_mean": None,
            "others_min": None,
            "others_max": None,
            "others_std": None,
            "delta_baseline_vs_mean": None,
            "delta_baseline_vs_min": None,
        }
    mean = statistics.mean(others)
    return {
        "others_mean": mean,
        "others_min": min(others),
        "others_max": max(others),
        "others_std": statistics.pstdev(others) if len(others) > 1 else 0.0,
        "delta_baseline_vs_mean": None if baseline is None else float(baseline - mean),
        "delta_baseline_vs_min": None if baseline is None else float(baseline - min(others)),
    }


def _percentile_baseline(baseline: float, all_values: list[float]) -> float | None:
    if not all_values:
        return None
    below = sum(1 for v in all_values if v < baseline)
    equal = sum(1 for v in all_values if v == baseline)
    # ponytail: tie-aware rank — midpoint of equal bucket
    return float((below + equal / 2) / len(all_values) * 100)


def build_report(seeds: tuple[int, ...] = ALL_SEEDS) -> dict[str, Any]:
    per_seed: list[dict[str, Any]] = []
    for seed in seeds:
        per_seed.append(holdout_for_seed(seed))

    baseline_row = next(r for r in per_seed if r["random_state"] == BASELINE_SEED)
    others_rows = [r for r in per_seed if r["random_state"] != BASELINE_SEED]

    summary_metrics: dict[str, Any] = {}
    for key in _SUMMARY_METRICS:
        baseline_val = baseline_row.get(key)
        baseline_f = float(baseline_val) if baseline_val is not None else None
        others_vals = _metric_values(others_rows, key)
        summary_metrics[key] = _summarize_metric(baseline_f, others_vals)

    all_spearman = _metric_values(per_seed, "Spearman")
    baseline_sp = baseline_row.get("Spearman")
    percentile_42 = None
    if baseline_sp is not None and all_spearman:
        percentile_42 = _percentile_baseline(float(baseline_sp), all_spearman)

    return {
        "model_version": MODEL_VERSION,
        "model_name": MODEL_NAME,
        "target_column": TARGET_COL,
        "feature_count": len(feature_columns()),
        "feature_columns": feature_columns(),
        "baseline_seed": BASELINE_SEED,
        "comparison_seeds": list(OTHER_SEEDS),
        "seeds": list(seeds),
        "baseline_42": {k: baseline_row.get(k) for k in _SUMMARY_METRICS},
        "summary_vs_others": summary_metrics,
        "percentile_42_spearman": percentile_42,
        "per_seed": per_seed,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def run(seeds: tuple[int, ...] = ALL_SEEDS) -> dict[str, Any]:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    report = build_report(seeds)
    evaluator.save_json(report, REPORT_PATH)
    sp = report["baseline_42"]["Spearman"]
    mean_sp = report["summary_vs_others"]["Spearman"]["others_mean"]
    delta = report["summary_vs_others"]["Spearman"]["delta_baseline_vs_mean"]
    print(f"Saved seed stability -> {REPORT_PATH}")
    print(
        f"baseline seed={BASELINE_SEED} Spearman={sp:.4f}  "
        f"others_mean={mean_sp:.4f}  delta_42_vs_mean={delta:+.4f}  "
        f"percentile_42={report['percentile_42_spearman']:.1f}"
    )
    return report


def run_self_check() -> None:
    row = holdout_for_seed(BASELINE_SEED)
    sp = row.get("Spearman")
    assert sp is not None
    if EVAL_PATH.is_file():
        with open(EVAL_PATH, encoding="utf-8") as f:
            expected = float(json.load(f)["Spearman"])
        assert abs(sp - expected) <= _SELF_CHECK_EPS, f"{sp} vs {expected}"
    assert row["train_row_count"] == 450
    assert row["test_row_count"] == 113


if __name__ == "__main__":
    run_self_check()
    run()
