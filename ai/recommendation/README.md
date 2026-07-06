# recommendation

`REVIEW_RANK_SCORE`가 있는 레시피로 추천 정렬용 점수를 학습하고, 없는 레시피는 ML로 impute하는 파이프라인입니다.

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

## 입력 / 출력

| 경로 | 설명 |
|------|------|
| `storage/processed/recipe/recipe_fix.csv` | 레시피 마스터 |
| `storage/processed/recipe/recipe_ingredient_alias.csv` | 재료 alias |
| `storage/processed/recipe/recipe_recommendation_scored.csv` | 최종 점수 |
| `ai/recommendation/artifacts/pipeline.joblib` | 학습 Pipeline |
| `ai/recommendation/artifacts/evaluation_report.json` | RMSE, MAE, R², Spearman, Hit@K |
| `ai/recommendation/artifacts/imputed_recommend_scores.csv` | impute된 행만 |

## 점수 규칙

- `REVIEW_RANK_SCORE` 있음 → `final_recommend_score` = 규칙 점수, `recommend_score_source` = `rule`
- 없음 → ML 예측(clip) → `ml_imputed`

## 평가 지표

- **회귀 (강의):** RMSE, MAE, R²
- **정렬 (추천):** Spearman, Hit@10/20/50 — `test_rows < K`이면 해당 Hit@K만 `null`
