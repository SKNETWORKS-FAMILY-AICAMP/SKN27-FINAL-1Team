"""Feature ablation — 스크리닝 기반 단계별 holdout 비교."""

from __future__ import annotations

import json
import pathlib
import sys
from datetime import datetime, timezone
from typing import Any

import pandas as pd
from sklearn.model_selection import train_test_split

if __name__ == "__main__" and __package__ is None:
    _root = pathlib.Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(_root))

from ai.recommendation import data_loader, evaluator, feature_screening, model
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

SCREENING_PATH = ARTIFACTS_DIR / "feature_screening_report.json"
ABLATION_PATH = ARTIFACTS_DIR / "feature_ablation_report.json"

# Phase 1: permutation drop 양수·상대 고영향 — Phase 3 제거 금지
_PROTECTED = frozenset({
    "CKG_KND_ACTO_NM",
    "ingredient_count",
    "commonness_mean",
    "CKG_MTRL_ACTO_NM",
    "serving_size",
    "SRAP_CNT_LOG_CENTERED",
    "CKG_MTH_ACTO_NM",
})

# Phase 2: 고상관 쌍에서 제거 (perm drop 낮은 쪽)
_PHASE2_REMOVE = frozenset({
    "unique_ingredient_count",
    "others_count",
    "alias_match_ratio",
})

_SPEARMAN_TIE_EPS = 0.005
_METRIC_KEYS = ("Spearman", "Hit@10", "Hit@20", "RMSE", "MAE", "R2")


def _load_screening() -> dict[str, Any]:
    if not SCREENING_PATH.is_file():
        feature_screening.run()
    with open(SCREENING_PATH, encoding="utf-8") as f:
        return json.load(f)


def _metric(report: dict[str, Any], key: str) -> float | None:
    value = report.get(key)
    if value is None:
        return None
    return float(value)


def _is_better(candidate: dict[str, Any], baseline: dict[str, Any]) -> bool:
    c_sp = _metric(candidate, "Spearman")
    b_sp = _metric(baseline, "Spearman")
    if c_sp is not None and b_sp is not None:
        if c_sp > b_sp + 1e-12:
            return True
        if c_sp < b_sp - 1e-12:
            return False
    elif c_sp is not None and b_sp is None:
        return True
    elif c_sp is None and b_sp is not None:
        return False

    for key in ("Hit@10", "Hit@20"):
        c_hit = _metric(candidate, key)
        b_hit = _metric(baseline, key)
        if c_hit is not None and b_hit is not None:
            if c_hit > b_hit + 1e-12:
                return True
            if c_hit < b_hit - 1e-12:
                return False

    c_sp = _metric(candidate, "Spearman") or 0.0
    b_sp = _metric(baseline, "Spearman") or 0.0
    if abs(c_sp - b_sp) <= _SPEARMAN_TIE_EPS:
        c_rmse = _metric(candidate, "RMSE")
        b_rmse = _metric(baseline, "RMSE")
        if c_rmse is not None and b_rmse is not None and c_rmse < b_rmse - 1e-12:
            return True
    return False


def _phase3_accepts(candidate: dict[str, Any], current: dict[str, Any]) -> bool:
    c_sp = _metric(candidate, "Spearman")
    b_sp = _metric(current, "Spearman")
    if c_sp is not None and b_sp is not None and c_sp > b_sp + 1e-12:
        return True
    c_hit = _metric(candidate, "Hit@10")
    b_hit = _metric(current, "Hit@10")
    if c_hit is not None and b_hit is not None and c_hit > b_hit + 1e-12:
        return True
    return False


def _summary(report: dict[str, Any]) -> dict[str, Any]:
    return {k: report.get(k) for k in _METRIC_KEYS}


def _holdout_eval(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    exclude: frozenset[str],
) -> dict[str, Any]:
    cols = feature_columns(exclude)
    if not cols:
        raise ValueError("holdout_eval: no features left after exclude")
    pipeline = model.build_pipeline(MODEL_NAME, exclude=exclude)
    model.fit_pipeline(pipeline, train_df, train_df[TARGET_COL])
    y_pred = model.predict(pipeline, test_df)
    return evaluator.evaluate(
        test_df[TARGET_COL],
        y_pred,
        train_row_count=len(train_df),
        test_row_count=len(test_df),
        model_type=MODEL_NAME,
        feature_columns_override=cols,
    )


def _step_record(
    *,
    phase: int,
    exclude: frozenset[str],
    removed: list[str],
    report: dict[str, Any],
    reference: dict[str, Any],
    accepted: bool,
    note: str = "",
) -> dict[str, Any]:
    ref_sp = _metric(reference, "Spearman")
    cur_sp = _metric(report, "Spearman")
    delta_sp = None
    if ref_sp is not None and cur_sp is not None:
        delta_sp = float(cur_sp - ref_sp)
    return {
        "phase": phase,
        "exclude": sorted(exclude),
        "removed": removed,
        "feature_count": len(feature_columns(exclude)),
        "accepted": accepted,
        "metrics": _summary(report),
        "delta_spearman": delta_sp,
        "note": note,
    }


def _negative_drop_candidates(screening: dict[str, Any], exclude: frozenset[str]) -> list[str]:
    drops: dict[str, float | None] = screening["permutation_spearman_drop"]
    candidates: list[tuple[float, str]] = []
    for col, drop in drops.items():
        if col in exclude or col in _PROTECTED:
            continue
        if drop is None or drop >= 0:
            continue
        candidates.append((drop, col))
    candidates.sort(key=lambda x: x[0])
    return [col for _, col in candidates]


def _run_phase2(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    baseline_report: dict[str, Any],
    exclude: frozenset[str],
) -> tuple[frozenset[str], dict[str, Any], list[dict[str, Any]]]:
    steps: list[dict[str, Any]] = []
    batch_exclude = exclude | _PHASE2_REMOVE
    batch_report = _holdout_eval(train_df, test_df, batch_exclude)
    accepted = _is_better(batch_report, baseline_report)
    steps.append(
        _step_record(
            phase=2,
            exclude=batch_exclude,
            removed=sorted(_PHASE2_REMOVE),
            report=batch_report,
            reference=baseline_report,
            accepted=accepted,
            note="batch_corr_dedup",
        )
    )
    if accepted:
        return batch_exclude, batch_report, steps

    best_exclude = exclude
    best_report = baseline_report
    for col in sorted(_PHASE2_REMOVE):
        trial_exclude = exclude | frozenset({col})
        trial_report = _holdout_eval(train_df, test_df, trial_exclude)
        step_accepted = _is_better(trial_report, best_report)
        steps.append(
            _step_record(
                phase=2,
                exclude=trial_exclude,
                removed=[col],
                report=trial_report,
                reference=best_report,
                accepted=step_accepted,
                note="fallback_single",
            )
        )
        if step_accepted:
            best_exclude = trial_exclude
            best_report = trial_report

    return best_exclude, best_report, steps


def _run_phase3(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    screening: dict[str, Any],
    start_exclude: frozenset[str],
    start_report: dict[str, Any],
) -> tuple[frozenset[str], dict[str, Any], list[dict[str, Any]]]:
    steps: list[dict[str, Any]] = []
    exclude = start_exclude
    current_report = start_report
    for col in _negative_drop_candidates(screening, exclude):
        trial_exclude = exclude | frozenset({col})
        trial_report = _holdout_eval(train_df, test_df, trial_exclude)
        accepted = _phase3_accepts(trial_report, current_report)
        steps.append(
            _step_record(
                phase=3,
                exclude=trial_exclude,
                removed=[col],
                report=trial_report,
                reference=current_report,
                accepted=accepted,
            )
        )
        if accepted:
            exclude = trial_exclude
            current_report = trial_report
    return exclude, current_report, steps


def run() -> dict[str, Any]:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    screening = _load_screening()
    merged = data_loader.load_and_merge()
    reset_seeds(RANDOM_STATE)
    labeled, _ = data_loader.split_labeled_unlabeled(merged)
    if len(labeled) < 2:
        raise ValueError("At least 2 labeled recipes are required for feature ablation")

    train_df, test_df = train_test_split(
        labeled,
        test_size=TEST_SIZE,
        random_state=RANDOM_STATE,
    )

    baseline_exclude: frozenset[str] = frozenset()
    baseline_report = _holdout_eval(train_df, test_df, baseline_exclude)
    steps: list[dict[str, Any]] = []

    phase2_exclude, phase2_report, phase2_steps = _run_phase2(
        train_df, test_df, baseline_report, baseline_exclude
    )
    steps.extend(phase2_steps)

    phase3_exclude, phase3_report, phase3_steps = _run_phase3(
        train_df, test_df, screening, phase2_exclude, phase2_report
    )
    steps.extend(phase3_steps)

    winner_report = phase3_report
    winner_exclude = phase3_exclude
    if not _is_better(winner_report, baseline_report):
        winner_report = baseline_report
        winner_exclude = baseline_exclude

    all_features = feature_columns()
    report: dict[str, Any] = {
        "model_version": MODEL_VERSION,
        "target_column": TARGET_COL,
        "labeled_count": len(labeled),
        "baseline": {
            "features": all_features,
            "feature_count": len(all_features),
            "metrics": _summary(baseline_report),
        },
        "steps": steps,
        "winner": {
            "features": feature_columns(winner_exclude),
            "feature_count": len(feature_columns(winner_exclude)),
            "exclude": sorted(winner_exclude),
            "removed_from_baseline": sorted(set(all_features) - set(feature_columns(winner_exclude))),
            "metrics": _summary(winner_report),
            "beats_baseline": _is_better(winner_report, baseline_report),
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    evaluator.save_json(report, ABLATION_PATH)
    print(f"Saved feature ablation -> {ABLATION_PATH}")
    w = report["winner"]
    b_sp = report["baseline"]["metrics"]["Spearman"]
    w_sp = w["metrics"]["Spearman"]
    print(
        f"baseline Spearman={b_sp:.4f}  winner Spearman={w_sp:.4f}  "
        f"beats_baseline={w['beats_baseline']}  removed={w['removed_from_baseline']}"
    )
    return report


def _self_check() -> None:
    screening = {
        "permutation_spearman_drop": {
            "cooking_time_min": -0.1,
            "CKG_STA_ACTO_NM": -0.05,
            "CKG_KND_ACTO_NM": 0.06,
        }
    }
    exclude = frozenset({"unique_ingredient_count"})
    candidates = _negative_drop_candidates(screening, exclude)
    assert "CKG_STA_ACTO_NM" in candidates
    assert "CKG_KND_ACTO_NM" not in candidates
    assert candidates[0] == "cooking_time_min"

    better = {"Spearman": 0.2, "Hit@10": 0.1, "RMSE": 1.0}
    worse = {"Spearman": 0.1, "Hit@10": 0.1, "RMSE": 1.0}
    assert _is_better(better, worse)
    assert not _is_better(worse, better)
    tie = {"Spearman": 0.1, "Hit@10": 0.2, "RMSE": 1.0}
    assert _phase3_accepts(tie, worse)


if __name__ == "__main__":
    _self_check()
    run()
