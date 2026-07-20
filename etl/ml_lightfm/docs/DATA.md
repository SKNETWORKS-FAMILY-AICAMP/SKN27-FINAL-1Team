# 학습 데이터 운용 가이드

`data/` 폴더의 CSV 3종이 모델 학습의 전체 입력입니다. 이 문서는 각 파일의 역할, 컬럼 의미, 파이프라인에서의 사용 방식, 그리고 추가 학습 시 데이터를 어떻게 조작해야 하는지를 설명합니다.

---

## 파일 목록

| 파일 | 행 수 | 역할 |
|------|-------|------|
| `review_by_llm.csv` | 1,007 | 리뷰 (유저-레시피 상호작용 + 감성 점수) |
| `recipe_fix.csv` | 3,171 | 레시피 메타데이터 (item feature 원천) |
| `recipe_ingredient_alias.csv` | 3,171 | 재료 정규화 (alias → 표준 재료명) |

---

## 1. `review_by_llm.csv` — 리뷰 데이터

유저(`group_id`)와 레시피(`recipe_id`) 사이의 상호작용 기록. WARP 학습의 interaction matrix와 선호 라벨(`y_prefer`)의 원천입니다.

### 컬럼

| 컬럼 | 타입 | 설명 | 파이프라인 사용 |
|------|------|------|----------------|
| `recipe_id` | int | 레시피 고유 ID | item 식별자 |
| `group_id` | int | 유저(리뷰어) 그룹 ID | user 식별자 |
| `star_count` | int (1~5) | 별점 | `y_prefer` 산출: 5점 리뷰 2개 이상 → 선호 |
| `content` | str | 리뷰 본문 | 전처리 시 drop (학습 미사용) |
| `positive` | float (0~1) | LLM 감성 분석: 긍정 확률 | export 집계용 (`positive_avg`) |
| `negative` | float (0~1) | LLM 감성 분석: 부정 확률 | export 집계용 (`negative_avg`) |
| `star_norm` | float (0~1) | 정규화 별점 `(star-3)/2` 클리핑 | export 집계용 (`star_norm_avg`) |

### 핵심 로직

- **Interaction matrix**: `star_count == 5`인 리뷰가 2개 이상인 레시피(`y_prefer=1`)에 대한 모든 리뷰가 positive interaction으로 사용됨
- **Popularity baseline**: Bayesian weighted rating (`n_star5 / review_n`, m=3)으로 비교 대상 생성
- `content`, `positive`, `negative`, `star_norm`은 학습 자체에는 사용되지 않으며, export CSV의 집계 컬럼으로만 활용

---

## 2. `recipe_fix.csv` — 레시피 메타데이터

전체 3,171개 레시피의 속성. LightFM의 item feature를 구성하는 핵심 원천입니다.

### 학습에 사용되는 컬럼

| 원본 컬럼 | 리네임 | 타입 | feature 생성 방식 |
|-----------|--------|------|-------------------|
| `RCP_SNO` | `recipe_id` | int | item ID |
| `CKG_NM` | `recipe_name` | str | categorical feature |
| `INQ_CNT` | `view_count` | int | `log1p` 변환 → numeric feature |
| `SRAP_CNT` | `scrap_count` | int | `log1p` 변환 → numeric feature |
| `CKG_MTH_ACTO_NM` | `cooking_method` | str | categorical (예: 볶기, 끓이기, 굽기) |
| `CKG_STA_ACTO_NM` | `cooking_category` | str | categorical (예: 술안주, 해장, 간식) |
| `CKG_MTRL_ACTO_NM` | `main_ingred` | str | categorical (예: 돼지고기, 해물) |
| `CKG_KND_ACTO_NM` | `recipe_kind` | str | categorical (예: 메인반찬, 국/탕) |
| `CKG_INBUN_NM` | `dishes` | str | categorical (예: 2인분, 4인분) |
| `CKG_DODF_NM` | `cooking_level` | str | categorical (예: 초급, 중급) |
| `CKG_TIME_NM` | `cooking_time` | str | categorical (예: 30분이내, 2시간이내) |

### 학습에 사용되지 않는 컬럼

`CKG_MTRL_CN` (재료 원문), `INQ_CNT_RATE`, `REVIEW_*`, `*_LOG*`, `*_2024`, `*_2026` 등 파생 통계 컬럼은 `config.py`의 `RECIPE_COLS` 필터에 의해 로드 시 제외됩니다.

---

## 3. `recipe_ingredient_alias.csv` — 재료 정규화

레시피별 재료 목록을 표준 alias로 매핑한 테이블. `aliases` feature를 생성합니다.

### 컬럼

| 컬럼 | 타입 | 설명 | 파이프라인 사용 |
|------|------|------|----------------|
| `RCP_SNO` | int | 레시피 ID (join key) | recipe_fix와 merge |
| `CKG_NM` | str | 레시피명 | merge 보조 (실 사용 X) |
| `ingredients_raw` | str (JSON array) | 원본 재료 리스트 | drop |
| `aliases_matched` | str (JSON array) | alias 매칭 결과 `[{alias_id, name}]` | `alias:{alias_id}` feature 생성 |
| `ingredients_normalized` | str (JSON array) | 정규화된 재료 `[[name, qty, unit]]` | `ingredient:{name}` feature 생성 (기본 제외) |
| `others_count` | int | 기타 재료 수 | numeric feature |
| `basic_count` | int | 기본 양념 수 | numeric feature |
| `others_items` | str | 기타 재료 목록 | drop |
| `basic_items` | str | 기본 양념 목록 | drop |

### 참고

- `ingredients` 컬럼은 기본 설정(`EXCLUDED_RECIPE_COLUMNS=ingredients`)에서 **제외**됨 → alias만 feature로 사용
- 환경 변수 `EXCLUDED_RECIPE_COLUMNS`를 변경하면 ingredients도 feature에 포함 가능

---

## 데이터 흐름 요약

```
review_by_llm.csv ──┐
                    ├─→ prepare_training_frames() ──→ review_df + recipe_df
recipe_fix.csv ─────┤                                       │
                    │                                       ├─→ build_lightfm_ids()    → dataset, item_ids
recipe_ingredient_  │                                       ├─→ build_prefer_labels()  → y_prefer (0/1)
alias.csv ──────────┘                                       ├─→ build_interactions()   → WARP matrix
                                                            └─→ build_item_features()  → item features
```

---

## 추가 학습 시 데이터 조작 가이드

### 시나리오 1: 새 레시피 추가

1. **`recipe_fix.csv`**: 새 행 추가. 최소 필수 컬럼: `RCP_SNO`, `CKG_NM`, `INQ_CNT`, `SRAP_CNT`, 카테고리 컬럼들
2. **`recipe_ingredient_alias.csv`**: 같은 `RCP_SNO`로 행 추가. `aliases_matched`에 정규화된 재료 alias JSON 배열
3. 리뷰가 없으면 cold item으로 처리됨 (item feature만으로 점수 생성)

### 시나리오 2: 새 리뷰 추가

1. **`review_by_llm.csv`**: 새 행 추가
   - `recipe_id`: 대상 레시피 (recipe_fix에 존재해야 함)
   - `group_id`: 리뷰어 식별자 (새 유저면 새 ID)
   - `star_count`: 1~5 정수
   - `positive`, `negative`: LLM 감성 분석 결과 (없으면 0.5/0.5)
   - `star_norm`: `(star_count - 3) / 2`, 클리핑 [0, 1]
2. 해당 레시피의 5점 리뷰가 2개 이상이 되면 자동으로 `y_prefer=1` → interaction matrix에 포함

### 시나리오 3: 개인화 CF (향후)

현재 catalog 모드(`__catalog__` 유저)로 전체 레시피 점수를 생성합니다. 개인화는:

1. 새 유저의 선호 레시피 interaction을 `review_by_llm.csv`에 추가
2. `train.py` 재실행 → 모델이 해당 유저의 임베딩을 학습
3. 추론 시 `model.predict(user_idx, item_idxs)` 로 개인화 점수 산출

### 주의사항

- **`recipe_id`와 `RCP_SNO`는 동일한 키** — 파일 간 일관성 유지 필수
- **`group_id`는 정수** — 새 유저 추가 시 기존 ID와 충돌 방지
- recipe_fix의 카테고리 값이 기존에 없는 새 값이면 자동으로 새 feature로 추가됨
- 데이터 추가 후 `python train.py` 재실행으로 모델 갱신

---

## 환경별 데이터 경로

| 환경 | 경로 |
|------|------|
| Docker (공식) | `/workspace/project/data/` |
| 로컬 (참조용) | `etl/ml_lightfm/data/` |

`config.py`의 `PROJECT_ROOT` 환경 변수가 기준 경로를 결정합니다.
