"""추천 점수 파이프라인 설정."""

from __future__ import annotations

import pathlib
from typing import Any, Callable

from sklearn.ensemble import (
    ExtraTreesRegressor,
    HistGradientBoostingRegressor,
    RandomForestRegressor,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]
RECIPE_FIX_CSV = ROOT / "storage" / "processed" / "recipe" / "recipe_fix.csv"
INGREDIENT_ALIAS_CSV = ROOT / "storage" / "processed" / "recipe" / "recipe_ingredient_alias.csv"
ARTIFACTS_DIR = pathlib.Path(__file__).resolve().parent / "artifacts"
OUTPUT_SCORED_CSV = ROOT / "storage" / "processed" / "recipe" / "recipe_recommendation_scored.csv"

RANDOM_STATE = 42
TEST_SIZE = 0.2
MODEL_VERSION = "recommend_model_v1"
MODEL_NAME = "extra_trees"

TARGET_COL = "REVIEW_RANK_SCORE"

EXCLUDE_COLS = frozenset({
    "RCP_SNO",
    "CKG_NM",
    TARGET_COL,
    "REVIEW_STAR_NORM_AVG",
    "REVIEW_SENTIMENT_AVG",
    "INQ_CNT",
    "SRAP_CNT",
    "INQ_CNT_RATE",
    "INQ_CNT_LOG",
    "SRAP_CNT_LOG",
    "CRAWL_COOK_REVIEW_CNT",
    "CRAWL_COMMENT_CNT",
    "CKG_MTRL_CN",
    "ingredients_raw",
    "aliases_matched",
    "ingredients_normalized",
    "others_items",
})

CATEGORICAL_FEATURES = [
    "CKG_KND_ACTO_NM",
    "CKG_MTH_ACTO_NM",
    "CKG_STA_ACTO_NM",
    "CKG_MTRL_ACTO_NM",
    "CKG_DODF_NM",
]

NUMERIC_FEATURES = [
    "serving_size",
    "cooking_time_min",
]

INGREDIENT_FEATURES = [
    "ingredient_count",
    "unique_ingredient_count",
    "others_count",
    "others_ratio",
    "alias_match_ratio",
    "commonness_mean",
]

HIT_AT_K_VALUES = (10, 20, 50)


def _require_lightgbm() -> Any:
    try:
        import lightgbm as lgb
    except ImportError as exc:
        raise ImportError(
            "lightgbm is not installed. Add it to ai/requirements.txt or use another MODEL_NAME."
        ) from exc
    return lgb.LGBMRegressor(
        n_estimators=300,
        random_state=RANDOM_STATE,
        n_jobs=-1,
        verbose=-1,
    )


def get_regressor(name: str = MODEL_NAME) -> Any:
    registry: dict[str, Callable[[], Any]] = {
        "extra_trees": lambda: ExtraTreesRegressor(
            n_estimators=300,
            random_state=RANDOM_STATE,
            n_jobs=-1,
        ),
        "random_forest": lambda: RandomForestRegressor(
            n_estimators=300,
            random_state=RANDOM_STATE,
            n_jobs=-1,
        ),
        "hist_gbm": lambda: HistGradientBoostingRegressor(random_state=RANDOM_STATE),
        "lightgbm": _require_lightgbm,
    }
    if name not in registry:
        raise ValueError(f"Unknown MODEL_NAME: {name!r}. Choose from {list(registry)}")
    return registry[name]()


def feature_columns() -> list[str]:
    return CATEGORICAL_FEATURES + NUMERIC_FEATURES + INGREDIENT_FEATURES
