from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ai.recommendation import cross_validation


def test_target_bins_and_fold_splits_are_deterministic_and_complete() -> None:
    rows = 250
    frame = pd.DataFrame(
        {
            "RCP_SNO": np.arange(rows),
            "REVIEW_RANK_SCORE": np.linspace(-1.0, 2.0, rows),
        }
    )
    strata, edges, counts = cross_validation.make_target_bins(
        frame["REVIEW_RANK_SCORE"]
    )
    first = cross_validation.make_fold_splits(frame, strata)
    second = cross_validation.make_fold_splits(frame, strata)

    assert len(edges) == 6
    assert len(counts) == 5
    assert all(count == 50 for count in counts.values())
    assert all(np.array_equal(a[0], b[0]) for a, b in zip(first, second))
    assert all(np.array_equal(a[1], b[1]) for a, b in zip(first, second))
    validation = np.concatenate([positions for _, positions in first])
    np.testing.assert_array_equal(np.sort(validation), np.arange(rows))
    for train_positions, validation_positions in first:
        assert len(train_positions) == 200
        assert len(validation_positions) == 50
        assert np.intersect1d(train_positions, validation_positions).size == 0


def test_target_bins_reject_stratum_smaller_than_fold_count() -> None:
    target = pd.Series(np.arange(9, dtype=float))
    with pytest.raises(ValueError, match="at least 5 rows"):
        cross_validation.make_target_bins(target, n_bins=2, n_splits=5)


def test_fold_splits_reject_validation_too_small_for_hit50() -> None:
    frame = pd.DataFrame({"RCP_SNO": np.arange(100)})
    strata = pd.Series(np.repeat(np.arange(5), 20))
    with pytest.raises(ValueError, match="Hit@50"):
        cross_validation.make_fold_splits(frame, strata)


def test_metric_summary_uses_population_standard_deviation() -> None:
    reports = [{"Spearman": 0.1}, {"Spearman": 0.2}, {"Spearman": 0.3}]
    summary = cross_validation._metric_summary(reports, "Spearman")

    assert summary["mean"] == pytest.approx(0.2)
    assert summary["std"] == pytest.approx(np.std([0.1, 0.2, 0.3], ddof=0))
    assert summary["min"] == pytest.approx(0.1)
    assert summary["max"] == pytest.approx(0.3)


def test_evaluation_report_section_contains_cv_means() -> None:
    report = {
        "n_splits": 5,
        "random_state": 42,
        "stratification": "target_quantile_bins",
        "summary": {
            metric: {"mean": float(index) / 10}
            for index, metric in enumerate(cross_validation.SUMMARY_METRICS)
        },
    }

    section = cross_validation.evaluation_report_section(report)

    assert section["role"] == "auxiliary_validation"
    assert section["method"] == "StratifiedKFold"
    assert section["n_splits"] == 5
    assert section["random_state"] == 42
    assert set(section["metrics_mean"]) == set(cross_validation.SUMMARY_METRICS)
    assert section["detail_report"] == "stratified_kfold_report.json"
