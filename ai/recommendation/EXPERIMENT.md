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

# 02. 재료 전처리 수정 — others 재매칭·기본재료 분리

`recipe_ingredient_alias.csv`의 `others_count` / `others_ratio` feature가 왜곡되지 않도록, alias 카탈로그 갱신분 반영과 기본재료(물) 분리를 **LLM 재실행 없이** 오프라인 보정한 작업입니다.

**상태:** 전처리·CSV·Neo4j·ML 배치 **반영 완료**. 본 수정은 feature 스케일만 바꾸며 모델·split·feature 개수는 동일(13개).

---

## 1. 작업 일지

| 순서 | 일시 (KST) | 내용 |
|------|------------|------|
| 1 | 2026-07-07 — | `nodes_alias.csv` 확장분(버터·피망·양송이버섯 등) 대비 `--rematch-others` 실행. 1,460행·2,078건 승격 |
| 2 | 2026-07-07 — | 기본재료 `물`을 `others_items` → `basic_items` 분리 (`--extract-basic`). 981행·1,050건 이동 |
| 3 | 2026-07-07 — | Neo4j `basicItems` 속성 적재, `python -m ai.recommendation.main` 재실행 |

---

## 2. 배경

- **others 재매칭:** 초기 LLM 배치 시 `nodes_alias.csv`에 없던 재료가 `others_items`에 남음. 이후 alias 추가 후에도 CSV는 갱신되지 않은 상태.
- **기본재료 분리:** 런타임은 `recommend_config` + `basic_ingredient_normalized()`로 `물`을 항상 보유 처리(`52`). ETL 산출물에는 물이 others에 ~1,050건 포함되어 `others_count` feature가 과대 계상됨.

---

## 3. 전처리 변경 요약

| 단계 | CLI | 입력·규칙 | 결과 |
|------|-----|-----------|------|
| alias 승격 | `--rematch-others` | `others_items[].name` ↔ `nodes_alias.name` **exact key** (`_match_key`) | `aliases_matched` 추가, others 감소 |
| 기본재료 분리 | `--extract-basic` | `is_basic_ingredient(name\|raw)` — `recommend_config`와 동일 | `basic_items` / `basic_count` 신설, others에서 제거 |

**스키마 추가:** `basic_items` (JSON), `basic_count` (int). `ingredients_normalized`에는 물 유지.

**판정 예 (물):** `물`, `물 1200ml` → basic · `뜨거운 물`, `계란물` → others 유지 (suffix 규칙 비활성).

**구현:** `etl/recipe/preprocessing_by_llm/normalize_recipe_ingredients_by_llm.py` — `assemble_result()` 생성 시 분기 + 기존 CSV 마이그레이션 CLI.

---

## 4. CSV 집계 변화

| 지표 | LLM 초기 (대략) | rematch 후 | basic 분리 후 |
|------|-----------------|------------|---------------|
| others 항목 합계 | 3,885 | ~1,807 | **757** |
| basic 항목 합계 | — | — | **1,050** |
| `others_count > 0` 레시피 | 2,179 | 1,380 | (동일) |

검증 샘플 `RCP_SNO=7016816`: 물 → `basic_items`, `others_count=0`.

---

## 5. ML holdout 지표 변화 (`extra_trees`, feature 13개, split 동일)

동일 `random_state=42`, 타깃·모델 변경 없음. **재료 파생 4개(`others_count`, `others_ratio`, `alias_match_ratio`, 간접 `commonness`) 입력값만 변화.**

| 시점 | RMSE | Spearman | Hit@10 | Hit@20 | Hit@50 |
|------|------|----------|--------|--------|--------|
| 베이스라인 (2026-07-06, 전처리 전) | 2.02 | 0.131 | 0.20 | 0.25 | 0.50 |
| alias rematch 후 | 2.04 | 0.140 | — | — | — |
| basic 분리 후 (2026-07-07) | **2.07** | **0.145** | 0.10 | 0.20 | 0.48 |

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

| 항목 | 위치 |
|------|------|
| 기본재료 판정 (공유) | `recommend_config.py` — `basic_ingredient_normalized`, `is_basic_ingredient` |
| ETL·CLI | `normalize_recipe_ingredients_by_llm.py` |
| Neo4j | `load_to_neo4j/loader.py` — `basicItems` |
| ideaVault | `54_recipe_ingredient_alias_rematch_basic.md`, `52_basic_ingredient.md` (ETL 확장) |

---

# 03. Feature 스크리닝 (영향도·중복·제거 후보)

v2 파이프라인(**15 feature**, 품질 2항 타깃)에서 **영향 미미·중복 feature**를 찾아 정리하기 위한 실험입니다.

**상태:** 사전 스크리닝 **구현·1차 실행 완료** (`feature_screening.py`). feature 삭제·ablation은 리포트 검토 후 수동.

---

## 1. 실험 일지

| 순서 | 일시 (KST) | 내용 |
|------|------------|------|
| 1 | 2026-07-07 — | 실험 03 착수. feature 13개 목록·산출 정리 (당시 v1 기준) |
| 2 | 2026-07-07 — | 실험 02 선행 완료 — `others_count` 정리, v1 Spearman 0.145 |
| 3 | 2026-07-07 — | 실험 04 — v2(15 feature, 품질 타깃). holdout Spearman **0.096** |
| 4 | 2026-07-07 — | `feature_screening.py` 추가·실행. `feature_screening_report.json` 생성 |
| 5 | (예정) | 제거 후보 ablation → `evaluation_report.json` 비교 |

---

## 2. 분석 설정 (v2 현재)

| 항목 | 값 |
|------|-----|
| 타깃 | `REVIEW_RANK_SCORE` = `REVIEW_STAR_NORM_AVG + REVIEW_SENTIMENT_AVG` (품질 2항) |
| 모델 | `extra_trees` (`n_estimators=300`, `random_state=42`) |
| split | `train_test_split` 0.2 → train 450 / test 113 |
| feature 수 | **15** (카테고리 5 + 수치 4 + 재료 6) |
| holdout Spearman | **0.096** (`evaluation_report.json`, 2026-07-07) |
| 스크리닝 CLI | `python -m ai.recommendation.feature_screening` |
| 출력 | `artifacts/feature_screening_report.json` |

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

| # | feature | 의미 |
|---|---------|------|
| 1–5 | `CKG_KND_ACTO_NM` … `CKG_DODF_NM` | 요리 종류·방법·상황·주재료·난이도 |

### 3.2. 메타·인기 수치 (4)

| # | feature | 의미 |
|---|---------|------|
| 6 | `serving_size` | `CKG_INBUN_NM` 파싱 |
| 7 | `cooking_time_min` | `CKG_TIME_NM` 파싱 |
| 8 | `INQ_CNT_LOG_CENTERED` | 조회 log-centered (ML feature, impute 시 합산에도 사용) |
| 9 | `SRAP_CNT_LOG_CENTERED` | 스크랩 log-centered |

### 3.3. 재료 파생 (6)

| # | feature | 의미 |
|---|---------|------|
| 10–15 | `ingredient_count` … `commonness_mean` | [기존 §3.3](EXPERIMENT.md)와 동일 |

- `others_ratio` ↔ `alias_match_ratio` 선형 종속 (`합≈1`).

---

## 4. 스크리닝 방법 (`feature_screening.py`)

동일 labeled 563건·동일 holdout. **3단 분석** — feature 자동 삭제 없음.

| 단계 | 리포트 필드 | 방법 | 해석 |
|------|-------------|------|------|
| 1. 단변량 | `univariate_spearman` | labeled 563, `feature_builder.transform` 후 각 feature ↔ 타깃 Spearman | \|ρ\| 낮으면 타깃과 직접 관계 약함 |
| 2. 중복 | `high_correlation_pairs` | 수치 12개 Pearson, \|ρ\|>0.7 | 한쪽 제거 후보 |
| 3. Permutation | `permutation_spearman_drop` | holdout에서 논리 feature별 원시 컬럼 shuffle → Spearman **감소량** | 양수 = 모델이 해당 신호에 의존 |

**Permutation shuffle 대상 (파생 feature):** `serving_size`→`CKG_INBUN_NM`, `cooking_time_min`→`CKG_TIME_NM`, 재료 파생→`ingredients_normalized` 또는 `others_count`. (`_PERMUTE_SOURCE` in `feature_screening.py`)

**제거 후보 휴리스틱 (수동):**

| 신호 | 판단 |
|------|------|
| \|univariate\| < 0.05 **그리고** \|permutation drop\| < 0.005 | 영향 미미 후보 |
| Pearson \|ρ\| > 0.9 | 중복 — 하나만 유지 |
| `INQ_*` / `SRAP_*` | 타깃 직접 상관 낮아도 프로덕션 합산·ML 입력 역할 분리 — ablation 후 결정 |

---

## 5. 1차 스크리닝 결과 (2026-07-07)

`holdout_spearman_baseline`: **0.096**

### 5.1. 단변량 Spearman (|ρ| 상위)

| feature | ρ |
|---------|---|
| `CKG_DODF_NM(난이도)` | 0.102 |
| `cooking_time_min(조리시간)` | 0.100 |
| `ingredient_count(재료수)` | 0.089 |
| `unique_ingredient_count(재료종류)` | 0.079 |
| `serving_size(분량)` | 0.077 |
| `commonness_mean` | **~0** |

전 feature \|ρ\| < 0.11 — 타깃(품질)과 직접 선형 순위 상관은 전반적으로 약함.

### 5.2. 고상관 쌍 (|ρ|>0.7)

| a | b | Pearson |
|---|---|---------|
| `ingredient_count` | `unique_ingredient_count` | 0.989 |
| `others_count` | `others_ratio` | 0.922 |
| `others_count` | `alias_match_ratio` | -0.922 |
| `others_ratio` | `alias_match_ratio` | **-1.0** |

→ `others_ratio` / `alias_match_ratio` **하나만 유지** 후보. `ingredient_count` vs `unique_ingredient_count`도 중복.

### 5.3. Permutation Spearman drop (|drop| 상위)

| feature | drop |
|---------|------|
| `CKG_KND_ACTO_NM` | +0.060 |
| `ingredient_count` | +0.050 |
| `cooking_time_min` | -0.074 |
| `CKG_STA_ACTO_NM` | -0.057 |
| `CKG_DODF_NM` | -0.043 |
| `commonness_mean` | +0.037 |
| `others_count` / `others_ratio` / `alias_match_ratio` | \|drop\| < 0.006 |

음수 drop = shuffle 후 Spearman이 오히려 좋아짐 → 해당 feature가 노이즈일 수 있음 (표본 113건 변동).

### 5.4. 1차 정리 후보 (ablation 전)

| 후보 | 근거 |
|------|------|
| `alias_match_ratio` 또는 `others_ratio` | 완전 종속 (ρ=-1) |
| `unique_ingredient_count` | `ingredient_count`와 ρ=0.99, permutation drop 0.002 |
| `commonness_mean` | 단변량 ρ≈0, permutation drop 낮음 |
| `others_count` | 단변량·permutation 모두 미미 (실험 02 이후에도) |

**유지 검토:** `CKG_KND_ACTO_NM`, `ingredient_count` — permutation drop 상대적으로 큼.

---

## 6. 다음 절차 (ablation)

1. 위 후보 1~2개씩 `config.py`에서 제거.
2. `python -m ai.recommendation.main` 재실행.
3. `evaluation_report.json` Spearman·Hit@K 비교 — 개선 없으면 되돌림.

### 6.1. 후보 feature 추가 (미구현)

| 후보 | 산출(안) |
|------|----------|
| `commonness_min` / `commonness_max` | 레시피 내 재료 등장 수 min/max |
| `rare_ingredient_ratio` | train 등장 수 < k 비율 |

---

## 7. 참고 (코드 위치)

| 역할 | 파일 |
|------|------|
| 스크리닝 | `feature_screening.py` |
| feature 목록 | `config.py` |
| 파생 로직 | `features.py` |
| holdout 평가 | `main.py`, `evaluator.py` |

---

# 04. 품질·인기 점수 분리 (프로덕션 반영)

실험 01에서 보류했던 ETL 공식 변경과 잔차+인기 feature 패턴을 **프로덕션 기본값**으로 고정한 작업입니다.

**상태:** 코드 반영 완료. ETL → ML → Neo4j 순 실행으로 CSV·그래프 갱신.

---

## 1. 변경 요약

| 항목 | 이전 | 이후 |
|------|------|------|
| ETL `REVIEW_RANK_SCORE` | 별점+감성+조회+스크랩 4항 | **별점+감성** 2항 (품질만) |
| ML 타깃 | 4항 합산 | 품질 2항 |
| ML feature | 13개 | **15개** (+`INQ_CNT_LOG_CENTERED`, `SRAP_CNT_LOG_CENTERED`) |
| `final_recommend_score` | labeled=규칙, unlabeled=ML | **품질(rule/ML) + 인기** 합산 |
| Neo4j `reviewRankScore` | `recipe_fix.REVIEW_RANK_SCORE` | `recipe_recommendation_scored.final_recommend_score` |
| `MODEL_VERSION` | `recommend_model_v1` | `recommend_model_v2` |

## 2. 실행 순서

```bash
python -m etl.recipe.preprocessing.recipe_review_aggregate_to_fix
python -m ai.recommendation.main
python -m etl.recipe.load_to_neo4j
```

## 3. 변경 파일

| 파일 | 변경 |
|------|------|
| `recipe_review_aggregate_to_fix.py` | `apply_rank_score` 품질 2항만 |
| `config.py` | 인기 feature, `POPULARITY_BASE_COLS`, `TARGET_FORMULA`, v2 |
| `imputer.py` | `popularity_base_score`, `quality_score`, final 합산 |
| `main.py` | `artifacts/imputed_recommend_scores.csv` 출력 제거 |
| `evaluator.py` | `target_formula` 필드 |
| `load_to_neo4j/loader.py` | scored CSV merge → `reviewRankScore`, fallback |

## 4. 참고

- labeled 563건의 `final_recommend_score`는 기존 4항 합과 **수치상 동일** (동일 항목 재배치).
- ML holdout Spearman은 품질 타깃 기준이라 여전히 낮을 수 있음 — 목적은 타깃·feature 역할 분리.
- CSV 커밋·롤백은 작업자가 git으로 판단 (별도 스냅샷 폴더 없음).
