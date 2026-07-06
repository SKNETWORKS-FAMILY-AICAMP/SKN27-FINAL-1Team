"""점수 없는 레시피 추론 및 final_recommend_score 생성."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline

from .config import MODEL_VERSION, TARGET_COL
from .model import predict


def build_scored_output(
    full_df: pd.DataFrame,
    pipeline: Pipeline,
    *,
    labeled_mask: pd.Series,
) -> pd.DataFrame:
    if len(full_df) != len(labeled_mask):
        raise ValueError("labeled_mask must have the same length as full_df")
    ml_predictions = np.full(len(full_df), np.nan, dtype=float)
    unlabeled_positions = np.flatnonzero(~labeled_mask.to_numpy())
    if len(unlabeled_positions):
        unlabeled = full_df.iloc[unlabeled_positions]
        ml_predictions[unlabeled_positions] = np.asarray(
            predict(pipeline, unlabeled), dtype=float
        )

    out = pd.DataFrame(
        {
            "RCP_SNO": full_df["RCP_SNO"],
            "CKG_NM": full_df["CKG_NM"],
            TARGET_COL: full_df[TARGET_COL],
            "ml_predicted_recommend_score": ml_predictions,
            "recommend_model_version": MODEL_VERSION,
        }
    )
    has_label = labeled_mask.to_numpy()
    out["final_recommend_score"] = np.where(
        has_label,
        full_df[TARGET_COL].to_numpy(dtype=float),
        ml_predictions,
    )
    out["recommend_score_source"] = np.where(has_label, "rule", "ml_imputed")
    return out


def imputed_rows(scored: pd.DataFrame) -> pd.DataFrame:
    return scored[scored["recommend_score_source"] == "ml_imputed"].copy()
