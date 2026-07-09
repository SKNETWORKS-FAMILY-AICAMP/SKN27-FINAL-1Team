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
