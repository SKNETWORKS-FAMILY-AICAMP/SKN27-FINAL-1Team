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


