"""점수 없는 레시피 추론 및 final_recommend_score 생성."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline

from .config import MODEL_VERSION, TARGET_COL
from .model import predict


def clip_predictions(preds: np.ndarray, y_train: pd.Series) -> np.ndarray:
    low = float(y_train.quantile(0.01))
    high = float(y_train.quantile(0.99))
    return np.clip(preds, low, high)


def build_scored_output(
    full_df: pd.DataFrame,
    pipeline: Pipeline,
    y_train: pd.Series,
    *,
    labeled_mask: pd.Series,
) -> pd.DataFrame:
    raw_pred = predict(pipeline, full_df)
    clipped = clip_predictions(np.asarray(raw_pred, dtype=float), y_train)

    out = pd.DataFrame(
        {
            "RCP_SNO": full_df["RCP_SNO"],
            "CKG_NM": full_df["CKG_NM"],
            TARGET_COL: full_df[TARGET_COL],
            "ml_predicted_recommend_score": clipped,
            "recommend_model_version": MODEL_VERSION,
        }
    )
    has_label = labeled_mask.to_numpy()
    out["final_recommend_score"] = np.where(
        has_label,
        full_df[TARGET_COL].to_numpy(dtype=float),
        clipped,
    )
    out["recommend_score_source"] = np.where(has_label, "rule", "ml_imputed")
    return out


def imputed_rows(scored: pd.DataFrame) -> pd.DataFrame:
    return scored[scored["recommend_score_source"] == "ml_imputed"].copy()
