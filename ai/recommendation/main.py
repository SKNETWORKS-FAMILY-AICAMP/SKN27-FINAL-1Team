"""추천 점수 파이프라인 진입점."""

from __future__ import annotations

import pathlib
import sys

if __name__ == "__main__" and __package__ is None:
    _root = pathlib.Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(_root))

import pandas as pd
from sklearn.model_selection import train_test_split

from ai.recommendation import data_loader, evaluator, features, imputer, model
from ai.recommendation.config import (
    ARTIFACTS_DIR,
    MODEL_NAME,
    MODEL_VERSION,
    OUTPUT_SCORED_CSV,
    RANDOM_STATE,
    TARGET_COL,
    TEST_SIZE,
    feature_columns,
)
from ai.recommendation.features import IngredientCommonnessLookup
from ai.recommendation.utils import reset_seeds


@reset_seeds
def run() -> None:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    merged = data_loader.load_and_merge()
    labeled, unlabeled = data_loader.split_labeled_unlabeled(merged)

    featured_labeled = features.build_all_features(labeled)
    featured_unlabeled = features.build_all_features(unlabeled)
    features.run_self_check()

    train_df, test_df = train_test_split(
        featured_labeled,
        test_size=TEST_SIZE,
        random_state=RANDOM_STATE,
    )
    y_train = train_df[TARGET_COL]
    y_test = test_df[TARGET_COL]

    lookup = IngredientCommonnessLookup().fit(train_df)
    train_df = features.apply_commonness(train_df, lookup)
    test_df = features.apply_commonness(test_df, lookup)
    featured_unlabeled = features.apply_commonness(featured_unlabeled, lookup)

    full_df = pd.concat(
        [
            train_df.assign(_split="train"),
            test_df.assign(_split="test"),
            featured_unlabeled.assign(_split="unlabeled"),
        ],
        ignore_index=True,
    )
    labeled_mask = full_df[TARGET_COL].notna()

    pipeline = model.build_pipeline(MODEL_NAME)
    model.fit_pipeline(pipeline, train_df, y_train)
    y_pred = model.predict(pipeline, test_df)

    eval_report = evaluator.evaluate(
        y_test,
        y_pred,
        train_row_count=len(train_df),
        test_row_count=len(test_df),
        model_type=MODEL_NAME,
    )
    feature_report = evaluator.build_feature_report(full_df, feature_columns())

    clip_low = float(y_train.quantile(0.01))
    clip_high = float(y_train.quantile(0.99))
    metadata = {
        "model_version": MODEL_VERSION,
        "model_name": MODEL_NAME,
        "random_state": RANDOM_STATE,
        "feature_columns": feature_columns(),
        "clip_low": clip_low,
        "clip_high": clip_high,
        "labeled_count": int(labeled_mask.sum()),
        "unlabeled_count": int((~labeled_mask).sum()),
    }

    model.save_pipeline(pipeline, ARTIFACTS_DIR / "pipeline.joblib")
    evaluator.save_json(eval_report, ARTIFACTS_DIR / "evaluation_report.json")
    evaluator.save_json(feature_report, ARTIFACTS_DIR / "feature_report.json")
    evaluator.save_json(metadata, ARTIFACTS_DIR / "metadata.json")

    scored = imputer.build_scored_output(
        full_df,
        pipeline,
        y_train,
        labeled_mask=labeled_mask,
    )
    imputed_only = imputer.imputed_rows(scored)

    OUTPUT_SCORED_CSV.parent.mkdir(parents=True, exist_ok=True)
    scored.to_csv(OUTPUT_SCORED_CSV, index=False, encoding="utf-8-sig")
    imputed_only.to_csv(
        ARTIFACTS_DIR / "imputed_recommend_scores.csv",
        index=False,
        encoding="utf-8-sig",
    )

    print(f"Saved pipeline -> {ARTIFACTS_DIR / 'pipeline.joblib'}")
    print(f"Saved scores -> {OUTPUT_SCORED_CSV}")
    print(f"RMSE={eval_report['RMSE']:.4f}  Spearman={eval_report['Spearman']:.4f}")


if __name__ == "__main__":
    run()
