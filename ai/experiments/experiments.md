# LightFM 실험 기록

## 실험 1 — `star_sentiment_sum` + WARP (100 epoch)

**일자:** 2026-07-09  
**노트북:** `LightFM_Model.ipynb` (Docker JupyterLab)  
**목적:** 기본 파이프라인 동작 확인 + `star_sentiment_sum` interaction target의 오프라인 성능 1차 측정

### 설정

| 항목 | 값 |
|------|-----|
| interaction target | `star_sentiment_sum` (`star` + `sentiment`, 연속값) |
| loss | `warp` |
| seed | 42 |
| train/test split | 0.8 / 0.2 (`random_train_test_split`) |
| epochs | 100 |
| num_threads | 2 |
| Go/No-Go 기준 | test `precision@5 >= 0.05` |

**데이터**

| 항목 | 값 |
|------|-----|
| users | 821 |
| items | 563 |
| interactions (nnz) | 990 |
| train nnz | 792 |
| test nnz | 198 |
| density | 0.21% |

### 결과

#### Test set (Unit 8 — 최종 평가)

| 지표 | 값 |
|------|-----|
| precision@5 | 0.0079 |
| precision@10 | 0.0056 |
| recall@5 | 0.0365 |
| recall@10 | 0.0506 |

**판정:** No-Go (`precision@5` 0.0079 < 0.05)

#### Train set (Unit 7 — epoch별 모니터링)

Unit 7은 **train** matrix 기준 `precision@5`를 출력한다.

| 구간 | train precision@5 |
|------|-------------------|
| epoch 1 | ~0.01 |
| epoch 50 전후 | 상승 추세 |
| epoch 89~99 | **0.2227** (수렴·정체) |
| epoch 100 | 0.2224 |

→ train 지표는 0.22까지 올라가지만, **test 지표는 0.008 수준**으로 큰 격차가 있음.

### 해석

1. **과적합 의심:** 100 epoch에서 train precision@5는 0.22대에 수렴했으나 test precision@5는 0.008 미만. epoch를 늘린 효과는 train memorization에 가깝다.
2. **loss/target 불일치:** `warp`는 암묵적 피드백(이진 positive)용인데, interaction은 연속값(`star + sentiment`). 설계 문서 §4.1 기준으로 Binary target + warp 조합이 더 정합적이다.
3. **데이터 희소성:** 821 users × 563 items, density 0.21% — CF 신호가 약해 일반화가 어렵다.
4. **모니터링 지표 한계:** Unit 7의 epoch 로그는 train 기준이라, 수렴처럼 보여도 test 성능과 무관할 수 있다.

### 원본 리포트 (Unit 9)

```json
{
  "target_mode": "star_sentiment_sum",
  "seed": 42,
  "test_ratio": 0.2,
  "epochs": 100,
  "loss": "warp",
  "matrix": {
    "num_users": 821,
    "num_items": 563,
    "nnz": 990,
    "train_nnz": 792,
    "test_nnz": 198
  },
  "metrics": {
    "precision@5": 0.00786516908556223,
    "precision@10": 0.00561797758564353,
    "recall@5": 0.03651685393258427,
    "recall@10": 0.05056179775280899
  },
  "decision": {
    "go": false,
    "criterion": "precision@5 >= 0.05"
  }
}
```

### 다음 실험 (실험 1 후속)

설계 문서의 interaction target 비교를 이어서 진행한다.

| 우선순위 | 내용 |
|----------|------|
| 1 | **Binary(1)** + `warp` — loss/target 정합성 확인 |
| 2 | epoch 수 축소(30~50) + **test** precision 모니터링 |
| 3 | `sentiment` only / `star` only / `star_norm` 비교 |
| 4 | Unit 10 baseline(인기 기반) 대비 비교 |


---

## 실험 2 — interaction 가중치·epoch 비교

**일자:** 2026-07-09  
**노트북:** `LightFM_Model.ipynb` (Docker JupyterLab)  
**목적:** 실험 1 후속 — `calc_interaction_value` 가중치(별점 only / 감성 only / 합산)와 epoch 수(30·50·100)가 test 성능에 미치는 영향 비교

### 공통 설정

실험 1과 동일 (seed 42, test 0.2, loss `warp`, Go/No-Go `precision@5 >= 0.05`).  
interaction은 `calc_interaction_value(star, sentiment, star_weight, sentiment_weight)`로 조절했다.  
리포트 JSON의 `target_mode`는 모두 `star_sentiment_sum`으로 남아 있으나, 실제 값은 아래 가중치로 구분한다.

| 항목 | 값 |
|------|-----|
| users / items / nnz | 821 / 563 / 990 |
| train / test nnz | 792 / 198 |
| density | 0.21% |

### 변형별 결과 (Test set)

| # | interaction | star_w | sent_w | epochs | precision@5 | precision@10 | recall@5 | recall@10 | 판정 |
|---|-------------|--------|--------|--------|-------------|--------------|----------|-----------|------|
| 2a | **sentiment only** | 0 | 1 | 100 | **0.0101** | 0.0067 | **0.0449** | 0.0618 | No-Go |
| 2b | **star only** | 1 | 0 | 100 | 0.0079 | 0.0062 | 0.0365 | 0.0562 | No-Go |
| 2c | star + sentiment | 1 | 1 | 50 | 0.0079 | 0.0062 | 0.0365 | 0.0562 | No-Go |
| 2d | star + sentiment | 1 | 1 | 30 | 0.0090 | **0.0090** | 0.0421 | **0.0801** | No-Go |
| (1) | star + sentiment | 1 | 1 | 100 | 0.0079 | 0.0056 | 0.0365 | 0.0506 | No-Go |

→ 4개 변형 모두 Go 기준(0.05) 미달.

### Train 모니터링 (Unit 7 — train precision@5)

| 변형 | epochs | train precision@5 (후반) |
|------|--------|--------------------------|
| 2c star+sentiment | 50 | epoch 40~50: **0.207 → 0.218** |
| 2d star+sentiment | 30 | epoch 23~30: **0.137 → 0.164** |
| (1) star+sentiment | 100 | epoch 89~100: **0.223** (실험 1) |

→ epoch를 줄여도 train 지표는 여전히 0.14~0.22대. test와의 격차는 실험 1과 동일 패턴.

### 해석

1. **감성 only가 별점 only·합산보다 test에서 소폭 우세:** 2a precision@5(0.0101) > 2d(0.0090) > 2b·2c·실험1(0.0079). 합산(2c)은 별점 only(2b)와 test 지표가 사실상 동일 → 현재 스케일에서 **별점이 interaction 신호를 지배**하고 감성 기여는 미미하거나 상쇄된다.
2. **epoch 축소만으로는 test 이득 없음:** 50·100 epoch 합산(2c vs 실험1) test 지표 동일. 30 epoch(2d)는 precision@5·recall@10이 약간 올라 **과적합 완화 가능성**은 있으나, train 0.16 vs test 0.009 격차는 여전히 큼.
3. **가중치 비율 튜닝 여지:** 단순 합(1:1) 대신 `sentiment_weight` 상향·정규화·클리핑 등으로 스케일을 맞추면 합산 설계의 의미를 재검증할 수 있다. 2a 결과상 **감성 단독 신호는 CF에 더 유용**할 수 있다.
4. **loss/target 정합성 미해결:** 연속 interaction + `warp` 조합은 실험 1 지적과 동일. Binary(1) + warp는 아직 미실시.

### 검토 사항 (미결)

- epoch 변경만으로는 Go 달성 불가 — early stopping을 **test** precision 기준으로 넣을지 검토
- interaction 설계: sentiment only vs 가중 합산 vs 비율 보정(`star_norm` 등) 추가 비교
- Unit 10 인기 기반 baseline 대비 우위 여부

### 원본 리포트 요약

**2a — sentiment only (100 epoch)**

```json
{"metrics": {"precision@5": 0.0101, "precision@10": 0.0067, "recall@5": 0.0449, "recall@10": 0.0618}, "decision": {"go": false}}
```

**2b — star only (100 epoch)** — 실험 1 test 지표와 동일

```json
{"metrics": {"precision@5": 0.0079, "precision@10": 0.0062, "recall@5": 0.0365, "recall@10": 0.0562}, "decision": {"go": false}}
```

**2c — star+sentiment (50 epoch)** — 2b와 test 지표 동일

```json
{"metrics": {"precision@5": 0.0079, "precision@10": 0.0062, "recall@5": 0.0365, "recall@10": 0.0562}, "decision": {"go": false}}
```

**2d — star+sentiment (30 epoch)**

```json
{"metrics": {"precision@5": 0.0090, "precision@10": 0.0090, "recall@5": 0.0421, "recall@10": 0.0801}, "decision": {"go": false}}
```

### 다음 실험 (실험 2 후속)

| 우선순위 | 내용 |
|----------|------|
| 1 | **Binary(1)** + `warp` — loss/target 정합성 (실험 1·2 미실시) |
| 2 | `sentiment_weight` 스케일 보정 후 star+sentiment 재비교 |
| 3 | test precision 기준 early stopping (epoch 30 전후 탐색) |
| 4 | Unit 10 baseline(인기 기반) 대비 비교 |

---

## 실험 3 — 인기 메타 아이템 피처 ablation (조회수·스크랩수)

**일자:** 2026-07-09  
**노트북:** `LightFM_Model.ipynb` (Docker JupyterLab)  
**목적:** `recipe_fix.csv`의 인기 메타(`INQ_CNT`→`view_count`, `SRAP_CNT`→`scrap_count`)를 아이템 피처에 포함할지 여부를 ablation으로 비교

### 공통 설정

실험 2d와 동일한 interaction·학습 설정.

| 항목 | 값 |
|------|-----|
| interaction | star + sentiment (1:1) |
| loss | `warp` |
| seed | 42 |
| train/test split | 0.8 / 0.2 |
| epochs | 30 |
| Go/No-Go 기준 | test `precision@5 >= 0.05` |

**데이터 (matrix)**

| 항목 | 값 |
|------|-----|
| users / items / nnz | 821 / 563 / 990 |
| train / test nnz | 792 / 198 |
| density | 0.21% |

**ablation 방법:** Unit 2 recipe 전처리에서 `column_rename_map`·`columns_to_drop`으로 `INQ_CNT`/`SRAP_CNT` 포함 여부를 바꿨다.

| # | view_count (`INQ_CNT`) | scrap_count (`SRAP_CNT`) |
|---|------------------------|--------------------------|
| 3a | ✓ | ✗ (제외) |
| 3b | ✗ (제외) | ✓ |
| 3c | ✗ (제외) | ✗ (제외) |
| 기준 2d | ✓ | ✓ |

### 변형별 결과 (Test set)

| # | view | scrap | precision@5 | precision@10 | recall@5 | recall@10 | 판정 |
|---|------|-------|-------------|--------------|----------|-----------|------|
| **2d (기준)** | ✓ | ✓ | **0.0090** | **0.0090** | 0.0421 | **0.0801** | No-Go |
| 3a | ✓ | ✗ | **0.0090** | 0.0084 | 0.0421 | 0.0787 | No-Go |
| 3b | ✗ | ✓ | 0.0079 | 0.0067 | 0.0337 | 0.0618 | No-Go |
| 3c | ✗ | ✗ | 0.0079 | 0.0079 | 0.0365 | 0.0730 | No-Go |

→ 4개 변형 모두 Go 기준(0.05) 미달. **view+scrap 모두 포함(2d) 또는 view만 유지(3a)일 때 precision@5 최고.**

### Train 모니터링 (Unit 7 — train precision@5)

3c(현재 노트북 저장 상태) 기준: epoch 30에서 train precision@5 **0.167**.  
실험 2d와 동일하게 train·test 격차가 큼.

### 해석

1. **조회수가 스크랩수보다 기여도가 큼:** view 제외(3b) 시 precision@5가 0.0090→0.0079로 하락. scrap만 제외(3a)는 2d와 precision@5 동일(0.0090), recall@10만 소폭 감소(0.080→0.079).
2. **둘 다 제외(3c)해도 view만 제외(3b)만큼 나쁘지 않음:** 3c recall@10(0.073)은 3b(0.062)보다 높아, 두 메타를 함께 넣었을 때 상호작용·스케일 이슈 가능성은 있으나 test precision 기준 이득은 없음.
3. **절대 성능은 여전히 미달:** 최선(2d·3a)도 precision@5 0.009 — Go(0.05)의 약 18% 수준.
4. **재현성 주의:** 실행 계획상 `build_item_features`→`fit_partial` 연결은 아직 미완(`LIGHTFM_NOTEBOOK_EXECUTION_PLAN.md` E2). 순수 CF만 돌린 경우 recipe 컬럼 제거만으로 test 지표가 달라지지 않아야 하므로, **hybrid 학습 경로 사용 여부를 실험 기록에 명시**하고 `build_item_features` 연결 후 동일 ablation을 재검증하는 것이 좋다. 현재 노트북 최종 상태는 3c(둘 다 제외)이며 Unit 8 출력과 일치한다.

### 원본 리포트 요약

**3a — scrap_count 제외 (view 유지)**

```json
{"metrics": {"precision@5": 0.0090, "precision@10": 0.0084, "recall@5": 0.0421, "recall@10": 0.0787}, "decision": {"go": false}}
```

**3b — view_count 제외 (scrap 유지)**

```json
{"metrics": {"precision@5": 0.0079, "precision@10": 0.0067, "recall@5": 0.0337, "recall@10": 0.0618}, "decision": {"go": false}}
```

**3c — view + scrap 모두 제외** (현재 노트북 상태)

```json
{"metrics": {"precision@5": 0.0079, "precision@10": 0.0079, "recall@5": 0.0365, "recall@10": 0.0730}, "decision": {"go": false}}
```

### 다음 실험 (실험 3 후속)

| 우선순위 | 내용 |
|----------|------|
| 1 | `build_item_features` 연결 후 동일 ablation 재실행 (hybrid 경로 명시) |
| 2 | **Binary(1)** + `warp` — loss/target 정합성 |
| 3 | view_count 단독 vs scrap_count 단독 vs 둘 다 (정규화·binning 포함) |
| 4 | Unit 10 baseline(인기 기반) 대비 비교 |

---

## 실험 4 — 레시피 item feature 컬럼 ablation (hybrid)

**일자:** 2026-07-09  
**노트북:** `LightFM_Model.ipynb` (Docker nbconvert)  
**스크립트:** `run_recipe_ablation.ps1`  
**목적:** hybrid 학습에서 레시피 컬럼을 1개씩 제외했을 때 test 성능 변화(영향도) 측정

### 공통 설정

| 항목 | 값 |
|------|-----|
| mode | hybrid (`build_item_features` + `fit_partial`) |
| interaction | star + sentiment (1:1) |
| loss | `warp` |
| seed | 42 |
| epochs | 30 |
| 고정 포함 | `view_count`, `scrap_count` (ablation 대상 아님) |

### 변형별 결과 (Test set)

| run | excluded | precision@5 | precision@10 | recall@5 | recall@10 | Δprecision@5 | unique_features |
|-----|----------|-------------|--------------|----------|-----------|----------------|-----------------|
| baseline | (none) | 0.0101 | 0.0084 | 0.0506 | 0.0815 | 0.0000 | 2382 |
| exclude_recipe_name | recipe_name | 0.0067 | 0.0073 | 0.0292 | 0.0685 | -0.0034 | 1819 |
| exclude_cooking_method | cooking_method | 0.0045 | 0.0056 | 0.0225 | 0.0562 | -0.0056 | 2369 |
| exclude_cooking_category | cooking_category | 0.0112 | 0.0090 | 0.0534 | 0.0784 | 0.0011 | 2370 |
| exclude_main_ingred | main_ingred | 0.0124 | 0.0096 | 0.0590 | 0.0885 | 0.0022 | 2366 |
| exclude_dishes | dishes | 0.0067 | 0.0084 | 0.0337 | 0.0728 | -0.0034 | 2376 |
| exclude_cooking_level | cooking_level | 0.0045 | 0.0051 | 0.0225 | 0.0506 | -0.0056 | 2379 |
| exclude_cooking_time | cooking_time | 0.0079 | 0.0079 | 0.0393 | 0.0713 | -0.0022 | 2374 |
| exclude_aliases | aliases | 0.0101 | 0.0096 | 0.0478 | 0.0927 | 0.0000 | 1908 |
| exclude_ingredients | ingredients | 0.0112 | 0.0090 | 0.0534 | 0.0871 | 0.0011 | 1870 |
| exclude_recipe_kind | recipe_kind | 0.0090 | 0.0079 | 0.0421 | 0.0713 | -0.0011 | 2364 |
| exclude_others_count | others_count | 0.0045 | 0.0073 | 0.0225 | 0.0657 | -0.0056 | 2378 |
| exclude_basic_count | basic_count | 0.0045 | 0.0073 | 0.0225 | 0.0702 | -0.0056 | 2379 |

→ Δprecision@5 = run − baseline. **양수** = 제외 시 test가 올라감(해당 컬럼이 노이즈/과적합 가능).

### 해석

**제외 시 precision@5 상승 (노이즈·과적합 후보):**
- `main_ingred` (Δ=0.0022)
- `cooking_category` (Δ=0.0011)
- `ingredients` (Δ=0.0011)

**제외 시 precision@5 하락 (유지 가치 후보):**
- `cooking_method` (Δ=-0.0056)
- `cooking_level` (Δ=-0.0056)
- `others_count` (Δ=-0.0056)

### 원본 리포트

JSON: `runs/baseline.json`, `runs/exclude_<column>.json`

**baseline**

```json
{
  "data_files": {
    "review": "review_by_llm.csv",
    "recipe": "recipe_fix.csv",
    "ingredient_alias": "recipe_ingredient_alias.csv"
  },
  "mode": "hybrid",
  "target_mode": "star_sentiment_sum",
  "excluded_recipe_columns": [],
  "seed": 42,
  "test_ratio": 0.2,
  "epochs": 30,
  "loss": "warp",
  "matrix": {
    "num_users": 821,
    "num_items": 563,
    "nnz": 990,
    "train_nnz": 792,
    "test_nnz": 198,
    "item_feature_nnz": 17284,
    "unique_features": 2382
  },
  "metrics": {
    "precision@5": 0.010112359188497066,
    "precision@10": 0.008426966145634651,
    "recall@5": 0.05056179775280899,
    "recall@10": 0.08146067415730338
  },
  "decision": {
    "go": false,
    "criterion": "precision@5 >= 0.05"
  }
}
```

---

## 실험 5 — 2컬럼 조합 + 제거후보 3개 동시 제외 (hybrid)

**일자:** 2026-07-09  
**노트북:** `LightFM_Model.ipynb` (Docker nbconvert)  
**스크립트:** `run_experiment5.ps1`  
**목적:** 제거 후보 포함 2컬럼 조합 ablation + 제거 후보 3개 동시 제외

### 공통 설정

| 항목 | 값 |
|------|-----|
| mode | hybrid |
| interaction | star + sentiment (1:1) |
| loss | `warp` |
| seed / epochs | 42 / 30 |
| 비교 기준 | 실험 4 baseline precision@5 = **0.0101** |

### Phase 5a — 코어 조합 (Remove×Remove, Remove×Keep)

| label | excluded | precision@5 | precision@10 | recall@5 | recall@10 | Δp@5 vs exp4 | unique_features |
|-------|----------|-------------|--------------|----------|-----------|--------------|-----------------|
| exp5_5a_cooking_category_basic_count | cooking_category, basic_count | 0.0112 | 0.0073 | 0.0447 | 0.0615 | +0.0011 | 2367 |
| exp5_5a_cooking_category_cooking_level | cooking_category, cooking_level | 0.0090 | 0.0073 | 0.0334 | 0.0615 | -0.0011 | 2367 |
| exp5_5a_cooking_category_cooking_method | cooking_category, cooking_method | 0.0101 | 0.0067 | 0.0506 | 0.0629 | +0.0000 | 2357 |
| exp5_5a_cooking_category_ingredients | cooking_category, ingredients | 0.0135 | 0.0107 | 0.0646 | 0.1039 | +0.0034 | 1858 |
| exp5_5a_cooking_category_others_count | cooking_category, others_count | 0.0124 | 0.0084 | 0.0548 | 0.0728 | +0.0023 | 2366 |
| exp5_5a_ingredients_basic_count | ingredients, basic_count | 0.0101 | 0.0101 | 0.0506 | 0.0983 | +0.0000 | 1867 |
| exp5_5a_ingredients_cooking_level | ingredients, cooking_level | 0.0124 | 0.0079 | 0.0590 | 0.0758 | +0.0023 | 1867 |
| exp5_5a_ingredients_cooking_method | ingredients, cooking_method | 0.0169 | 0.0112 | 0.0815 | 0.0966 | +0.0068 | 1857 |
| exp5_5a_ingredients_others_count | ingredients, others_count | 0.0112 | 0.0084 | 0.0534 | 0.0787 | +0.0011 | 1866 |
| exp5_5a_main_ingred_basic_count | main_ingred, basic_count | 0.0124 | 0.0079 | 0.0562 | 0.0730 | +0.0023 | 2363 |
| exp5_5a_main_ingred_cooking_category | main_ingred, cooking_category | 0.0067 | 0.0067 | 0.0309 | 0.0601 | -0.0034 | 2354 |
| exp5_5a_main_ingred_cooking_level | main_ingred, cooking_level | 0.0101 | 0.0090 | 0.0478 | 0.0843 | +0.0000 | 2363 |
| exp5_5a_main_ingred_cooking_method | main_ingred, cooking_method | 0.0124 | 0.0096 | 0.0590 | 0.0843 | +0.0023 | 2353 |
| exp5_5a_main_ingred_ingredients | main_ingred, ingredients | 0.0124 | 0.0101 | 0.0590 | 0.0983 | +0.0023 | 1854 |
| exp5_5a_main_ingred_others_count | main_ingred, others_count | 0.0101 | 0.0084 | 0.0433 | 0.0770 | +0.0000 | 2362 |

### Phase 5b — Remove × Secondary

| label | excluded | precision@5 | precision@10 | recall@5 | recall@10 | Δp@5 vs exp4 | unique_features |
|-------|----------|-------------|--------------|----------|-----------|--------------|-----------------|
| exp5_5b_cooking_category_aliases | cooking_category, aliases | 0.0135 | 0.0101 | 0.0646 | 0.0938 | +0.0034 | 1896 |
| exp5_5b_cooking_category_cooking_time | cooking_category, cooking_time | 0.0056 | 0.0062 | 0.0253 | 0.0545 | -0.0045 | 2362 |
| exp5_5b_cooking_category_dishes | cooking_category, dishes | 0.0112 | 0.0096 | 0.0534 | 0.0840 | +0.0011 | 2364 |
| exp5_5b_cooking_category_recipe_kind | cooking_category, recipe_kind | 0.0079 | 0.0079 | 0.0348 | 0.0713 | -0.0022 | 2352 |
| exp5_5b_cooking_category_recipe_name | cooking_category, recipe_name | 0.0067 | 0.0090 | 0.0337 | 0.0826 | -0.0034 | 1807 |
| exp5_5b_ingredients_aliases | ingredients, aliases | 0.0112 | 0.0096 | 0.0534 | 0.0882 | +0.0011 | 1396 |
| exp5_5b_ingredients_cooking_time | ingredients, cooking_time | 0.0124 | 0.0079 | 0.0590 | 0.0758 | +0.0023 | 1862 |
| exp5_5b_ingredients_dishes | ingredients, dishes | 0.0135 | 0.0084 | 0.0646 | 0.0815 | +0.0034 | 1864 |
| exp5_5b_ingredients_recipe_kind | ingredients, recipe_kind | 0.0101 | 0.0073 | 0.0478 | 0.0702 | +0.0000 | 1852 |
| exp5_5b_ingredients_recipe_name | ingredients, recipe_name | 0.0124 | 0.0079 | 0.0590 | 0.0758 | +0.0023 | 1307 |
| exp5_5b_main_ingred_aliases | main_ingred, aliases | 0.0112 | 0.0107 | 0.0534 | 0.0994 | +0.0011 | 1892 |
| exp5_5b_main_ingred_cooking_time | main_ingred, cooking_time | 0.0079 | 0.0073 | 0.0365 | 0.0657 | -0.0022 | 2358 |
| exp5_5b_main_ingred_dishes | main_ingred, dishes | 0.0101 | 0.0090 | 0.0506 | 0.0854 | +0.0000 | 2360 |
| exp5_5b_main_ingred_recipe_kind | main_ingred, recipe_kind | 0.0101 | 0.0084 | 0.0478 | 0.0815 | +0.0000 | 2348 |
| exp5_5b_main_ingred_recipe_name | main_ingred, recipe_name | 0.0112 | 0.0101 | 0.0489 | 0.0896 | +0.0011 | 1803 |

### Phase 5c — 제거 후보 3개 동시 제외

| label | excluded | precision@5 | precision@10 | recall@5 | recall@10 | Δp@5 vs exp4 | unique_features |
|-------|----------|-------------|--------------|----------|-----------|--------------|-----------------|
| exp5_5c_all_remove | main_ingred, cooking_category, ingredients | 0.0146 | 0.0096 | 0.0657 | 0.0882 | +0.0045 | 1842 |

### 해석

- **최고 precision@5:** `exp5_5a_ingredients_cooking_method` (0.0169, excluded: ingredients, cooking_method)
- **최저 precision@5:** `exp5_5b_cooking_category_cooking_time` (0.0056)

**exp4 baseline 대비 Δprecision@5 상위:**
- `ingredients, cooking_method` (+0.0068)
- `main_ingred, cooking_category, ingredients` (+0.0045)
- `cooking_category, ingredients` (+0.0034)

**exp4 baseline 대비 Δprecision@5 하위 (제거 시 손실 큼):**
- `cooking_category, cooking_time` (-0.0045)
- `main_ingred, cooking_category` (-0.0034)
- `cooking_category, recipe_name` (-0.0034)

**5c (3개 동시 제외):**
- 3개 동시 제외 precision@5 **0.0146** (exp4 baseline 0.0101, exp4 main_ingred 단독 0.0124)

### 원본 리포트 (baseline)

```json
{
  "data_files": {
    "review": "review_by_llm.csv",
    "recipe": "recipe_fix.csv",
    "ingredient_alias": "recipe_ingredient_alias.csv"
  },
  "mode": "hybrid",
  "target_mode": "star_sentiment_sum",
  "excluded_recipe_columns": [],
  "seed": 42,
  "test_ratio": 0.2,
  "epochs": 30,
  "loss": "warp",
  "matrix": {
    "num_users": 821,
    "num_items": 563,
    "nnz": 990,
    "train_nnz": 792,
    "test_nnz": 198,
    "item_feature_nnz": 17284,
    "unique_features": 2382
  },
  "metrics": {
    "precision@5": 0.010112359188497066,
    "precision@10": 0.008988764137029648,
    "recall@5": 0.05056179775280899,
    "recall@10": 0.08258426966292134
  },
  "decision": {
    "go": false,
    "criterion": "precision@5 >= 0.05"
  }
}
```

---

## 실험 6 — ingredients+cooking_method 제외 최종 검증 (hybrid)

**일자:** 2026-07-09  
**노트북:** `LightFM_Model.ipynb` (Docker nbconvert)  
**스크립트:** `run_experiment6.ps1`  
**목적:** `ingredients`+`cooking_method` 제외 채택 전 seed 재현성·대안·모순 검증

### 공통 설정

| 항목 | 값 |
|------|-----|
| mode | hybrid |
| interaction | star + sentiment (1:1) |
| loss | `warp` |
| seeds | 42, 123, 456 |
| epochs | 30 |
| runs | 3 seed × 5 config = **15** |

### 테이블 A — seed × config

| seed | config | excluded | precision@5 | recall@5 | Δp@5 vs seed baseline |
|------|--------|----------|-------------|----------|----------------------|
| 42 | baseline | (none) | 0.0090 | 0.0449 | +0.0000 |
| 42 | candidate | ingredients, cooking_method | 0.0169 | 0.0772 | +0.0079 |
| 42 | alt_5c | main_ingred, cooking_category, ingredients | 0.0124 | 0.0590 | +0.0034 |
| 42 | ctrl_ingredients | ingredients | 0.0112 | 0.0534 | +0.0022 |
| 42 | ctrl_cooking_method | cooking_method | 0.0034 | 0.0169 | -0.0056 |
| 123 | baseline | (none) | 0.0069 | 0.0305 | +0.0000 |
| 123 | candidate | ingredients, cooking_method | 0.0057 | 0.0286 | -0.0011 |
| 123 | alt_5c | main_ingred, cooking_category, ingredients | 0.0103 | 0.0514 | +0.0034 |
| 123 | ctrl_ingredients | ingredients | 0.0080 | 0.0400 | +0.0011 |
| 123 | ctrl_cooking_method | cooking_method | 0.0080 | 0.0362 | +0.0011 |
| 456 | baseline | (none) | 0.0067 | 0.0333 | +0.0000 |
| 456 | candidate | ingredients, cooking_method | 0.0056 | 0.0278 | -0.0011 |
| 456 | alt_5c | main_ingred, cooking_category, ingredients | 0.0044 | 0.0222 | -0.0022 |
| 456 | ctrl_ingredients | ingredients | 0.0067 | 0.0333 | +0.0000 |
| 456 | ctrl_cooking_method | cooking_method | 0.0067 | 0.0333 | +0.0000 |

### 테이블 B — config별 seed 평균

| config | mean p@5 | std p@5 | mean Δp@5 vs baseline | wins vs baseline (of 3) |
|--------|----------|---------|----------------------|-------------------------|
| baseline | 0.0075 | 0.0011 | +0.0000 | 0/3 |
| candidate | 0.0094 | 0.0053 | +0.0019 | 1/3 |
| alt_5c | 0.0090 | 0.0034 | +0.0015 | 2/3 |
| ctrl_ingredients | 0.0086 | 0.0019 | +0.0011 | 2/3 |
| ctrl_cooking_method | 0.0060 | 0.0019 | -0.0015 | 1/3 |

### 테이블 C — candidate vs alt_5c

| seed | candidate p@5 | alt_5c p@5 | winner |
|------|---------------|------------|--------|
| 42 | 0.0169 | 0.0124 | candidate |
| 123 | 0.0057 | 0.0103 | alt_5c |
| 456 | 0.0056 | 0.0044 | candidate |

**head-to-head:** candidate 2/3, alt_5c 1/3, tie 0/3

### 해석·최종 판단

- candidate가 baseline 대비 precision@5 우위: **1/3 seed**
- candidate mean Δp@5 vs baseline: **+0.0019**
- ctrl_cooking_method 모든 seed에서 baseline 하락: **아니오**
- candidate vs alt_5c mean p@5: **0.0094** vs **0.0090** (std 0.0053 vs 0.0034)

**최종 피처 세트 권고 (자동 초안):**
- **보류** — seed 간 재현 부족, 추가 실험 또는 ingredients-only 제외 검토

**exp5 교차검증 (seed=42 candidate):**
- exp6_s42_candidate p@5 = **0.0169**, exp5 기대값 0.0169, 차이 0.0000 (OK)

### 원본 리포트 (seed=42 baseline)

```json
{
  "data_files": {
    "review": "review_by_llm.csv",
    "recipe": "recipe_fix.csv",
    "ingredient_alias": "recipe_ingredient_alias.csv"
  },
  "mode": "hybrid",
  "target_mode": "star_sentiment_sum",
  "excluded_recipe_columns": [],
  "seed": 42,
  "test_ratio": 0.2,
  "epochs": 30,
  "loss": "warp",
  "matrix": {
    "num_users": 821,
    "num_items": 563,
    "nnz": 990,
    "train_nnz": 792,
    "test_nnz": 198,
    "item_feature_nnz": 17284,
    "unique_features": 2382
  },
  "metrics": {
    "precision@5": 0.008988764137029648,
    "precision@10": 0.008426966145634651,
    "recall@5": 0.0449438202247191,
    "recall@10": 0.08146067415730338
  },
  "decision": {
    "go": false,
    "criterion": "precision@5 >= 0.05"
  }
}
```

---

## 실험 7 — ingredients_only vs 5c 피처 세트 확정 검증 (hybrid)

**일자:** 2026-07-09  
**노트북:** `LightFM_Model.ipynb` (Docker nbconvert)  
**스크립트:** `run_experiment7.ps1`  
**목적:** `ingredients`만 제외 vs 5c 중 기본 hybrid 피처 세트 확정

### 공통 설정

| 항목 | 값 |
|------|-----|
| mode | hybrid |
| interaction | star + sentiment (1:1) |
| loss | `warp` |
| seeds | 42, 123, 456, 789, 1024 |
| epochs | 30 |
| runs | 5 seed × 3 config = **15** |

### 테이블 A — seed × config

| seed | config | excluded | precision@5 | recall@5 | Δp@5 vs seed baseline |
|------|--------|----------|-------------|----------|----------------------|
| 42 | baseline | (none) | 0.0101 | 0.0506 | +0.0000 |
| 42 | ingredients_only | ingredients | 0.0112 | 0.0534 | +0.0011 |
| 42 | alt_5c | main_ingred, cooking_category, ingredients | 0.0112 | 0.0562 | +0.0011 |
| 123 | baseline | (none) | 0.0069 | 0.0305 | +0.0000 |
| 123 | ingredients_only | ingredients | 0.0091 | 0.0457 | +0.0023 |
| 123 | alt_5c | main_ingred, cooking_category, ingredients | 0.0091 | 0.0457 | +0.0023 |
| 456 | baseline | (none) | 0.0067 | 0.0333 | +0.0000 |
| 456 | ingredients_only | ingredients | 0.0067 | 0.0333 | +0.0000 |
| 456 | alt_5c | main_ingred, cooking_category, ingredients | 0.0056 | 0.0278 | -0.0011 |
| 789 | baseline | (none) | 0.0056 | 0.0281 | +0.0000 |
| 789 | ingredients_only | ingredients | 0.0056 | 0.0281 | +0.0000 |
| 789 | alt_5c | main_ingred, cooking_category, ingredients | 0.0056 | 0.0281 | +0.0000 |
| 1024 | baseline | (none) | 0.0056 | 0.0282 | +0.0000 |
| 1024 | ingredients_only | ingredients | 0.0068 | 0.0339 | +0.0011 |
| 1024 | alt_5c | main_ingred, cooking_category, ingredients | 0.0068 | 0.0339 | +0.0011 |

### 테이블 B — config별 seed 평균

| config | mean p@5 | std p@5 | mean Δp@5 vs baseline | wins vs baseline (of 5) |
|--------|----------|---------|----------------------|-------------------------------|
| baseline | 0.0070 | 0.0016 | +0.0000 | 0/5 |
| ingredients_only | 0.0079 | 0.0020 | +0.0009 | 3/5 |
| alt_5c | 0.0077 | 0.0022 | +0.0007 | 3/5 |

### 테이블 C — ingredients_only vs alt_5c

| seed | ingredients_only p@5 | alt_5c p@5 | winner |
|------|------------------------|------------|--------|
| 42 | 0.0112 | 0.0112 | tie |
| 123 | 0.0091 | 0.0091 | tie |
| 456 | 0.0067 | 0.0056 | ingredients_only |
| 789 | 0.0056 | 0.0056 | tie |
| 1024 | 0.0068 | 0.0068 | tie |

**head-to-head:** ingredients_only 1/5, alt_5c 0/5, tie 4/5

### 해석·최종 판단

- ingredients_only baseline 대비 우위: **3/5 seed**
- alt_5c baseline 대비 우위: **3/5 seed**
- ingredients_only vs alt_5c head-to-head: **1/5 seed**
- mean p@5: ingredients_only **0.0079** (std 0.0020) vs alt_5c **0.0077** (std 0.0022)

**최종 피처 세트 권고 (자동 초안):**
- **ingredients_only 조건부 채택** — 둘 다 baseline 대비 이득이나 차이 미미, 변경 최소 원칙으로 ingredients만 제외

### 노트북 기본값 반영

`LightFM_Model.ipynb` Unit 1 기본 `EXCLUDED_RECIPE_COLUMNS = ["ingredients"]` (env 미설정 시).  
`view_count` + `scrap_count` 및 나머지 레시피 컬럼은 포함. override: `EXCLUDED_RECIPE_COLUMNS=""` (전체 feature).  
`view_count` / `scrap_count` feature token은 항상 `log1p` 적용 (`view_count_log:…`, `scrap_count_log:…`).

**exp6 교차검증 (seed 42·123·456):**
- seed 42 `ingredients_only`: exp7 **0.0112**, exp6 **0.0112**, 차이 0.0000 (OK)
- seed 42 `alt_5c`: exp7 **0.0112**, exp6 **0.0124**, 차이 0.0012 (확인 필요)
- seed 123 `ingredients_only`: exp7 **0.0091**, exp6 **0.0080**, 차이 0.0011 (확인 필요)
- seed 123 `alt_5c`: exp7 **0.0091**, exp6 **0.0103**, 차이 0.0012 (확인 필요)
- seed 456 `ingredients_only`: exp7 **0.0067**, exp6 **0.0067**, 차이 0.0000 (OK)
- seed 456 `alt_5c`: exp7 **0.0056**, exp6 **0.0044**, 차이 0.0012 (확인 필요)

### 원본 리포트 (seed=42, ingredients 제외 + log1p)

```json
{
  "data_files": {
    "review": "review_by_llm.csv",
    "recipe": "recipe_fix.csv",
    "ingredient_alias": "recipe_ingredient_alias.csv"
  },
  "mode": "hybrid",
  "target_mode": "star_sentiment_sum",
  "excluded_recipe_columns": [
    "ingredients"
  ],
  "seed": 42,
  "test_ratio": 0.2,
  "epochs": 30,
  "loss": "warp",
  "log_numeric_columns": [
    "scrap_count",
    "view_count"
  ],
  "matrix": {
    "num_users": 821,
    "num_items": 563,
    "nnz": 990,
    "train_nnz": 792,
    "test_nnz": 198,
    "item_feature_nnz": 12176,
    "unique_features": 1870
  },
  "metrics": {
    "precision@5": 0.012359551154077053,
    "precision@10": 0.009550562128424644,
    "recall@5": 0.05898876404494382,
    "recall@10": 0.08820224719101123
  },
  "decision": {
    "go": false,
    "criterion": "precision@5 >= 0.05"
  }
}
```
