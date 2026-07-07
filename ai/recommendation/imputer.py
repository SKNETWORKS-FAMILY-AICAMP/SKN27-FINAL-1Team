"""점수 없는 레시피 추론 및 final_recommend_score 생성."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline

from .config import MODEL_VERSION, POPULARITY_BASE_COLS, TARGET_COL
from .model import predict


def popularity_base_score(df: pd.DataFrame) -> np.ndarray:
    return df[list(POPULARITY_BASE_COLS)].fillna(0).sum(axis=1).to_numpy(dtype=float)


def quality_score(
    df: pd.DataFrame,
    labeled_mask: pd.Series,
    ml_predictions: np.ndarray,
) -> np.ndarray:
    rule = df[TARGET_COL].to_numpy(dtype=float)
    return np.where(labeled_mask.to_numpy(), rule, ml_predictions)


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

    pop_base = popularity_base_score(full_df)
    quality = quality_score(full_df, labeled_mask, ml_predictions)
    final = quality + pop_base

    out = pd.DataFrame(
        {
            "RCP_SNO": full_df["RCP_SNO"],
            "CKG_NM": full_df["CKG_NM"],
            TARGET_COL: full_df[TARGET_COL],
            "ml_predicted_recommend_score": ml_predictions,
            "final_recommend_score": final,
            "recommend_model_version": MODEL_VERSION,
        }
    )
    out["recommend_score_source"] = np.where(
        labeled_mask.to_numpy(), "rule", "ml_imputed"
    )
    return out


def imputed_rows(scored: pd.DataFrame) -> pd.DataFrame:
    return scored[scored["recommend_score_source"] == "ml_imputed"].copy()


if __name__ == "__main__":
    sample = pd.DataFrame(
        {
            "INQ_CNT_LOG_CENTERED": [0.5, -0.5],
            "SRAP_CNT_LOG_CENTERED": [0.2, 0.2],
        }
    )
    assert popularity_base_score(sample).tolist() == [0.7, -0.3]
