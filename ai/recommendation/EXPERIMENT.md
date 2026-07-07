# 01. 조회·스크랩 분리 실험 기록

`REVIEW_RANK_SCORE`에서 인기(조회·스크랩) 항을 빼 잔차 타깃으로 학습하고, 동일 컬럼을 feature로 넣었을 때 지표가 어떻게 변하는지 확인한 실험입니다.

**상태:** 실험 코드는 확인 후 **베이스라인으로 되돌림**. 본 문서만 실험 기록을 보존합니다.

---

## 1. 실험 일지

| 순서 | 일시 (KST) | 일시 (UTC) | 내용 |
|------|------------|------------|------|
| 1 | 2026-07-06 17:37:21 | 2026-07-06 08:37:21 | 베이스라인 실행 (`extra_trees`, 전체 타깃, feature 13개). `evaluation_report.json` 생성 |
| 2 | 2026-07-06 18:44~18:46 | — | `MODEL_NAME=lightgbm` 교체 시도. 패키지 미설치 후 설치·재실행. RMSE 2.14, Spearman 0.10으로 베이스라인 대비 하락 |
| 3 | 2026-07-06 23:09:57 | 2026-07-06 14:09:57 | 잔차 타깃 + 인기 feature 실험 실행. RMSE 0.38, Spearman 0.098. 테스트 6건 통과 |
| 4 | 2026-07-06 23:10~ | — | 순위 지표 개선 미미 판단. 실험 코드 되돌림, 본 문서(`EXPERIMENT.md`)에 기록 보존 |

---

## 2. 배경

### 2.1. 기존 `REVIEW_RANK_SCORE` (ETL 규칙)

```
REVIEW_RANK_SCORE
  = REVIEW_STAR_NORM_AVG
  + REVIEW_SENTIMENT_AVG
  + INQ_CNT_LOG_CENTERED
  + SRAP_CNT_LOG_CENTERED
```

- 라벨 있음(563건): `final_recommend_score` = 규칙 점수 (`rule`)
- 라벨 없음(2,608건): ML impute (`ml_imputed`)

### 2.2. 베이스라인 ML 설정

- `MODEL_NAME`: `extra_trees`
- `random_state`: 42, `test_size`: 0.2 (train 450 / test 113)
- feature 13개: 카테고리 5 + 인분·조리시간 2 + 재료 파생 6
- 인기 컬럼(`INQ_CNT_LOG_CENTERED`, `SRAP_CNT_LOG_CENTERED`)은 **feature에 미포함**

### 2.3. 실험 동기

타깃에 이미 들어 있는 조회·스크랩 신호를 feature로도 쓰면 평가가 부풀어 오를 수 있어, **타깃에서 인기 항을 빼고(잔차)** feature로 넣는 방식을 시험했습니다. 성능이 괜찮으면 ETL 공식 변경을 검토할 예정이었습니다.

---

## 3. 실험 설계

### 3.1. 학습 타깃 (잔차)

```
train_target = REVIEW_RANK_SCORE - INQ_CNT_LOG_CENTERED - SRAP_CNT_LOG_CENTERED
             ≈ REVIEW_STAR_NORM_AVG + REVIEW_SENTIMENT_AVG
```

### 3.2. 추가 feature

- `INQ_CNT_LOG_CENTERED`
- `SRAP_CNT_LOG_CENTERED`

(`NUMERIC_FEATURES`에 포함, 모델 입력 15개)

### 3.3. impute 시 최종 점수 복원

```
base_score = INQ_CNT_LOG_CENTERED + SRAP_CNT_LOG_CENTERED
final_recommend_score (unlabeled) = base_score + ml_predicted_residual
```

라벨 있는 행은 기존과 동일하게 `REVIEW_RANK_SCORE`(규칙 점수) 유지.

### 3.4. 변경 파일 (실험 시)

| 파일 | 변경 내용 |
|------|-----------|
| `config.py` | `POPULARITY_BASE_COLS`, `TARGET_FORMULA`, 인기 컬럼을 `NUMERIC_FEATURES`에 추가 |
| `main.py` | `y_train`/`y_test`/재학습 타깃을 `residual_target()`으로 변경 |
| `imputer.py` | `residual_target()`, `popularity_base_score()`, impute 시 `base + residual` |
| `evaluator.py` | `evaluation_report.json`에 `target_formula` 기록 |
| `test_recommendation_pipeline.py` | 잔차·복원 테스트 추가 |

---

## 4. 결과

동일 데이터·동일 `extra_trees`·동일 split 기준.

| 지표 | 베이스라인 (전체 타깃) | 실험 (잔차 타깃 + 인기 feature) |
|------|------------------------|----------------------------------|
| RMSE | 2.023 | 0.377 |
| MAE | 1.594 | 0.160 |
| R² | -0.208 | -0.196 |
| Spearman | **0.131** | 0.098 |
| Hit@10 | 0.20 | 0.20 |
| Hit@20 | **0.25** | 0.20 |
| Hit@50 | 0.50 | **0.52** |

실험 실행 시 터미널 출력 (2026-07-06 23:09:57 KST): `RMSE=0.3767  Spearman=0.0985`

### 4.1. 해석

1. **RMSE/MAE는 타깃 스케일이 달라져 직접 비교 불가**  
   잔차 타깃(별점+감성 근사)은 분산이 작아 절대 오차가 자연스럽게 줄어듭니다.

2. **순위 지표(우선 비교 대상)**  
   - Spearman: 0.131 → 0.098 (소폭 하락)  
   - Hit@10: 동일  
   - Hit@20: 0.25 → 0.20 (하락)  
   - Hit@50: 0.50 → 0.52 (소폭 상승)

3. **R²**는 여전히 음수 — 잔차(리뷰 품질)를 메타+인기로 맞추는 것도 쉽지 않음.

4. **부가 실험 (일지 #2):** `lightgbm`으로 모델만 교체 시 RMSE 2.14, Spearman 0.10으로 `extra_trees` 베이스라인보다 나빠짐 (소량 데이터 한계).

### 4.2. 결론 (당시 판단)

- 잔차 분리 + 인기 feature 추가만으로 **순위 품질이 뚜렷이 개선되지 않음**.
- ETL `REVIEW_RANK_SCORE` 공식 변경은 **보류**. 코드는 베이스라인으로 복원.
- 이후 검토: 인기 파생 feature 추가(`INQ_CNT_RATE` 등), 별점·감성은 impute 불가하므로 최후 순위.

---

## 5. 재현 방법

1. 위 「3.4. 변경 파일」 내용을 임시 적용 (또는 실험 커밋이 있으면 해당 브랜치/커밋 체크아웃).
2. 프로젝트 루트에서 실행:

```bash
python ai/recommendation/main.py
```

3. `ai/recommendation/artifacts/evaluation_report.json`에서 `target_formula`, feature 목록, 지표 확인.
4. 비교 후 `git checkout` 등으로 베이스라인 복원.

---

## 6. 참고

- 베이스라인 `evaluation_report.json`: 2026-07-06 17:37:21 KST (08:37:21 UTC), feature 13개.
- 실험 `evaluation_report.json`: 2026-07-06 23:09:57 KST (14:09:57 UTC), feature 15개, `target_formula` 포함.
- 파이프라인 사용법·입출력: [README.md](README.md)

---

# 02. 재료 feature 확장 실험

베이스라인(실험 01 이후 코드 복원 상태)의 **현재 ML feature 13개**를 점검하고, 재료 파생 feature를 단계적으로 추가·스크리닝하는 실험입니다.

**상태:** 준비 중 — 본 섹션은 feature 재점검 및 사전 분석용. 코드 변경·지표 비교는 이후 단계.

---

## 1. 실험 일지

| 순서 | 일시 (KST) | 내용 |
|------|------------|------|
| 1 | 2026-07-07 — | 실험 02 착수. 베이스라인 feature 13개 목록·산출·전처리 정리 (본 문서 §2~§4) |
| 2 | (예정) | labeled 563건 기준 feature별 Spearman·중복 상관 스크리닝 |
| 3 | (예정) | 후보 재료 feature 2~3개씩 ablation 후 `evaluation_report.json` 비교 |

---

## 2. 분석 설정 (베이스라인)

| 항목 | 값 |
|------|-----|
| 타깃 | `REVIEW_RANK_SCORE` (ETL 규칙 점수 전체) |
| 모델 | `extra_trees` (`n_estimators=300`, `random_state=42`) |
| split | `train_test_split` 0.2 → train 450 / test 113 |
| feature 수 | **13** (카테고리 5 + 수치 2 + 재료 6) |
| 입력 CSV | `recipe_fix.csv` + `recipe_ingredient_alias.csv` (`data_loader.load_and_merge`) |
| 베이스라인 지표 | RMSE 2.02, Spearman 0.131, Hit@10 0.20, Hit@20 0.25, Hit@50 0.50 (2026-07-06 17:37 KST) |

### 2.1. 파이프라인 흐름

```
recipe_fix + recipe_ingredient_alias (merge)
  → RecommendationFeatureBuilder (features.py: 메타·재료 파생 + commonness fit)
  → ColumnTransformer (model.py: 카테고리 인코딩 + 수치 impute)
  → ExtraTreesRegressor
  → predict 시 y를 [train 1%ile, 99%ile] clip
```

---

## 3. ML feature 목록 (13개)

`config.py`의 `feature_columns()` = `CATEGORICAL_FEATURES` + `NUMERIC_FEATURES` + `INGREDIENT_FEATURES`.

### 3.1. 카테고리 (5)

원본은 `recipe_fix.csv` 컬럼. 별도 파생 없이 merge 결과에서 그대로 사용.

| # | feature | 원본 컬럼 | 산출 방법 | 의미 | ML 전처리 (`extra_trees`) | impute |
|---|---------|-----------|-----------|------|---------------------------|--------|
| 1 | `CKG_KND_ACTO_NM` | 동일 | CSV 그대로 | 요리 종류 (예: 메인반찬, 국/탕) | `SimpleImputer(most_frequent)` → `OneHotEncoder(handle_unknown="ignore")` | ○ |
| 2 | `CKG_MTH_ACTO_NM` | 동일 | CSV 그대로 | 조리 방법 (예: 끓이기, 볶기) | 동일 | ○ |
| 3 | `CKG_STA_ACTO_NM` | 동일 | CSV 그대로 | 상황/목적 (예: 일상, 술안주) | 동일 | ○ |
| 4 | `CKG_MTRL_ACTO_NM` | 동일 | CSV 그대로 | 주재료 유형 (예: 돼지고기, 해물) | 동일 | ○ |
| 5 | `CKG_DODF_NM` | 동일 | CSV 그대로 | 난이도 (예: 초급, 중급, 고급) | 동일 | ○ |

- 결측 시: 해당 컬럼 **최빈값**으로 대체 후 one-hot.
- 학습에 없던 카테고리: one-hot 벡터 **전부 0** (`handle_unknown="ignore"`).

### 3.2. 메타 수치 (2)

`features.build_meta_features()`에서 텍스트를 정수로 파싱.

| # | feature | 원본 컬럼 | 산출 방법 | 의미 | ML 전처리 | impute |
|---|---------|-----------|-----------|------|-----------|--------|
| 6 | `serving_size` | `CKG_INBUN_NM` | `parse_serving_size`: 문자열에서 **첫 번째 정수** 추출 (예: `"2인분"` → 2). `"확인필요"`·빈값 → `None` | 인분 수 | `SimpleImputer(median)` | ○ |
| 7 | `cooking_time_min` | `CKG_TIME_NM` | `parse_cooking_time_minutes`: 첫 정수 추출. `"시간"` 포함 시 ×60분, `"분"` 포함 시 그대로 분 | 조리 시간(분) | `SimpleImputer(median)` | ○ |

- 구현: `etl/recipe/load_to_postgres/loader.py`의 파서를 `features.py`에서 재사용.

### 3.3. 재료 파생 (6)

`recipe_ingredient_alias.csv`의 `ingredients_normalized`, `others_count`, `others_items` 사용.  
`ingredients_normalized` 형식: `[[이름, 양, 단위], ...]` (JSON/리터럴 문자열).

| # | feature | 원본·입력 | 산출 방법 | 의미 | ML 전처리 | impute |
|---|---------|-----------|-----------|------|-----------|--------|
| 8 | `ingredient_count` | `ingredients_normalized` | 파싱한 재료 행 **개수** `len(normalized)` | 레시피에 적힌 재료 항목 수 | `SimpleImputer(median)` | ○ |
| 9 | `unique_ingredient_count` | 동일 | 재료 **이름**(각 행 `[0]`)의 **고유 개수** | 서로 다른 재료 종류 수 | 동일 | ○ |
| 10 | `others_count` | `others_count` 또는 `others_items` | CSV `others_count` 우선; 없으면 `others_items` 파싱 길이 | alias에 매칭되지 않은 재료 수 | 동일 | ○ |
| 11 | `others_ratio` | 위와 `ingredient_count` | `others_count / ingredient_count` (분모 0이면 0) | 미매칭 재료 **비율** | 동일 | ○ |
| 12 | `alias_match_ratio` | 위와 동일 | `1.0 - others_ratio` | alias 정규화 **매칭 비율** | 동일 | ○ |
| 13 | `commonness_mean` | `ingredients_normalized` + **train fit 통계** | `IngredientCommonnessLookup`: fit 시 train 각 재료가 등장한 **레시피 수** 집계 → transform 시 레시피 내 재료별 등장 수의 **평균**. train에 없는 재료는 0 | 재료가 데이터셋에서 얼마나 **흔한지**(대중 재료 vs 희귀) | 동일 | ○ |

- `alias_match_ratio`와 `others_ratio`는 **선형 종속** (`합=1`). 정보 중복 가능 → 스크리닝 시 한쪽만 봐도 됨.
- `commonness_mean`만 **train split 기준 fit** (`RecommendationFeatureBuilder.fit`). 평가·재학습 파이프라인마다 train 행으로 다시 fit.

---

## 4. 모델에 넣지 않는 컬럼 (`EXCLUDE_COLS`)

merge 후 DataFrame에 있으나 **의도적으로 feature에서 제외**된 항목. 실험 02에서 후보 검토 시 참고.

| 컬럼 | 제외 이유 | impute 시 값 존재 |
|------|-----------|-------------------|
| `REVIEW_RANK_SCORE` | 타깃 (라벨) | 라벨 없는 행만 NaN |
| `REVIEW_STAR_NORM_AVG`, `REVIEW_SENTIMENT_AVG` | 리뷰 품질 — 라벨 없는 행에 없음 | △ 라벨 있는 행만 |
| `INQ_CNT`, `SRAP_CNT`, `INQ_CNT_RATE`, `INQ_CNT_LOG`, `SRAP_CNT_LOG` | 인기·트래픽 (실험 01에서 타깃과 겹침 이슈) | ○ |
| `INQ_CNT_LOG_CENTERED`, `SRAP_CNT_LOG_CENTERED` | 타깃 구성 요소 (현재 베이스라인 feature 아님) | ○ |
| `ingredients_normalized`, `others_items`, `ingredients_raw`, `aliases_matched` | 재료 **원문** — 파생 feature로만 사용 | ○ |
| `CKG_MTRL_CN` | 재료 원문 텍스트 (파싱 전) | ○ |
| `RCP_SNO`, `CKG_NM` | ID·이름 (식별자) | ○ |

---

## 5. 실험 02 예정 절차

1. **사전 스크리닝** (코드 변경 없음): labeled 563건에서 수치·재료 7개 ↔ `REVIEW_RANK_SCORE` Spearman, feature 간 상관(|ρ|>0.7) 표 작성.
2. **후보 추가** (2~3개씩): 예) `commonness_min`, `commonness_max`, `rare_ingredient_ratio` — `features.py` + `config.py` 최소 수정.
3. **ablation**: 동일 `random_state=42`로 베이스라인 vs +후보만 비교. **Spearman, Hit@10/20** 우선.
4. **기록**: 본 문서 일지·결과 표 갱신. 개선 없으면 코드 되돌림.

### 5.1. 후보 feature (미구현)

| 후보 | 산출(안) | 기대 |
|------|----------|------|
| `commonness_min` | 레시피 내 재료 등장 수 **최솟값** | 희귀 재료 1개 영향 |
| `commonness_max` | **최댓값** | 대중 재료 포함 |
| `rare_ingredient_ratio` | train 등장 수 &lt; k 인 재료 비율 | niche 요리 구분 |
| `unique_ingredient_ratio` | `unique_ingredient_count / ingredient_count` | 중복 재료 비율 |

---

## 6. 참고 (코드 위치)

| 역할 | 파일 |
|------|------|
| feature 목록 | `config.py` — `CATEGORICAL_FEATURES`, `NUMERIC_FEATURES`, `INGREDIENT_FEATURES` |
| 파생 로직 | `features.py` — `build_meta_features`, `build_basic_ingredient_features`, `IngredientCommonnessLookup` |
| 전처리·모델 | `model.py` — `ColumnTransformer`, `OneHotEncoder`, `SimpleImputer` |
| 데이터 병합 | `data_loader.py` — `load_and_merge` |
| 인분·시간 파서 | `etl/recipe/load_to_postgres/loader.py` — `parse_serving_size`, `parse_cooking_time_minutes` |
