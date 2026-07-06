"""회귀·랭킹 평가 및 리포트 저장."""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from .config import (
    HIT_AT_K_VALUES,
    MODEL_VERSION,
    RANDOM_STATE,
    TARGET_COL,
    feature_columns,
)


def hit_at_k(y_true: np.ndarray, y_pred: np.ndarray, k: int) -> float | None:
    n = len(y_true)
    if n < k:
        return None
    true_top = set(np.argsort(-y_true)[:k])
    pred_top = set(np.argsort(-y_pred)[:k])
    return len(true_top & pred_top) / k


def _json_safe(value: Any) -> Any:
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value


def evaluate(
    y_true: pd.Series,
    y_pred: np.ndarray,
    *,
    train_row_count: int,
    test_row_count: int,
    model_type: str,
) -> dict[str, Any]:
    y = y_true.to_numpy(dtype=float)
    pred = np.asarray(y_pred, dtype=float)
    rmse = float(np.sqrt(mean_squared_error(y, pred)))
    mae = float(mean_absolute_error(y, pred))
    r2 = float(r2_score(y, pred))
    sp = spearmanr(y, pred).correlation
    spearman = None if sp is None or np.isnan(sp) else float(sp)

    report: dict[str, Any] = {
        "model_version": MODEL_VERSION,
        "random_state": RANDOM_STATE,
        "train_row_count": train_row_count,
        "test_row_count": test_row_count,
        "target_column": TARGET_COL,
        "feature_columns": feature_columns(),
        "model_type": model_type,
        "RMSE": rmse,
        "MAE": mae,
        "R2": r2,
        "Spearman": spearman,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    for k in HIT_AT_K_VALUES:
        report[f"Hit@{k}"] = hit_at_k(y, pred, k)
    return report


def build_feature_report(df: pd.DataFrame, cols: list[str]) -> dict[str, Any]:
    subset = df[cols]
    missing = {c: float(subset[c].isna().mean()) for c in cols}
    describe = subset.describe(include="all").astype(object).where(pd.notna, None).to_dict()
    return {
        "row_count": len(df),
        "missing_rate": missing,
        "describe": describe,
    }


def save_json(data: dict[str, Any], path: str | Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_json_safe(data), f, ensure_ascii=False, indent=2)
