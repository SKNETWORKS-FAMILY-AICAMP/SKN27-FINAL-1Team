# recommendation

`REVIEW_RANK_SCORE`(품질: 별점+감성)가 있는 레시피로 추천 정렬용 점수를 학습하고, 없는 레시피는 ML로 impute합니다. 최종 정렬 점수는 품질 + 인기(조회·스크랩 log-centered) 합산입니다.

## 강의 구조 대응 (`auc_98.2/service/`)

| 강의 | ai/recommendation |
|------|-------------------|
| `utils.py` | `utils.py` (`reset_seeds`) |
| `data.py` | `data_loader.py` |
| `preprocess.py` | `features.py` |
| `model.py` | `model.py` |
| `run.py` | `main.py` |

## 실행 (프로젝트 루트)

```bash
python -m ai.recommendation.main
python ai/recommendation/main.py
python -m ai.recommendation.feature_screening
python -m ai.recommendation.feature_ablation
```

조기 종료 포인트 (feature self-check만):

```bash
python -m ai.recommendation.features
```

## 모델 교체

[`config.py`](config.py)에서 `MODEL_NAME` 한 줄 변경:

```python
MODEL_NAME = "extra_trees"  # random_forest | hist_gbm | lightgbm
```

`pipeline.joblib` contains raw-data feature generation, train-fitted ingredient
commonness, preprocessing, the regressor, and clipping bounds. Load it and call
`ai.recommendation.model.predict(pipeline, raw_merged_dataframe)`; callers do not
need to build feature columns separately.

## 입력 / 출력

| 경로 | 설명 |
|------|------|
| `storage/processed/recipe/recipe_fix.csv` | 레시피 마스터 |
| `storage/processed/recipe/recipe_ingredient_alias.csv` | 재료 alias |
| `storage/processed/recipe/recipe_recommendation_scored.csv` | 최종 점수 (Neo4j `reviewRankScore` 적재 기준) |
| `ai/recommendation/artifacts/pipeline.joblib` | 학습 Pipeline |
| `ai/recommendation/artifacts/evaluation_report.json` | RMSE, MAE, R², Spearman, Hit@K |
| `ai/recommendation/artifacts/feature_screening_report.json` | feature 단변량·중복·permutation Spearman drop (실험 03) |
| `ai/recommendation/artifacts/feature_ablation_report.json` | ablation 단계별 holdout 비교 (실험 03) |

## 점수 규칙

- ETL `REVIEW_RANK_SCORE` = `REVIEW_STAR_NORM_AVG + REVIEW_SENTIMENT_AVG` (품질만)
- ML 타깃: 위 품질 점수 (labeled 563건)
- `final_recommend_score` = 품질(rule 또는 ML 예측) + `INQ_CNT_LOG_CENTERED` + `SRAP_CNT_LOG_CENTERED`
- `REVIEW_RANK_SCORE` 있음 → 품질은 규칙 점수, `recommend_score_source` = `rule`
- 없음 → 품질은 ML 예측(clip) → `ml_imputed`
- Neo4j 적재: `recipe_recommendation_scored.csv`의 `final_recommend_score` → `reviewRankScore` (3,171건)

## 평가 지표

- **회귀 (강의):** RMSE, MAE, R²
- **정렬 (추천):** Spearman, Hit@10/20/50 — `test_rows < K`이면 해당 Hit@K만 `null`
