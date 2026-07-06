"""sklearn Pipeline 구성·학습·저장."""

from __future__ import annotations

import pathlib
from typing import Any

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder

from .config import (
    CATEGORICAL_FEATURES,
    INGREDIENT_FEATURES,
    MODEL_NAME,
    NUMERIC_FEATURES,
    feature_columns,
    get_regressor,
)
from .features import RecommendationFeatureBuilder

_ONEHOT_MODELS = frozenset({"extra_trees", "random_forest", "lightgbm"})


def _categorical_encoder(model_name: str) -> OneHotEncoder | OrdinalEncoder:
    if model_name in _ONEHOT_MODELS:
        return OneHotEncoder(handle_unknown="ignore")
    if model_name == "hist_gbm":
        return OrdinalEncoder(
            handle_unknown="use_encoded_value",
            unknown_value=-1,
        )
    raise ValueError(
        f"Unknown MODEL_NAME: {model_name!r}. Choose from {sorted(_ONEHOT_MODELS | {'hist_gbm'})}"
    )


def build_pipeline(model_name: str = MODEL_NAME) -> Pipeline:
    categorical_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("encoder", _categorical_encoder(model_name)),
        ]
    )
    numeric_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
        ]
    )
    numeric_cols = NUMERIC_FEATURES + INGREDIENT_FEATURES
    preprocessor = ColumnTransformer(
        transformers=[
            ("cat", categorical_pipeline, CATEGORICAL_FEATURES),
            ("num", numeric_pipeline, numeric_cols),
        ]
    )
    return Pipeline(
        steps=[
            ("feature_builder", RecommendationFeatureBuilder()),
            ("preprocessor", preprocessor),
            ("model", get_regressor(model_name)),
        ]
    )


def fit_pipeline(
    pipeline: Pipeline,
    X_train: pd.DataFrame,
    y_train: pd.Series,
) -> Pipeline:
    pipeline.fit(X_train, y_train)
    pipeline.clip_low_ = float(y_train.quantile(0.01))
    pipeline.clip_high_ = float(y_train.quantile(0.99))
    pipeline.training_row_count_ = len(X_train)
    return pipeline


def predict(pipeline: Pipeline, X: pd.DataFrame, *, clip: bool = True) -> Any:
    predictions = pipeline.predict(X)
    if not clip:
        return predictions
    if not hasattr(pipeline, "clip_low_") or not hasattr(pipeline, "clip_high_"):
        raise ValueError("Pipeline does not contain fitted clipping bounds")
    return predictions.clip(pipeline.clip_low_, pipeline.clip_high_)


def save_pipeline(pipeline: Pipeline, path: pathlib.Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, path)
