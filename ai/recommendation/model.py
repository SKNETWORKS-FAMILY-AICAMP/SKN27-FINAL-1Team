"""sklearn Pipeline 구성·학습·저장."""

from __future__ import annotations

import pathlib
from typing import Any

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder

from .config import (
    CATEGORICAL_FEATURES,
    INGREDIENT_FEATURES,
    MODEL_NAME,
    NUMERIC_FEATURES,
    feature_columns,
    get_regressor,
)


def build_pipeline(model_name: str = MODEL_NAME) -> Pipeline:
    categorical_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            (
                "label_encoder",
                OrdinalEncoder(
                    handle_unknown="use_encoded_value",
                    unknown_value=-1,
                ),
            ),
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
            ("preprocessor", preprocessor),
            ("model", get_regressor(model_name)),
        ]
    )


def fit_pipeline(
    pipeline: Pipeline,
    X_train: pd.DataFrame,
    y_train: pd.Series,
) -> Pipeline:
    pipeline.fit(X_train[feature_columns()], y_train)
    return pipeline


def predict(pipeline: Pipeline, X: pd.DataFrame) -> Any:
    return pipeline.predict(X[feature_columns()])


def save_pipeline(pipeline: Pipeline, path: pathlib.Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, path)
