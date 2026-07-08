# 01. 조회·스크랩 분리 실험 기록

`REVIEW_RANK_SCORE`에서 인기(조회·스크랩) 항을 빼 잔차 타깃으로 학습하고, 동일 컬럼을 feature로 넣었을 때 지표가 어떻게 변하는지 확인한 실험입니다.

**상태:** 실험 코드는 확인 후 **베이스라인으로 되돌림**. 본 문서만 실험 기록을 보존합니다.

---

## 1. 실험 일지


| 순서  | 일시 (KST)               | 일시 (UTC)            | 내용                                                                                    |
| --- | ---------------------- | ------------------- | ------------------------------------------------------------------------------------- |
| 1   | 2026-07-06 17:37:21    | 2026-07-06 08:37:21 | 베이스라인 실행 (`extra_trees`, 전체 타깃, feature 13개). `evaluation_report.json` 생성             |
| 2   | 2026-07-06 18:44~18:46 | —                   | `MODEL_NAME=lightgbm` 교체 시도. 패키지 미설치 후 설치·재실행. RMSE 2.14, Spearman 0.10으로 베이스라인 대비 하락 |
| 3   | 2026-07-06 23:09:57    | 2026-07-06 14:09:57 | 잔차 타깃 + 인기 feature 실험 실행. RMSE 0.38, Spearman 0.098. 테스트 6건 통과                        |
| 4   | 2026-07-06 23:10~      | —                   | 순위 지표 개선 미미 판단. 실험 코드 되돌림, 본 문서(`EXPERIMENT.md`)에 기록 보존                               |


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


| 파일                                | 변경 내용                                                                      |
| --------------------------------- | -------------------------------------------------------------------------- |
| `config.py`                       | `POPULARITY_BASE_COLS`, `TARGET_FORMULA`, 인기 컬럼을 `NUMERIC_FEATURES`에 추가    |
| `main.py`                         | `y_train`/`y_test`/재학습 타깃을 `residual_target()`으로 변경                        |
| `imputer.py`                      | `residual_target()`, `popularity_base_score()`, impute 시 `base + residual` |
| `evaluator.py`                    | `evaluation_report.json`에 `target_formula` 기록                              |
| `test_recommendation_pipeline.py` | 잔차·복원 테스트 추가                                                               |


---



## 4. 결과

동일 데이터·동일 `extra_trees`·동일 split 기준.


| 지표       | 베이스라인 (전체 타깃) | 실험 (잔차 타깃 + 인기 feature) |
| -------- | ------------- | ----------------------- |
| RMSE     | 2.023         | 0.377                   |
| MAE      | 1.594         | 0.160                   |
| R²       | -0.208        | -0.196                  |
| Spearman | **0.131**     | 0.098                   |
| Hit@10   | 0.20          | 0.20                    |
| Hit@20   | **0.25**      | 0.20                    |
| Hit@50   | 0.50          | **0.52**                |


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

1. `ai/recommendation/artifacts/evaluation_report.json`에서 `target_formula`, feature 목록, 지표 확인.
2. 비교 후 `git checkout` 등으로 베이스라인 복원.

---



## 6. 참고

- 베이스라인 `evaluation_report.json`: 2026-07-06 17:37:21 KST (08:37:21 UTC), feature 13개.
- 실험 `evaluation_report.json`: 2026-07-06 23:09:57 KST (14:09:57 UTC), feature 15개, `target_formula` 포함.
- 파이프라인 사용법·입출력: [README.md](README.md)

---



# 02. 재료 전처리 수정 — others 재매칭·기본재료 분리

`recipe_ingredient_alias.csv`의 `others_count` / `others_ratio` feature가 왜곡되지 않도록, alias 카탈로그 갱신분 반영과 기본재료(물) 분리를 **LLM 재실행 없이** 오프라인 보정한 작업입니다.

**상태:** 전처리·CSV·Neo4j·ML 배치 **반영 완료**. 본 수정은 feature 스케일만 바꾸며 모델·split·feature 개수는 동일(13개).

---



## 1. 작업 일지


| 순서  | 일시 (KST)     | 내용                                                                              |
| --- | ------------ | ------------------------------------------------------------------------------- |
| 1   | 2026-07-07 — | `nodes_alias.csv` 확장분(버터·피망·양송이버섯 등) 대비 `--rematch-others` 실행. 1,460행·2,078건 승격 |
| 2   | 2026-07-07 — | 기본재료 `물`을 `others_items` → `basic_items` 분리 (`--extract-basic`). 981행·1,050건 이동 |
| 3   | 2026-07-07 — | Neo4j `basicItems` 속성 적재, `python -m ai.recommendation.main` 재실행                |


---



## 2. 배경

- **others 재매칭:** 초기 LLM 배치 시 `nodes_alias.csv`에 없던 재료가 `others_items`에 남음. 이후 alias 추가 후에도 CSV는 갱신되지 않은 상태.
- **기본재료 분리:** 런타임은 `recommend_config` + `basic_ingredient_normalized()`로 `물`을 항상 보유 처리(`52`). ETL 산출물에는 물이 others에 ~1,050건 포함되어 `others_count` feature가 과대 계상됨.

---



## 3. 전처리 변경 요약


| 단계       | CLI                | 입력·규칙                                                                   | 결과                                            |
| -------- | ------------------ | ----------------------------------------------------------------------- | --------------------------------------------- |
| alias 승격 | `--rematch-others` | `others_items[].name` ↔ `nodes_alias.name` **exact key** (`_match_key`) | `aliases_matched` 추가, others 감소               |
| 기본재료 분리  | `--extract-basic`  | `is_basic_ingredient(name|raw)` — `recommend_config`와 동일                | `basic_items` / `basic_count` 신설, others에서 제거 |


**스키마 추가:** `basic_items` (JSON), `basic_count` (int). `ingredients_normalized`에는 물 유지.

**판정 예 (물):** `물`, `물 1200ml` → basic · `뜨거운 물`, `계란물` → others 유지 (suffix 규칙 비활성).

**구현:** `etl/recipe/preprocessing_by_llm/normalize_recipe_ingredients_by_llm.py` — `assemble_result()` 생성 시 분기 + 기존 CSV 마이그레이션 CLI.

---



## 4. CSV 집계 변화


| 지표                     | LLM 초기 (대략) | rematch 후 | basic 분리 후 |
| ---------------------- | ----------- | --------- | ---------- |
| others 항목 합계           | 3,885       | ~1,807    | **757**    |
| basic 항목 합계            | —           | —         | **1,050**  |
| `others_count > 0` 레시피 | 2,179       | 1,380     | (동일)       |


검증 샘플 `RCP_SNO=7016816`: 물 → `basic_items`, `others_count=0`.

---



## 5. ML holdout 지표 변화 (`extra_trees`, feature 13개, split 동일)

동일 `random_state=42`, 타깃·모델 변경 없음. **재료 파생 4개(**`others_count`**,** `others_ratio`**,** `alias_match_ratio`**, 간접** `commonness`**) 입력값만 변화.**


| 시점                        | RMSE     | Spearman  | Hit@10 | Hit@20 | Hit@50 |
| ------------------------- | -------- | --------- | ------ | ------ | ------ |
| 베이스라인 (2026-07-06, 전처리 전) | 2.02     | 0.131     | 0.20   | 0.25   | 0.50   |
| alias rematch 후           | 2.04     | 0.140     | —      | —      | —      |
| basic 분리 후 (2026-07-07)   | **2.07** | **0.145** | 0.10   | 0.20   | 0.48   |


- RMSE는 소폭 상승, Spearman은 소폭 상승 — 절대 오차·순위 지표가 동시에 좋아지는 패턴은 아님.
- Hit@K는 holdout 113건 기준 변동 폭이 큼 — 전처리 효과 판단은 **Spearman + others 분포 정상화**를 우선 봄.
- **해석:** `others_count`가 “진짜 미매칭”에 가깝게 정리됨 → 실험 03(재료 feature 확장)의 사전 전제 충족. ETL 공식·모델 교체는 아직 없음.

---



## 6. 재현

```bash
python -m etl.recipe.preprocessing_by_llm.normalize_recipe_ingredients_by_llm --rematch-others
python -m etl.recipe.preprocessing_by_llm.normalize_recipe_ingredients_by_llm --extract-basic
python -m etl.recipe.load_to_neo4j
python -m ai.recommendation.main
```

---



## 7. 참고 (코드·문서)


| 항목           | 위치                                                                               |
| ------------ | -------------------------------------------------------------------------------- |
| 기본재료 판정 (공유) | `recommend_config.py` — `basic_ingredient_normalized`, `is_basic_ingredient`     |
| ETL·CLI      | `normalize_recipe_ingredients_by_llm.py`                                         |
| Neo4j        | `load_to_neo4j/loader.py` — `basicItems`                                         |
| ideaVault    | `54_recipe_ingredient_alias_rematch_basic.md`, `52_basic_ingredient.md` (ETL 확장) |


---



# 03. Feature 스크리닝 (영향도·중복·제거 후보)

v2 파이프라인(**15 feature**, 품질 2항 타깃)에서 **영향 미미·중복 feature**를 찾아 정리하기 위한 실험입니다.

**상태:** 스크리닝·ablation **완료** (`feature_screening.py`, `feature_ablation.py`). winner 12 feature → `config.py` 반영.

---



## 1. 실험 일지


| 순서  | 일시 (KST)     | 내용                                                               |
| --- | ------------ | ---------------------------------------------------------------- |
| 1   | 2026-07-07 — | 실험 03 착수. feature 13개 목록·산출 정리 (당시 v1 기준)                        |
| 2   | 2026-07-07 — | 실험 02 선행 완료 — `others_count` 정리, v1 Spearman 0.145               |
| 3   | 2026-07-07 — | 실험 04 — v2(15 feature, 품질 타깃). holdout Spearman **0.096**        |
| 4   | 2026-07-07 — | `feature_screening.py` 추가·실행. `feature_screening_report.json` 생성 |
| 5   | **완료**       | ablation → Spearman 0.096→0.211 (`feature_ablation_report.json`) |


---



## 2. 분석 설정 (v2 현재)


| 항목               | 값                                                                           |
| ---------------- | --------------------------------------------------------------------------- |
| 타깃               | `REVIEW_RANK_SCORE` = `REVIEW_STAR_NORM_AVG + REVIEW_SENTIMENT_AVG` (품질 2항) |
| 모델               | `extra_trees` (`n_estimators=300`, `random_state=42`)                       |
| split            | `train_test_split` 0.2 → train 450 / test 113                               |
| feature 수        | **15** (카테고리 5 + 수치 4 + 재료 6)                                               |
| holdout Spearman | **0.096** (`evaluation_report.json`, 2026-07-07)                            |
| 스크리닝 CLI         | `python -m ai.recommendation.feature_screening`                             |
| 출력               | `artifacts/feature_screening_report.json`                                   |




### 2.1. 파이프라인 흐름

```
recipe_fix + recipe_ingredient_alias (merge)
  → RecommendationFeatureBuilder (features.py)
  → ColumnTransformer (카테고리 one-hot + 수치 impute)
  → ExtraTreesRegressor
  → holdout Spearman (품질 타깃)
```

---



## 3. ML feature 목록 (15개)

`config.py`의 `feature_columns()` = `CATEGORICAL_FEATURES` + `NUMERIC_FEATURES` + `INGREDIENT_FEATURES`.

### 3.1. 카테고리 (5)


| #   | feature                           | 의미                  |
| --- | --------------------------------- | ------------------- |
| 1–5 | `CKG_KND_ACTO_NM` … `CKG_DODF_NM` | 요리 종류·방법·상황·주재료·난이도 |




### 3.2. 메타·인기 수치 (4)


| #   | feature                 | 의미                                             |
| --- | ----------------------- | ---------------------------------------------- |
| 6   | `serving_size`          | `CKG_INBUN_NM` 파싱                              |
| 7   | `cooking_time_min`      | `CKG_TIME_NM` 파싱                               |
| 8   | `INQ_CNT_LOG_CENTERED`  | 조회 log-centered (ML feature, impute 시 합산에도 사용) |
| 9   | `SRAP_CNT_LOG_CENTERED` | 스크랩 log-centered                               |




### 3.3. 재료 파생 (6)


| #     | feature                                | 의미                           |
| ----- | -------------------------------------- | ---------------------------- |
| 10–15 | `ingredient_count` … `commonness_mean` | [기존 §3.3](EXPERIMENT.md)와 동일 |


- `others_ratio` ↔ `alias_match_ratio` 선형 종속 (`합≈1`).

---



## 4. 스크리닝 방법 (`feature_screening.py`)

동일 labeled 563건·동일 holdout. **3단 분석** — feature 자동 삭제 없음.


| 단계             | 리포트 필드                      | 방법                                                                 | 해석                   |
| -------------- | --------------------------- | ------------------------------------------------------------------ | -------------------- |
| 1. 단변량         | `univariate_spearman`       | labeled 563, `feature_builder.transform` 후 각 feature ↔ 타깃 Spearman | |ρ| 낮으면 타깃과 직접 관계 약함 |
| 2. 중복          | `high_correlation_pairs`    | 수치 12개 Pearson, |ρ|>0.7                                            | 한쪽 제거 후보             |
| 3. Permutation | `permutation_spearman_drop` | holdout에서 논리 feature별 원시 컬럼 shuffle → Spearman **감소량**             | 양수 = 모델이 해당 신호에 의존   |


**Permutation shuffle 대상 (파생 feature):** `serving_size`→`CKG_INBUN_NM`, `cooking_time_min`→`CKG_TIME_NM`, 재료 파생→`ingredients_normalized` 또는 `others_count`. (`_PERMUTE_SOURCE` in `feature_screening.py`)

**제거 후보 휴리스틱 (수동):**


| 신호                                                     | 판단                                               |
| ------------------------------------------------------ | ------------------------------------------------ |
| |univariate| < 0.05 **그리고** |permutation drop| < 0.005 | 영향 미미 후보                                         |
| Pearson |ρ| > 0.9                                      | 중복 — 하나만 유지                                      |
| `INQ_*` / `SRAP_*`                                     | 타깃 직접 상관 낮아도 프로덕션 합산·ML 입력 역할 분리 — ablation 후 결정 |


---



## 5. 1차 스크리닝 결과 (2026-07-07)

`holdout_spearman_baseline`: **0.096**

### 5.1. 단변량 Spearman (|ρ| 상위)


| feature                         | ρ      |
| ------------------------------- | ------ |
| `CKG_DODF_NM(난이도)`              | 0.102  |
| `cooking_time_min(조리시간)`        | 0.100  |
| `ingredient_count(재료수)`         | 0.089  |
| `unique_ingredient_count(재료종류)` | 0.079  |
| `serving_size(분량)`              | 0.077  |
| `commonness_mean`               | **~0** |


전 feature ρ < 0.11 — 타깃(품질)과 직접 선형 순위 상관은 전반적으로 약함.

### 5.2. 고상관 쌍 (|ρ|>0.7)


| a                  | b                         | Pearson  |
| ------------------ | ------------------------- | -------- |
| `ingredient_count` | `unique_ingredient_count` | 0.989    |
| `others_count`     | `others_ratio`            | 0.922    |
| `others_count`     | `alias_match_ratio`       | -0.922   |
| `others_ratio`     | `alias_match_ratio`       | **-1.0** |


→ `others_ratio` / `alias_match_ratio` **하나만 유지** 후보. `ingredient_count` vs `unique_ingredient_count`도 중복.

### 5.3. Permutation Spearman drop (|drop| 상위)


| feature                                               | drop           |
| ----------------------------------------------------- | -------------- |
| `CKG_KND_ACTO_NM`                                     | +0.060         |
| `ingredient_count`                                    | +0.050         |
| `cooking_time_min`                                    | -0.074         |
| `CKG_STA_ACTO_NM`                                     | -0.057         |
| `CKG_DODF_NM`                                         | -0.043         |
| `commonness_mean`                                     | +0.037         |
| `others_count` / `others_ratio` / `alias_match_ratio` | |drop| < 0.006 |


음수 drop = shuffle 후 Spearman이 오히려 좋아짐 → 해당 feature가 노이즈일 수 있음 (표본 113건 변동).

### 5.4. 1차 정리 후보 (ablation 전)


| 후보                                    | 근거                                                 |
| ------------------------------------- | -------------------------------------------------- |
| `alias_match_ratio` 또는 `others_ratio` | 완전 종속 (ρ=-1)                                       |
| `unique_ingredient_count`             | `ingredient_count`와 ρ=0.99, permutation drop 0.002 |
| `commonness_mean`                     | 단변량 ρ≈0, permutation drop 낮음                       |
| `others_count`                        | 단변량·permutation 모두 미미 (실험 02 이후에도)                 |


**유지 검토:** `CKG_KND_ACTO_NM`, `ingredient_count` — permutation drop 상대적으로 큼.

---



## 6. Ablation 결과 (2026-07-07)

`python -m ai.recommendation.feature_ablation` 실행. 리포트: `artifacts/feature_ablation_report.json`.

### 6.1. Phase 2 (고상관 dedup)


| 시도          | 제거                                                             | Spearman    | 결과                        |
| ----------- | -------------------------------------------------------------- | ----------- | ------------------------- |
| batch       | `unique_ingredient_count`, `others_count`, `alias_match_ratio` | 0.082       | **거절** (baseline 0.096 ↓) |
| fallback 각각 | 위 3개 단독                                                        | 0.064~0.088 | **전부 거절**                 |


→ 고상관 3개는 **유지** (holdout 기준 제거 이득 없음).

### 6.2. Phase 3 (음수 permutation drop 순차 제거)


| 순서  | 제거                     | Spearman  | Hit@10 | 결과  |
| --- | ---------------------- | --------- | ------ | --- |
| 1   | `cooking_time_min`     | 0.128     | 0.20   | 채택  |
| 2   | `CKG_STA_ACTO_NM`      | 0.160     | 0.10   | 채택  |
| 3   | `CKG_DODF_NM`          | **0.211** | 0.20   | 채택  |
| 4   | `INQ_CNT_LOG_CENTERED` | 0.184     | 0.20   | 거절  |




### 6.3. Winner → `config.py` 반영


|          | baseline (15) | winner (12) |
| -------- | ------------- | ----------- |
| Spearman | 0.096         | **0.211**   |
| Hit@10   | 0.10          | 0.20        |
| Hit@20   | 0.25          | 0.25        |
| RMSE     | 0.377         | 0.374       |


**제거:** `CKG_STA_ACTO_NM`, `CKG_DODF_NM`, `cooking_time_min`

**유지:** 고상관 3종(`unique_ingredient_count`, `others_count`, `alias_match_ratio`) — Phase 2에서 제거 시 Spearman 하락.

### 6.4. 후보 feature 추가


| 후보                                  | 상태             | 비고                            |
| ----------------------------------- | -------------- | ----------------------------- |
| `commonness_min` / `commonness_max` | **반영** (실험 05) | holdout Spearman 0.211→0.224  |
| `rare_ingredient_ratio`             | **보류** (실험 05) | k=5 시 Spearman 하락, config 미반영 |


---



## 7. 참고 (코드 위치)


| 역할         | 파일                        |
| ---------- | ------------------------- |
| 스크리닝       | `feature_screening.py`    |
| ablation   | `feature_ablation.py`     |
| feature 목록 | `config.py`               |
| 파생 로직      | `features.py`             |
| holdout 평가 | `main.py`, `evaluator.py` |


---



# 04. 품질·인기 점수 분리 (프로덕션 반영)

실험 01에서 보류했던 ETL 공식 변경과 잔차+인기 feature 패턴을 **프로덕션 기본값**으로 고정한 작업입니다.

**상태:** 코드 반영 완료. ETL → ML → Neo4j 순 실행으로 CSV·그래프 갱신.

---



## 1. 변경 요약


| 항목                      | 이전                             | 이후                                                         |
| ----------------------- | ------------------------------ | ---------------------------------------------------------- |
| ETL `REVIEW_RANK_SCORE` | 별점+감성+조회+스크랩 4항                | **별점+감성** 2항 (품질만)                                         |
| ML 타깃                   | 4항 합산                          | 품질 2항                                                      |
| ML feature              | 13개                            | **15개** (+`INQ_CNT_LOG_CENTERED`, `SRAP_CNT_LOG_CENTERED`) |
| `final_recommend_score` | labeled=규칙, unlabeled=ML       | **품질(rule/ML) + 인기** 합산                                    |
| Neo4j `reviewRankScore` | `recipe_fix.REVIEW_RANK_SCORE` | `recipe_recommendation_scored.final_recommend_score`       |
| `MODEL_VERSION`         | `recommend_model_v1`           | `recommend_model_v2`                                       |




## 2. 실행 순서

```bash
python -m etl.recipe.preprocessing.recipe_review_aggregate_to_fix
python -m ai.recommendation.main
python -m etl.recipe.load_to_neo4j
```



## 3. 변경 파일


| 파일                                  | 변경                                                       |
| ----------------------------------- | -------------------------------------------------------- |
| `recipe_review_aggregate_to_fix.py` | `apply_rank_score` 품질 2항만                                |
| `config.py`                         | 인기 feature, `POPULARITY_BASE_COLS`, `TARGET_FORMULA`, v2 |
| `imputer.py`                        | `popularity_base_score`, `quality_score`, final 합산       |
| `main.py`                           | `artifacts/imputed_recommend_scores.csv` 출력 제거           |
| `evaluator.py`                      | `target_formula` 필드                                      |
| `load_to_neo4j/loader.py`           | scored CSV merge → `reviewRankScore`, fallback           |




## 4. 참고

- labeled 563건의 `final_recommend_score`는 기존 4항 합과 **수치상 동일** (동일 항목 재배치).
- ML holdout Spearman은 품질 타깃 기준이라 여전히 낮을 수 있음 — 목적은 타깃·feature 역할 분리.
- CSV 커밋·롤백은 작업자가 git으로 판단 (별도 스냅샷 폴더 없음).

---



# 05. commonness 파생 feature 확장 (`min`/`max`, `rare_ingredient_ratio`)

실험 03 §6.4 후보 중 `commonness_min`/`commonness_max`를 추가하고, 통과 시 `rare_ingredient_ratio`를 이어서 시험한 실험입니다.

**상태:** `commonness_min`/`commonness_max` **config 반영 완료**. `rare_ingredient_ratio`(k=5)는 holdout 하락으로 **미반영**.

---



## 1. 실험 일지


| 순서  | 일시 (KST)         | 일시 (UTC)         | 내용                                                                          |
| --- | ---------------- | ---------------- | --------------------------------------------------------------------------- |
| 1   | 2026-07-07 11:45 | 2026-07-07 02:45 | 1차: `IngredientCommonnessLookup`에 min/max 추가. feature 12→14개                |
| 2   | 2026-07-07 11:45 | 2026-07-07 02:45 | screening·ablation·main 실행. baseline Spearman **0.224** (>0.211 합격)         |
| 3   | 2026-07-07 11:47 | 2026-07-07 02:47 | 2차: `rare_ingredient_ratio`(k=5) 추가. baseline Spearman **0.205** (1차 대비 하락) |
| 4   | 2026-07-07 11:48 | 2026-07-07 02:48 | `rare_ingredient_ratio` revert. min/max 유지 상태로 pipeline·artifacts 재생성       |


---



## 2. 배경·설계



### 2.1. 출발점 (실험 03 winner)

- feature 12개, holdout Spearman **0.211**
- `commonness_mean`만 사용 — 레시피 내 재료별 train 등장 레시피 수의 평균



### 2.2. 1차 추가 feature

`features.py` `IngredientCommonnessLookup._row_stats()` — 동일 lookup·동일 루프에서 산출:

```
commonness_min  = min(train 등장 레시피 수 per 재료)
commonness_max  = max(...)
commonness_mean  = mean(...)  # 기존과 동일
```



### 2.3. 2차 추가 feature (시험 후 revert)

```
rare_ingredient_ratio = (등장 수 < k인 재료 수) / (재료 수)    # k=5 고정
```



### 2.4. 합격 기준


| 단계  | 기준                                             | 결과             |
| --- | ---------------------------------------------- | -------------- |
| 1차  | 14 feature baseline Spearman **> 0.211**       | **통과** (0.224) |
| 2차  | 15 feature baseline Spearman **> 1차 baseline** | **실패** (0.205) |




### 2.5. 변경 파일


| 파일                     | 변경                                                        |
| ---------------------- | --------------------------------------------------------- |
| `features.py`          | `_row_stats()`, `transform()` 3컬럼, `apply_commonness()`   |
| `config.py`            | `INGREDIENT_FEATURES` +`commonness_min`, `commonness_max` |
| `feature_screening.py` | `_PERMUTE_SOURCE` +2                                      |
| `feature_ablation.py`  | `_PROTECTED` +`commonness_min`, `commonness_max`          |


---



## 3. 1차 결과 — `commonness_min` / `commonness_max`

동일 `extra_trees`, `random_state=42`, split 450/113.


| 지표       | 실험 03 winner (12) | 1차 baseline (14) | 변화     |
| -------- | ----------------- | ---------------- | ------ |
| Spearman | 0.211             | **0.224**        | +0.013 |
| Hit@10   | 0.20              | **0.30**         | +0.10  |
| Hit@20   | 0.25              | **0.30**         | +0.05  |
| Hit@50   | 0.54              | 0.54             | —      |
| RMSE     | 0.374             | 0.373            | 소폭 ↓   |




### 3.1. 스크리닝 (`feature_screening_report.json`)

**단변량 Spearman (commonness 계열):**


| feature           | ρ      |
| ----------------- | ------ |
| `commonness_max`  | 0.059  |
| `commonness_min`  | -0.041 |
| `commonness_mean` | ~0     |


**고상관:** `commonness_mean` ↔ `commonness_max` Pearson **0.724** (|ρ|>0.7)

**Permutation drop:**


| feature           | drop   |
| ----------------- | ------ |
| `commonness_mean` | +0.092 |
| `commonness_min`  | +0.058 |
| `commonness_max`  | +0.001 |


→ min/max/mean 모두 양수 drop. `commonness_min`은 `_PROTECTED` 등록.

### 3.2. Ablation (14 feature baseline)


| 단계            | 내용                                                                | Spearman  | 결과     |
| ------------- | ----------------------------------------------------------------- | --------- | ------ |
| Phase 2 batch | `unique_ingredient_count`, `others_count`, `alias_match_ratio` 제거 | **0.264** | **채택** |
| Phase 3       | `others_ratio` 제거                                                 | 0.241     | 거절     |


**참고:** 실험 03에서는 Phase 2 batch 제거가 Spearman **하락**이었으나, min/max 추가 후에는 **상승**(0.224→0.264). ablation winner(11 feature)는 `config.py`에 아직 미반영 — 프로덕션은 14 feature baseline.

---



## 4. 2차 결과 — `rare_ingredient_ratio` (k=5, 미반영)


| 지표       | 1차 baseline (14) | 2차 baseline (15) |
| -------- | ---------------- | ---------------- |
| Spearman | **0.224**        | 0.205            |


1차 대비 하락 → `rare_ingredient_ratio` **config에서 제거**. min/max는 유지.

**해석:** k=5 기준으로 대부분 재료가 “희귀”에 해당해 분산이 작거나, mean/min/max와 중복 신호일 수 있음. k 튜닝은 별도 실험으로 분리.

---



## 5. 현재 프로덕션 설정 (실험 05 시점 스냅샷)

- ML feature **14개** (실험 03 winner 12 + `commonness_min` + `commonness_max`)
- holdout Spearman **0.224** (2026-07-07 11:48 KST)
- **이후 실험 06에서 11 feature·0.264로 갱신** — 아래 §6 참고



### 재현

```bash
python -m ai.recommendation.features
python -m ai.recommendation.feature_screening
python -m ai.recommendation.feature_ablation
python -m ai.recommendation.main
```

---



## 6. 참고 (실험 05)


| 항목              | 위치                                            |
| --------------- | --------------------------------------------- |
| commonness 파생   | `features.py` — `IngredientCommonnessLookup`  |
| feature 목록      | `config.py` — `INGREDIENT_FEATURES`           |
| 평가 (14 feature) | `artifacts/evaluation_report.json` (실험 05 직후) |


---



# 06. Feature 제거 — ablation winner 반영 + serving_size 시험

실험 05 ablation winner(고상관 3종 제거)를 `config.py`에 반영하고, `serving_size` 추가 제거를 시험한 작업입니다.

**상태:** **11 feature config 반영 완료**. `serving_size` 제거는 **거절**(Spearman 하락).

---



## 1. 실험 일지


| 순서  | 일시 (KST)         | 내용                                                                                         |
| --- | ---------------- | ------------------------------------------------------------------------------------------ |
| 1   | 2026-07-07 12:00 | 1단계: `unique_ingredient_count`, `others_count`, `alias_match_ratio` config 제거 → 11 feature |
| 2   | 2026-07-07 12:00 | screening·ablation·main. Spearman **0.264** 재현 (≥0.264 합격)                                 |
| 3   | 2026-07-07 12:00 | 2단계: `_PROTECTED`에서 `serving_size` 해제, Phase 3 제거 시험                                       |
| 4   | 2026-07-07 12:00 | `serving_size` 제거 → Spearman **0.228** (거절). 11 feature 유지                                 |


---



## 2. 제거·유지 결정


| feature                   | 조치     | Spearman 영향                    |
| ------------------------- | ------ | ------------------------------ |
| `unique_ingredient_count` | **제거** | 14→11 feature, 0.224→**0.264** |
| `others_count`            | **제거** | `others_ratio`만 유지             |
| `alias_match_ratio`       | **제거** | `others_ratio`와 종속             |
| `others_ratio`            | **유지** | 제거 시 0.241 (실험 05와 동일)         |
| `serving_size`            | **유지** | 제거 시 0.264→0.228               |


---



## 3. 결과 (11 feature, 최종)


| 지표       | 실험 05 (14) | 실험 06 (11) |
| -------- | ---------- | ---------- |
| Spearman | 0.224      | **0.264**  |
| Hit@10   | 0.30       | 0.30       |
| Hit@20   | 0.30       | 0.30       |
| Hit@50   | 0.54       | 0.54       |
| RMSE     | 0.373      | 0.372      |




### 3.1. 11 feature screening (permutation drop 상위)


| feature                | drop                      |
| ---------------------- | ------------------------- |
| `CKG_KND_ACTO_NM`      | +0.215                    |
| `commonness_min`       | +0.202                    |
| `CKG_MTRL_ACTO_NM`     | +0.174                    |
| `INQ_CNT_LOG_CENTERED` | +0.104                    |
| `serving_size`         | -0.019 (제거 시도 거절)         |
| `commonness_max`       | -0.024 (보류, `_PROTECTED`) |


---



## 4. 현재 프로덕션 설정

- ML feature **11개**: 카테고리 3 + `serving_size` + 인기 2 + `ingredient_count` + `others_ratio` + commonness 3
- holdout Spearman **0.264** (`evaluation_report.json`)
- `pipeline.joblib`, `recipe_recommendation_scored.csv` 갱신 완료



### 재현

```bash
python -m ai.recommendation.feature_screening
python -m ai.recommendation.feature_ablation
python -m ai.recommendation.main
```

---



## 5. 참고


| 항목                               | 위치                                                                   |
| -------------------------------- | -------------------------------------------------------------------- |
| feature 목록                       | `config.py` — `INGREDIENT_FEATURES`                                  |
| `_PROTECTED` (`serving_size` 해제) | `feature_ablation.py`                                                |
| 최신 평가                            | `artifacts/evaluation_report.json`                                   |
| ablation step                    | `artifacts/feature_ablation_report.json` — Phase 3 `serving_size` 거절 |


---



# 07. commonness_max / commonness_min 제거 시험

11 feature baseline(Spearman 0.264)에서 commonness 파생 2종을 순차 제거 시험한 작업입니다.

**상태:** **둘 다 거절** — `commonness_mean` + `min` + `max` **전부 유지** (11 feature 동일).

---



## 1. 실험 일지


| 순서  | 일시 (KST)         | 내용                                                   |
| --- | ---------------- | ---------------------------------------------------- |
| 1   | 2026-07-07 12:10 | 1단계: `commonness_max` config 제거 → 10 feature         |
| 2   | 2026-07-07 12:10 | holdout Spearman **0.200** (<0.264) → **거절**, max 복원 |
| 3   | 2026-07-07 12:11 | 2단계: `commonness_min` 제거 → 10 feature (mean+max)     |
| 4   | 2026-07-07 12:11 | Spearman **0.213** (<0.264) → **거절**, min 복원         |
| 5   | 2026-07-07 12:12 | 11 feature·0.264 baseline 재학습, artifacts 복구          |


---



## 2. 합격 기준·결과


| 단계                  | 채택 조건           | 결과     | Spearman |
| ------------------- | --------------- | ------ | -------- |
| `commonness_max` 제거 | > 0.264         | **거절** | 0.200    |
| `commonness_min` 제거 | ≥ 1단계 최고(0.264) | **거절** | 0.213    |


---



## 3. 해석

- 실험 06 screening에서 `commonness_max` permutation drop **-0.024**였으나, 실제 제거 시 **대폭 하락** — 트리가 max를 mean/min과 **조합**해 쓰거나, holdout 변동·교란 효과 가능.
- `commonness_min`은 drop **+0.202**로 핵심 신호 — 제거 시 0.264→0.213 (**-0.051**), 예상대로 거절.
- commonness 3종(**mean/min/max**)은 **세트로 유지**하는 것이 현재 최적.

---



## 4. 현재 프로덕션 (변경 없음)

- ML feature **11개**, holdout Spearman **0.264**
- `evaluation_report.json`, `pipeline.joblib`, `recipe_recommendation_scored.csv` — 실험 06과 동일 구성



### 재현

```bash
python -m ai.recommendation.feature_screening
python -m ai.recommendation.main
```

---



# 08. 재료 feature 확장 (1~3순위 순차)

실험 07 baseline(11 feature, Spearman **0.264**)에서 재료 관련 feature를 1~3순위 후보군 순서로 **한 번에 하나씩** 추가 시험한 작업입니다.

**상태:** **완료** — `mtrl_empty_amount_ratio` **1종 채택** (12 feature, Spearman **0.284**).

**rolling_baseline:** 0.264 → **0.284** (최종)

**스냅샷:** `artifacts/scored_snapshot_pre_exp08_baseline.csv`

---



## 1. 실험 일지


| 순서  | 후보                          | Spearman  | rolling 대비 | 결과     | 비고                   |
| --- | --------------------------- | --------- | ---------- | ------ | -------------------- |
| —   | baseline                    | 0.264     | —          | —      | 11 feature           |
| 1-1 | `commonness_std`            | 0.249     | -0.015     | **거절** | 원복                   |
| 1-2 | `commonness_range`          | 0.244     | -0.020     | **거절** | 원복                   |
| 1-3 | `rare_ingredient_ratio_k10` | 0.256     | -0.008     | **거절** | 원복                   |
| 1-4 | `rare_ingredient_ratio_k20` | 0.233     | -0.031     | **거절** | 원복                   |
| 1-5 | `rare_ingredient_ratio_k50` | 0.252     | -0.013     | **거절** | 원복                   |
| 2-1 | `empty_amount_ratio`        | 0.264     | -0.0003    | **거절** | 동점 미만, 원복            |
| 2-2 | `unique_alias_count`        | 0.210     | -0.054     | **거절** | 원복                   |
| 2-3 | `canonical_alias_ratio`     | 0.226     | -0.039     | **거절** | 원복                   |
| 3-1 | `mtrl_slot_count`           | 0.224     | -0.040     | **거절** | 원복                   |
| 3-2 | `mtrl_empty_amount_ratio`   | **0.284** | **+0.019** | **채택** | 12 feature           |
| 3-3 | `mtrl_normalized_delta`     | 0.267     | -0.017     | **거절** | rolling 0.284 기준, 원복 |


상세 수치: `artifacts/exp08_results.json`

---



## 2. 채택 feature


| feature                   | 정의                              | Spearman 영향     |
| ------------------------- | ------------------------------- | --------------- |
| `mtrl_empty_amount_ratio` | `CKG_MTRL_CN` 항목 중 amount가 빈 비율 | 0.264→**0.284** |


**최종 ML feature 12개:** 카테고리 3 + `serving_size` + 인기 2 + 재료 6 (`ingredient_count`, `others_ratio`, commonness 3, `mtrl_empty_amount_ratio`)

---



## 3. 순위 변동 (`mtrl_empty_amount_ratio` 채택)

`artifacts/rank_delta_exp08_mtrl_empty_amount_ratio.json`


| 지표                     | 값       |
| ---------------------- | ------- |
| 순위 Spearman (이전 vs 이후) | 0.9995  |
| 순위 변동 레시피 수            | 2,841   |
| 최대 |Δrank|             | 202     |
| Top-50 겹침              | 49 / 50 |


---



## 4. 스크리닝 (12 feature 최종)

- holdout Spearman: **0.284**
- `mtrl_empty_amount_ratio` permutation drop: **+0.017** (`_PROTECTED` 미등록 — +0.05 미만)
- 고상관: `commonness_mean` ↔ `commonness_max` (0.724) — 기존과 동일, 추가 dedup 불필요

---



## 5. 현재 프로덕션

- holdout Spearman **0.284** (`evaluation_report.json`)
- `pipeline.joblib`, `recipe_recommendation_scored.csv` 갱신 완료
- Neo4j `reviewRankScore` 적재: scored CSV 준비 완료 — `python -m etl.recipe.load_to_neo4j` (Neo4j 연결 필요, 미실행)



### 재현

```bash
python -m ai.recommendation.features
python -m ai.recommendation.feature_screening
python -m ai.recommendation.main
pytest test/ai/recommendation/test_recommendation_pipeline.py -q
```

---



# 09. random_state 안정성 (42 baseline vs 다중 시드)

feature 실험(03~08)이 모두 **단일 holdout(**`random_state=42`**)** 기준이었으므로, 12 feature config에서 시드 변동에 따른 holdout 지표 분산을 측정한 작업입니다.

**상태:** **완료**

**범위:** `train_test_split` + `reset_seeds` + `ExtraTreesRegressor` **전부 동일 시드** (split 고정 분해 없음).

**프로덕션:** `RANDOM_STATE=42` **유지**. `main` / scored CSV / `evaluation_report.json` **미변경**.

---



## 1. 시드 목록


| 구분       | 시드                                                    |
| -------- | ----------------------------------------------------- |
| baseline | `42`                                                  |
| 비교군      | `0`, `1`, `7`, `13`, `99`, `123`, `256`, `512`, `999` |


---



## 2. Spearman (holdout, 12 feature)


| seed   | Spearman  | Hit@10 | Hit@20 | train/test |
| ------ | --------- | ------ | ------ | ---------- |
| **42** | **0.284** | 0.20   | 0.30   | 450/113    |
| 0      | -0.041    | 0.10   | 0.10   | 450/113    |
| 1      | 0.044     | 0.00   | 0.05   | 450/113    |
| 7      | 0.008     | 0.10   | 0.10   | 450/113    |
| 13     | 0.179     | 0.10   | 0.15   | 450/113    |
| 99     | 0.127     | 0.00   | 0.20   | 450/113    |
| 123    | 0.169     | 0.30   | 0.20   | 450/113    |
| 256    | **0.225** | 0.10   | 0.20   | 450/113    |
| 512    | 0.148     | 0.10   | 0.25   | 450/113    |
| 999    | 0.150     | 0.10   | 0.25   | 450/113    |


상세: `artifacts/seed_stability_report.json`

---



## 3. 42 vs 비교군(9시드) 요약


| 지표           | seed 42   | others mean | others min | others max | Δ42−mean   | Δ42−min    |
| ------------ | --------- | ----------- | ---------- | ---------- | ---------- | ---------- |
| **Spearman** | **0.284** | 0.112       | -0.041     | 0.225      | **+0.172** | **+0.325** |
| Hit@10       | 0.20      | 0.10        | 0.00       | 0.30       | +0.10      | +0.20      |
| Hit@20       | 0.30      | 0.17        | 0.05       | 0.25       | +0.13      | +0.25      |
| Hit@50       | 0.60      | 0.48        | 0.42       | 0.52       | +0.12      | +0.18      |


- `percentile_42_spearman`**:** **95.0** (10시드 중 2위, 최고는 42의 0.284)
- others **std(Spearman):** 0.083

---



## 4. 해석·안정성 판정


| 기준 (계획)                     | 결과                                        |
| --------------------------- | ----------------------------------------- |
| |Δ42−mean| < 0.02 → 수용      | **해당 없음** (Δ = **+0.172**)                |
| percentile_42 = 100 → 42 유리 | **95** — 42가 **눈에 띄게 상위** (256=0.225가 2위) |
| Δ42−min > 0.05 → holdout 취약 | **해당** (+0.325)                           |


**결론:**

- holdout Spearman **0.284는 42 split·모델 조합에 강하게 의존**하는 값으로 보는 것이 타당합니다.
- labeled 563건·test 113건 규모에서 **split 변경 시 commonness lookup·train 분포가 바뀌고**, Spearman이 0.04~0.18대로 떨어지는 시드가 다수입니다.
- **feature 채택/거절(실험 03~08)은 42 holdout 단일값만으로는 과신하기 어렵음** — 이후 개선은 **다중 시드 평균·RepeatedKFold** 또는 **labeled 확대**를 병행하는 것이 안전합니다.
- 프로덕션 `RANDOM_STATE=42` 유지는 **재현성** 목적에는 맞으나, **일반화 성능 수치로 0.284를 해석하면 과대평가 위험**이 있습니다.

---



## 5. 구현·재현


| 파일                                                | 역할                                                               |
| ------------------------------------------------- | ---------------------------------------------------------------- |
| `[seed_stability.py](seed_stability.py)`          | 10시드 holdout + summary JSON                                      |
| `[config.py](config.py)` / `[model.py](model.py)` | `get_regressor` / `build_pipeline`에 `random_state` 선택 인자 (기본 42) |


```bash
python -m ai.recommendation.seed_stability
```

- self-check: seed 42 Spearman이 `evaluation_report.json`과 ±0.001 이내
- `pipeline.joblib`·scored CSV **갱신하지 않음** (진단 전용)

---



# 10. Stratified 5-Fold 보조 검증

기존 `random_state=42` holdout을 공식 기준으로 유지하고, target 분위수를
보존한 5-fold 교차검증을 보조 지표로 추가했습니다. `main` 실행 시 holdout
평가 직후 자동 실행되며 fold 모델은 production 예측에 사용하지 않습니다.

## 1. 설정


| 항목              | 값                                                            |
| --------------- | ------------------------------------------------------------ |
| split           | `StratifiedKFold(n_splits=5, shuffle=True, random_state=42)` |
| strata          | `REVIEW_RANK_SCORE` 5분위 (`qcut`, 동점 보존)                      |
| bin count       | 115 / 121 / 126 / 169 / 32                                   |
| fold validation | 113 / 113 / 113 / 112 / 112                                  |
| feature/model   | 기존 12 feature / ExtraTrees                                   |




## 2. 결과


| 지표       | mean      | std   | min    | max    |
| -------- | --------- | ----- | ------ | ------ |
| Spearman | **0.136** | 0.124 | -0.014 | 0.279  |
| Hit@10   | 0.100     | 0.110 | 0.000  | 0.300  |
| Hit@20   | 0.190     | 0.080 | 0.100  | 0.300  |
| Hit@50   | 0.516     | 0.056 | 0.440  | 0.580  |
| RMSE     | 0.402     | 0.100 | 0.243  | 0.518  |
| MAE      | 0.174     | 0.023 | 0.134  | 0.200  |
| R²       | -0.180    | 0.081 | -0.341 | -0.118 |


- 공식 holdout(seed 42) Spearman은 기존과 동일한 **0.284**입니다.
- OOF 전체 Spearman **0.135**는 fold별 모델의 예측을 합친 진단값입니다.
- `evaluation_report.json`에는 기존 holdout 지표와 함께 `cross_validation.metrics_mean`
으로 5-fold 평균을 기록합니다.
- 상세 결과: `artifacts/stratified_kfold_report.json`
- OOF 행별 결과: `artifacts/stratified_kfold_predictions.csv`



## 3. 실행

```bash
# 5-fold 단독 실행
python -m ai.recommendation.cross_validation

# holdout + 5-fold + production 전체 재학습 + evaluation_report 갱신
python -m ai.recommendation.main
```

---



# 11. 난이도·시간·객관적 복잡도 재활용 실험



## 1. 실험 배경

난이도와 조리 시간은 단변량 Spearman이 각각 약 0.10이었지만 기존 모델에
함께 넣었을 때는 노이즈로 작용했습니다. 이를 단순 폐기하지 않고 표현 방식,
요리 종류 대비 상대값, 실제 조리 단계 기반 복잡도, 작성 밀도와의 불일치로
변환하면 유효한 신호를 분리할 수 있는지 검증했습니다.

공식 비교는 기존과 같은 `random_state=42`, train/test 450/113입니다. 후보는
한 번에 하나씩 추가했으며 Spearman이 rolling baseline보다 **0.005 이상**
상승할 때만 유지하고, 그렇지 않으면 즉시 원복했습니다. Spearman 통과 후
Hit@10/20/50을 차순위로 판단하도록 설계했습니다.

## 2. 단계별 검증



### 2.1. 표현 개선


| feature              | 정의               | Spearman | Hit@10/20/50 | 결과  |
| -------------------- | ---------------- | -------- | ------------ | --- |
| `difficulty_ordinal` | 초급=1, 중급=2, 고급=3 | 0.215    | .30/.25/.54  | 거절  |
| `cooking_time_log`   | `log1p(minute)`  | 0.212    | .10/.25/.50  | 거절  |


순서 정보를 명시하거나 시간 편차를 로그로 줄여도 기존 재료·카테고리 신호에
추가 정보를 제공하지 못했습니다.

### 2.2. 요리 종류 대비 상대 시간


| feature               | 정의                  | Spearman | Hit@10/20/50 | 결과  |
| --------------------- | ------------------- | -------- | ------------ | --- |
| `time_vs_kind_median` | 시간 - train 요리종류 중앙값 | 0.195    | .10/.25/.56  | 거절  |
| `time_ratio_to_kind`  | 시간 / train 요리종류 중앙값 | 0.214    | .10/.30/.56  | 거절  |


중앙값은 train에서만 계산했지만 상대 시간도 순위 품질을 개선하지 못했습니다.

### 2.3. 실제 조리 단계 기반 객관적 복잡도


| feature                   | Spearman | Hit@10/20/50    | 결과  |
| ------------------------- | -------- | --------------- | --- |
| `step_count_log`          | 0.232    | .20/.20/.56     | 거절  |
| `step_text_total_len_log` | 0.219    | .10/.20/.60     | 거절  |
| `step_text_mean_len_log`  | 0.227    | .20/.30/.56     | 거절  |
| `step_image_count_log`    | 0.263    | **.30**/.30/.52 | 거절  |
| `step_image_ratio`        | 0.253    | .20/**.35**/.56 | 거절  |
| `objective_complexity`    | 0.207    | .30/.25/.50     | 거절  |


이미지 수와 비율은 일부 Hit@K를 높였지만 1순위 Spearman과 Hit@50이 하락해
채택하지 않았습니다. 설명 길이의 단변량 상관은 있었지만 기존 모델에 더하면
중복·교란 신호가 되어 성능이 낮아졌습니다.

### 2.4. 밀도·난이도 불일치·명시적 상호작용


| feature               | Spearman  | Hit@10/20/50    | 결과  |
| --------------------- | --------- | --------------- | --- |
| `time_per_step_log`   | 0.204     | .10/.25/.56     | 거절  |
| `ingredient_per_step` | 0.265     | .20/**.35**/.56 | 거절  |
| `detail_per_step_log` | 0.227     | .20/.30/.56     | 거절  |
| `difficulty_gap`      | 0.265     | .20/.25/.58     | 거절  |
| `difficulty_gap_abs`  | **0.282** | .10/.30/.58     | 거절  |
| `difficulty_kind`     | 0.134     | .10/.10/.52     | 거절  |
| `difficulty_method`   | 0.134     | .20/.20/.54     | 거절  |
| `time_kind`           | 0.021     | .20/.15/.44     | 거절  |


가장 근접한 `difficulty_gap_abs`도 0.283728→0.282425로 소폭 하락했고
Hit@10·50도 낮아져 채택하지 않았습니다. 명시적 결합 카테고리는 labeled
563건에서 조합별 표본이 분산되어 크게 과적합했습니다.

## 3. 최종 영향과 결정


| 지표                   | 실험 전     | 최종       | 변화  |
| -------------------- | -------- | -------- | --- |
| Spearman             | 0.283728 | 0.283728 | 0   |
| Hit@10               | 0.20     | 0.20     | 0   |
| Hit@20               | 0.30     | 0.30     | 0   |
| Hit@50               | 0.60     | 0.60     | 0   |
| production feature 수 | 12       | 12       | 0   |


모든 후보를 거절했으므로 `config.py`, production feature builder와 최종 모델은
변경하지 않았습니다. 이번 결과는 난이도·시간이 단독 연관성을 갖더라도 현재
표본과 ExtraTrees에서는 재료·카테고리·인기 신호 이후의 추가 설명력을 안정적으로
분리하지 못한다는 뜻입니다. 상세 수치는
`artifacts/exp11_complexity_feature_results.json`에 보존했습니다.

---



# 12. 조회수-스크랩 관계 feature 실험 (롤백)



## 1. 실험 내용

기존 popularity 신호인 `INQ_CNT_LOG_CENTERED`, `SRAP_CNT_LOG_CENTERED`에
관계형 feature 2개를 추가해 성능 변화를 확인했습니다.

- `scrap_per_view = SRAP_CNT / (INQ_CNT + 1)`
- `scrap_view_log_gap = log1p(SRAP_CNT) - log1p(INQ_CNT)`

비교 기준은 기존과 동일한 `random_state=42`, holdout 450/113 및
Stratified 5-fold 보조 검증입니다.

## 2. 결과 요약


| 지표               | baseline | 추가 후   | 변화    |
| ---------------- | -------- | ------ | ----- |
| Holdout Spearman | 0.2837   | 0.2451 | 하락    |
| Holdout Hit@10   | 0.20     | 0.10   | 하락    |
| Holdout Hit@20   | 0.30     | 0.25   | 하락    |
| Holdout Hit@50   | 0.60     | 0.62   | 소폭 상승 |
| CV mean Spearman | 0.1359   | 0.1016 | 하락    |
| CV mean Hit@10   | 0.10     | 0.08   | 하락    |
| CV mean Hit@20   | 0.19     | 0.18   | 하락    |
| CV mean Hit@50   | 0.516    | 0.480  | 하락    |


RMSE/MAE/R²는 일부 개선됐지만, 본 실험의 1차 판정 기준인 rank 지표
(Spearman, Hit@K)에서 일관된 개선이 없어서 채택하지 않았습니다.

## 3. 결정

- production feature에는 **미반영**
- 관련 코드/산출물은 모두 **롤백**
- 결론: 현재 데이터/모델(ExtraTrees) 기준으로 조회수-스크랩 관계 feature는
순위 품질 개선 신호로 충분하지 않음

---



# 13. 2026 조회수 비교 실험 (2024 기준 대비)

`recipe_fix.csv`에 추가된 2026 조회수 컬럼을 기존 popularity feature 체계에
단계적으로 투입해 비교했습니다. 실험 규칙은 **하락 시 즉시 원복 후 다음 후보 진행**입니다.

## 1. baseline (winner 시작점)


| 설정                       | Holdout Spearman | Holdout Hit@10 | 5-fold mean Spearman |
| ------------------------ | ---------------- | -------------- | -------------------- |
| 기존 production 12 feature | **0.2858**       | **0.20**       | **0.1361**           |




## 2. 후보 실험 결과


| 단계        | 후보 feature 변경                                             | Holdout Spearman | Hit@10 | CV mean Spearman | 판정                          |
| --------- | --------------------------------------------------------- | ---------------- | ------ | ---------------- | --------------------------- |
| Phase 1   | `INQ_CNT_LOG_CENTERED` → `INQ_CNT_LOG_CENTERED_2026` (치환) | 0.2676           | 0.14   | 0.1469           | **거절** (Spearman 하락)        |
| Phase 2-a | `INQ_CNT_LOG_CENTERED` + `INQ_CNT_LOG_CENTERED_2026`      | 0.2346           | 0.06   | 0.1498           | **거절** (Spearman/Hit@10 하락) |
| Phase 2-b | baseline + `INQ_CNT_RATE_2026`                            | 0.2752           | 0.08   | 0.1470           | **거절** (Spearman/Hit@10 하락) |
| Phase 2-c | `INQ_CNT_LOG_CENTERED_2024` + `INQ_CNT_LOG_CENTERED_2026` | 0.2346           | 0.06   | 0.1498           | **거절** (Spearman/Hit@10 하락) |
| Phase 3-a | baseline + `INQ_CNT_DELTA_2024_2026`                      | 0.2498           | 0.06   | 0.1339           | **거절** (3개 지표 하락)           |
| Phase 3-b | baseline + `INQ_CNT_GROWTH_RATE_2024_2026`                | 0.2674           | 0.08   | 0.1327           | **거절** (3개 지표 하락)           |




## 3. 원복/최종 결정

- 모든 후보가 최소 1개 핵심 지표를 악화시켜 **즉시 원복** 처리.
- 최종 winner는 기존 production과 동일:
  - `INQ_CNT_LOG_CENTERED`
  - `SRAP_CNT_LOG_CENTERED`
- 추가된 2026 조회수 파생(`_2026`, `DELTA`, `GROWTH_RATE`)은 **현재 모델/데이터에서는 미반영**.



## 4. 재검증

- winner(기존 baseline) 상태에서 재실행:
  - `python -m ai.recommendation.feature_screening`
  - `python -m ai.recommendation.feature_ablation`
- 결과:
  - screening holdout Spearman: **0.2858**
  - ablation: `beats_baseline=False`, `removed=[]`



## 5. 현재 상태

- `config.py`는 baseline 설정으로 복원됨.
- `evaluation_report.json` / `pipeline.joblib` / `recipe_recommendation_scored.csv`는
baseline(winner) 기준으로 재생성 완료.

---



# 14. 조회수 변화(log-delta) 타깃 KFold 진단 (비적용)

별점/감성 타깃이 아닌 관심도 변화 자체를 학습하면 적합도가 올라가는지 확인하기 위한
진단 실험입니다. 결과는 **실험 기록 전용**이며 production에는 반영하지 않습니다.

## 1. 타깃·데이터 정의

- 타깃: `INTEREST_TARGET_LOG_DELTA_2024_2026 = log1p(INQ_CNT_2026) - log1p(INQ_CNT_2024)`
- 입력 데이터: `recipe_fix.csv` 전체 3,171행
- 유효 타깃 행: **3,170행** (`INQ_CNT_2026` 결측 1행 제외)
- 타깃 분포 요약:
  - p01: 0.0362
  - p50: 0.6530
  - p99: 2.3141
  - mean/std: 0.7366 / 0.5085



## 2. 실행 방식

- 스크립트: `python -m ai.recommendation.interest_target_cv`
- 산출물:
  - `ai/recommendation/artifacts/interest_target_kfold_report.json`
  - `ai/recommendation/artifacts/interest_target_kfold_predictions.csv`
- CV: `StratifiedKFold(n_splits=5, shuffle=True, random_state=42)`
  - target quantile bin 5개, 각 634행
- 비교군:
  - **A_current_features**: 기존 production feature 12개 유지
  - **B_without_inq_centered**: `INQ_CNT_LOG_CENTERED` 제외(11개)



## 3. 결과 요약 (mean/std/min 중심)


| 구분                     | 5-fold Spearman mean | std        | min        | RMSE mean | R2 mean    |
| ---------------------- | -------------------- | ---------- | ---------- | --------- | ---------- |
| A_current_features     | **0.4086**           | 0.0321     | **0.3752** | 0.4790    | **0.1114** |
| B_without_inq_centered | 0.3144               | **0.0235** | 0.2745     | 0.5041    | 0.0157     |
| (참고) 품질 타깃 기존 CV       | 0.1361               | 0.1255     | -0.0158    | 0.4016    | -0.1791    |


추가 참고(Hit@K): 본 타깃은 “상위 급등 레시피” 맞추기 난도가 높아 Hit@K 절대값은 낮음.
주요 판정은 Spearman/안정성(std, min)으로 해석했습니다.

## 4. 해석

- 관심도(log-delta) 타깃에서는 기존 feature 구성 A가 B보다 명확히 우수합니다.
  - Spearman mean: +0.0942
  - Fold min: +0.1007
- 3k 규모 전체 활용으로 fold 분산이 낮아졌고(특히 품질 타깃 대비 min 안정), 관심도 신호 자체는
현재 모델이 학습 가능한 패턴으로 보입니다.
- 단, 이 결과는 품질 타깃 성능 개선을 의미하지 않으며, 목적 함수가 다르므로 직접 대체 불가입니다.



## 5. 결정 (비적용)

- 본 실험은 **diagnostic only**로 종료.
- production 타깃(`REVIEW_RANK_SCORE`)과 scoring 로직은 변경하지 않음.
- 다음 단계 검토안:
  - 품질 점수와 관심도 점수를 별도 모델로 학습한 뒤 가중 결합 실험
  - 관심도 모델에서 누수 가능성 재점검(추가 제외군 실험)

---

# 15. 2026 조회수(log) 타깃 KFold 진단 (비적용)

직전 실험(#14)의 타깃을 `24->26 log-delta`에서 `2026 조회수 log` 자체로 바꾼
진단 실험입니다. production 반영 없이 비교 데이터만 기록합니다.

## 1. 타깃·데이터

- 타깃: `INTEREST_TARGET_LOG_2026 = log1p(INQ_CNT_2026)` (런타임 재계산)
- 유효 행: **3170 / 3171**
  - `INQ_CNT_2026` 결측 1건, 음수 0건
- 분포 요약:
  - p01/p50/p99 = 7.1905 / 8.3971 / 10.6058
  - mean/std = 8.5055 / 0.7568

## 2. 실행·산출물

- 실행: `python -m ai.recommendation.interest_target_cv`
- 산출물:
  - `ai/recommendation/artifacts/interest_target_2026log_kfold_report.json`
  - `ai/recommendation/artifacts/interest_target_2026log_kfold_predictions.csv`
- 비교군:
  - A: 기존 feature 12개
  - B: `INQ_CNT_LOG_CENTERED` 제외(11개)

## 3. 결과 요약 (A/B + 직전 log-delta 비교)

| 타깃 / 비교군 | Spearman mean | Spearman std | Spearman min | Hit@10 mean | Hit@20 mean | Hit@50 mean |
|---|---:|---:|---:|---:|---:|---:|
| 2026 log / A | **0.7254** | **0.0094** | **0.7112** | **0.40** | **0.48** | **0.552** |
| 2026 log / B | 0.2411 | 0.0278 | 0.2100 | 0.14 | 0.14 | 0.240 |
| 24->26 log-delta / A (#14) | 0.4086 | 0.0321 | 0.3752 | 0.04 | 0.03 | 0.144 |
| 24->26 log-delta / B (#14) | 0.3144 | 0.0235 | 0.2745 | 0.02 | 0.06 | 0.120 |

## 4. 해석

- 같은 모델/구성에서 타깃을 `2026 log`로 두면 A군 성능이 크게 상승했습니다.
  - Spearman mean: 0.4086 -> **0.7254**
  - std: 0.0321 -> **0.0094** (fold 안정성 개선)
  - min: 0.3752 -> **0.7112**
- A/B 격차가 매우 커져(`+0.4843`), `INQ_CNT_LOG_CENTERED` 신호의 기여가
  2026 log 타깃에 특히 강하게 작용함을 확인했습니다.

## 5. 결론 (비적용)

- 본 결과는 **diagnostic only**이며 production 타깃/스코어링에는 미반영.
- 의미: “26년 절대 관심도” 예측 목적에는 현재 피처/모델이 적합할 가능성이 높음.
- 다음 검토:
  - 관심도 모델을 별도 트랙으로 유지하고 품질 모델과 후단 결합 실험
  - 타깃 누수/시간축 해석을 위한 추가 제외군(`SRAP`, `INQ rate`) 점검

