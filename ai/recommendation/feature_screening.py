"""Feature 영향도 스크리닝 — 단변량·중복·permutation Spearman drop."""

from __future__ import annotations

import pathlib
import sys
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

if __name__ == "__main__" and __package__ is None:
    _root = pathlib.Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(_root))

from ai.recommendation import data_loader, evaluator, features, model
from ai.recommendation.config import (
    ARTIFACTS_DIR,
    INGREDIENT_FEATURES,
    MODEL_NAME,
    MODEL_VERSION,
    NUMERIC_FEATURES,
    RANDOM_STATE,
    TARGET_COL,
    TARGET_FORMULA,
    TEST_SIZE,
    feature_columns,
)
from ai.recommendation.utils import reset_seeds

CORRELATION_THRESHOLD = 0.7
_NUMERIC_SCREEN_COLS = NUMERIC_FEATURES + INGREDIENT_FEATURES

# ponytail: logical feature → test_df raw column to shuffle (derived cols rebuilt in pipeline)
_PERMUTE_SOURCE: dict[str, str] = {
    "serving_size": "CKG_INBUN_NM",
    "cooking_time_min": "CKG_TIME_NM",
    "ingredient_count": "ingredients_normalized",
    "unique_ingredient_count": "ingredients_normalized",
    "others_count": "others_count",
    "others_ratio": "others_count",
    "alias_match_ratio": "others_count",
    "commonness_mean": "ingredients_normalized",
    "commonness_min": "ingredients_normalized",
    "commonness_max": "ingredients_normalized",
}


def _permute_source_column(logical: str) -> str:
    return _PERMUTE_SOURCE.get(logical, logical)


def _spearman_or_none(x: np.ndarray, y: np.ndarray) -> float | None:
    corr = spearmanr(x, y).correlation
    if corr is None or np.isnan(corr):
        return None
    return float(corr)


def _feature_values(featured: pd.DataFrame, col: str) -> np.ndarray:
    series = featured[col]
    if col in featured.columns and featured[col].dtype == object:
        codes, _ = pd.factorize(series.astype(str))
        return codes.astype(float)
    return pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)


def univariate_spearman(
    labeled_df: pd.DataFrame,
    train_df: pd.DataFrame,
    *,
    target_col: str = TARGET_COL,
) -> dict[str, float | None]:
    builder = features.RecommendationFeatureBuilder().fit(train_df)
    featured = builder.transform(labeled_df)
    target = labeled_df[target_col].to_numpy(dtype=float)
    return {
        col: _spearman_or_none(_feature_values(featured, col), target)
        for col in feature_columns()
    }


def high_correlation_pairs(
    labeled_df: pd.DataFrame,
    train_df: pd.DataFrame,
    *,
    threshold: float = CORRELATION_THRESHOLD,
) -> list[dict[str, Any]]:
    builder = features.RecommendationFeatureBuilder().fit(train_df)
    featured = builder.transform(labeled_df)
    numeric = featured[_NUMERIC_SCREEN_COLS].apply(pd.to_numeric, errors="coerce")
    pairs: list[dict[str, Any]] = []
    cols = list(_NUMERIC_SCREEN_COLS)
    for i, left in enumerate(cols):
        for right in cols[i + 1 :]:
            corr = numeric[left].corr(numeric[right])
            if corr is None or np.isnan(corr) or abs(corr) <= threshold:
                continue
            pairs.append({"a": left, "b": right, "pearson": float(corr)})
    return pairs


def permutation_spearman_drop(
    pipeline: Pipeline,
    test_df: pd.DataFrame,
    y_test: pd.Series,
    *,
    random_state: int = RANDOM_STATE,
) -> tuple[float | None, dict[str, float | None]]:
    y = y_test.to_numpy(dtype=float)
    baseline_pred = np.asarray(model.predict(pipeline, test_df), dtype=float)
    baseline = _spearman_or_none(y, baseline_pred)
    drops: dict[str, float | None] = {}
    for index, col in enumerate(feature_columns()):
        source = _permute_source_column(col)
        if source not in test_df.columns:
            drops[col] = None
            continue
        permuted = test_df.copy()
        rng = np.random.default_rng(random_state + index)
        permuted[source] = rng.permutation(permuted[source].to_numpy())
        pred = np.asarray(model.predict(pipeline, permuted), dtype=float)
        permuted_sp = _spearman_or_none(y, pred)
        if baseline is None or permuted_sp is None:
            drops[col] = None
        else:
            drops[col] = float(baseline - permuted_sp)
    return baseline, drops


def build_screening_report(
    labeled_df: pd.DataFrame,
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    pipeline: Pipeline,
    y_test: pd.Series,
    *,
    correlation_threshold: float = CORRELATION_THRESHOLD,
) -> dict[str, Any]:
    baseline, perm_drops = permutation_spearman_drop(pipeline, test_df, y_test)
    return {
        "model_version": MODEL_VERSION,
        "target_column": TARGET_COL,
        "target_formula": TARGET_FORMULA,
        "labeled_count": len(labeled_df),
        "train_row_count": len(train_df),
        "test_row_count": len(test_df),
        "holdout_spearman_baseline": baseline,
        "correlation_threshold": correlation_threshold,
        "univariate_spearman": univariate_spearman(labeled_df, train_df),
        "high_correlation_pairs": high_correlation_pairs(
            labeled_df, train_df, threshold=correlation_threshold
        ),
        "permutation_spearman_drop": perm_drops,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def run() -> dict[str, Any]:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    merged = data_loader.load_and_merge()
    reset_seeds(RANDOM_STATE)
    labeled, _ = data_loader.split_labeled_unlabeled(merged)
    if len(labeled) < 2:
        raise ValueError("At least 2 labeled recipes are required for feature screening")

    train_df, test_df = train_test_split(
        labeled,
        test_size=TEST_SIZE,
        random_state=RANDOM_STATE,
    )
    pipeline = model.build_pipeline(MODEL_NAME)
    model.fit_pipeline(pipeline, train_df, train_df[TARGET_COL])

    report = build_screening_report(
        labeled,
        train_df,
        test_df,
        pipeline,
        test_df[TARGET_COL],
    )
    out_path = ARTIFACTS_DIR / "feature_screening_report.json"
    evaluator.save_json(report, out_path)
    print(f"Saved feature screening -> {out_path}")
    baseline = report["holdout_spearman_baseline"]
    baseline_text = f"{baseline:.4f}" if baseline is not None else "N/A"
    print(f"holdout Spearman={baseline_text}  high_corr_pairs={len(report['high_correlation_pairs'])}")
    return report


def _self_check() -> None:
    labeled = pd.DataFrame(
        {
            TARGET_COL: [1.0, 2.0, 3.0, 4.0],
            "ingredients_normalized": ['[["a","1","t"],["b","1","t"],["c","1","t"],["d","1","t"]]'] * 4,
            "others_count": [0, 1, 2, 3],
            "others_items": ["[]"] * 4,
            "CKG_INBUN_NM": ["2인분"] * 4,
            "CKG_TIME_NM": ["30분"] * 4,
            "CKG_KND_ACTO_NM": ["한식"] * 4,
            "CKG_MTH_ACTO_NM": ["볶기"] * 4,
            "CKG_STA_ACTO_NM": ["일상"] * 4,
            "CKG_MTRL_ACTO_NM": ["채소"] * 4,
            "CKG_DODF_NM": ["초급"] * 4,
            "INQ_CNT_LOG_CENTERED": [0.1, 0.2, 0.3, 0.4],
            "SRAP_CNT_LOG_CENTERED": [0.0, 0.1, 0.2, 0.3],
        }
    )
    pairs = high_correlation_pairs(labeled, labeled.iloc[:2], threshold=0.9)
    ratio_pair = next(
        (p for p in pairs if {p["a"], p["b"]} == {"others_ratio", "alias_match_ratio"}),
        None,
    )
    assert ratio_pair is not None
    assert abs(ratio_pair["pearson"]) > 0.9


if __name__ == "__main__":
    _self_check()
    run()
