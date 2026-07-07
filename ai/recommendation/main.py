"""추천 점수 파이프라인 진입점."""

from __future__ import annotations

import pathlib
import sys

if __name__ == "__main__" and __package__ is None:
    _root = pathlib.Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(_root))

from sklearn.model_selection import train_test_split

from ai.recommendation import cross_validation, data_loader, evaluator, features, imputer, model
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
from ai.recommendation.utils import reset_seeds

# ML 실행 함수 
def run() -> None:

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    merged = data_loader.load_and_merge()           # 데이터 로드 및 병합
    reset_seeds(RANDOM_STATE)                       # 랜덤 시드 설정
    labeled, unlabeled = data_loader.split_labeled_unlabeled(merged)

    features.run_self_check()

    if len(labeled) < 2:
        raise ValueError("At least 2 labeled recipes are required for training and evaluation")

    # 트레인 / 테스트 데이터 분리 
    train_df, test_df = train_test_split(
        labeled,
        test_size=TEST_SIZE,
        random_state=RANDOM_STATE,
    )
    y_train = train_df[TARGET_COL]
    y_test = test_df[TARGET_COL]

    # 평가 파이프라인 빌드 및 트레이닝
    evaluation_pipeline = model.build_pipeline(MODEL_NAME)
    model.fit_pipeline(evaluation_pipeline, train_df, y_train)
    y_pred = model.predict(evaluation_pipeline, test_df)

    # 평가 리포트 생성
    eval_report = evaluator.evaluate(
        y_test,
        y_pred,
        train_row_count=len(train_df),
        test_row_count=len(test_df),
        model_type=MODEL_NAME,
    )
    evaluation_features = evaluation_pipeline.named_steps["feature_builder"].transform(merged)
    feature_report = evaluator.build_feature_report(evaluation_features, feature_columns())

    # seed 42 holdout과 별도로 동일 labeled 데이터의 5-fold 보조 검증을 수행한다.
    # fold 모델은 평가 후 폐기되며 아래 production 전체 재학습에는 사용하지 않는다.
    cv_report = cross_validation.run(labeled)
    eval_report["cross_validation"] = cross_validation.evaluation_report_section(
        cv_report
    )

    # 평가가 괜찮다는 전제로 모든 데이터를 가지고 재학습 (평가 데이터 까지 포함해서 예측 최대화 )
    pipeline = model.build_pipeline(MODEL_NAME)
    model.fit_pipeline(pipeline, labeled, labeled[TARGET_COL])
    full_df = merged.copy()
    labeled_mask = full_df[TARGET_COL].notna()

    # 메타데이터 생성
    metadata = {
        "model_version": MODEL_VERSION,
        "model_name": MODEL_NAME,
        "random_state": RANDOM_STATE,
        "feature_columns": feature_columns(),
        "clip_low": pipeline.clip_low_,
        "clip_high": pipeline.clip_high_,
        "labeled_count": int(labeled_mask.sum()),
        "unlabeled_count": int((~labeled_mask).sum()),
        "training_row_count": pipeline.training_row_count_,
        "refit_on_all_labeled": True,
    }

    # 파이프라인, 평가 리포트, 특성 리포트, 메타데이터 저장
    model.save_pipeline(pipeline, ARTIFACTS_DIR / "pipeline.joblib")
    evaluator.save_json(eval_report, ARTIFACTS_DIR / "evaluation_report.json")
    evaluator.save_json(feature_report, ARTIFACTS_DIR / "feature_report.json")
    evaluator.save_json(metadata, ARTIFACTS_DIR / "metadata.json")

    scored = imputer.build_scored_output(
        full_df,
        pipeline,
        labeled_mask=labeled_mask,
    )

    # 예측 출력 검증
    if len(scored) != len(merged) or not scored["RCP_SNO"].reset_index(drop=True).equals(
        merged["RCP_SNO"].reset_index(drop=True)
    ):
        raise RuntimeError("Scored output did not preserve the input recipe order")
    if scored["RCP_SNO"].duplicated().any():
        raise RuntimeError("Scored output contains duplicate RCP_SNO values")
    OUTPUT_SCORED_CSV.parent.mkdir(parents=True, exist_ok=True)
    scored.to_csv(OUTPUT_SCORED_CSV, index=False, encoding="utf-8-sig")

    # 출력 검증 결과 출력
    print(f"Saved pipeline -> {ARTIFACTS_DIR / 'pipeline.joblib'}")
    print(f"Saved scores -> {OUTPUT_SCORED_CSV}")
    sp = eval_report["Spearman"]
    sp_text = f"{sp:.4f}" if sp is not None else "N/A"
    cv_sp = cv_report["summary"]["Spearman"]
    cv_hit10 = cv_report["summary"]["Hit@10"]["mean"]
    cv_hit20 = cv_report["summary"]["Hit@20"]["mean"]
    cv_hit50 = cv_report["summary"]["Hit@50"]["mean"]
    print(f"Holdout RMSE={eval_report['RMSE']:.4f}  Spearman={sp_text}")
    print(
        "5-Fold Spearman "
        f"mean={cv_sp['mean']:.4f} std={cv_sp['std']:.4f} min={cv_sp['min']:.4f}"
    )
    print(
        f"5-Fold Hit@10={cv_hit10:.4f}  "
        f"Hit@20={cv_hit20:.4f}  Hit@50={cv_hit50:.4f}"
    )


if __name__ == "__main__":
    run()
