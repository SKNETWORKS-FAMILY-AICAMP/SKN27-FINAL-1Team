# 평가 지표 헌장

**상태:** Phase 1 완료 (2026-07-15)  
**구현:** [`evaluation.py`](../evaluation.py) · Pop: [`scoring.star_popularity_scores`](../scoring.py)

---

## 정의

| 용어 | 정의 |
|------|------|
| **y\*** | `n_star5 ≥ 2` → 1 (5점 리뷰 2건 이상인 레시피) |
| **s_pref** | LightFM catalog predict 점수 |
| **Pop** | train fold **5점 비율** Bayesian WR 순위 (룰 베이스) |
| **평가 풀** | warm CV test fold (~113/fold) |

### Pop (5점 Bayesian 인기도)

```
R = n_star5 / review_n        # 레시피 5점 비율 (0~1)
C = train fold 전체 5점 비율
WR = v/(v+m) · R + m/(v+m) · C
```

- `v` = train fold 해당 레시피 리뷰 수
- `m` = **3**
- 5점 누적 ↑ → R ↑ → WR ↑ (리뷰 적으면 C 쪽으로 수축)
- test 레시피에 train 리뷰 없으면 `WR = C`

---

## Go — R0~R2

**실행:** `python evaluation.py` (Docker)

```
go = R0 ∧ (R1 on ≥4/5 seeds)
```

| 층 | 조건 |
|----|------|
| **R0** | full-fit `s_pref` 유한·std>0 |
| **R1** | **Recall@20(model) > Recall@20(Pop)** · ≥4/5 seed |

Seeds: `(42, 123, 456, 789, 1024)`

---

## 달성 수치 (Phase 1)

### Warm-fold CV (Go 판정 대상)

| 지표 | Model | Pop |
|------|-------|-----|
| **Recall@20** (mean) | **0.236** | 0.152 |
| Precision@20 | 0.468 | — |
| **Go** | **5/5 seed 통과** | — |

### Full-catalog 진단 (Go 제외, 참고)

| K | Recall | Precision | cold_share |
|---|--------|-----------|------------|
| 20 | 0.101 | 1.00 | 0% |
| 50 | 0.242 | 0.96 | 2~5% |
| 100 | 0.424 | 0.84 | ~10% |

---

## Export (`recipe_lightfm.csv`)

| 컬럼 | 설명 |
|------|------|
| `y_hat` / `s_pref` | full-fit catalog predict (전 item) |
| `prefer_rank` | s_pref 내림차순 전체 순위 (1~3171) |
| `is_warm` | 1=리뷰 있음(563), 0=cold(2608) |
| `y_prefer` | warm: 0/1, cold: -1 |
| `prefer_hat` | t_star 기준 이진 추정 |
| `n_star5` | 5점 리뷰 수 |

---

## Full-catalog 진단 지표

| 지표 | 의미 |
|------|------|
| `warm_recall_at_k` | 전역 y\*=1(198) 중 Top-K 포함 비율 |
| `warm_precision_at_k` | Top-K 중 y\*=1 비율 |
| `cold_share_at_k` | Top-K 중 cold 비율 |
| `*_pop` | 동일 풀, `star_pop`(전체 review) 순위 기준 |

리포트: `outputs/prefer_eval_report.json` → `full_catalog_eval`

---

## 산출물

| 파일 | 역할 |
|------|------|
| `outputs/prefer_eval_report.json` | CV Go + full-catalog 진단 리포트 |
| `outputs/recipe_lightfm.csv` | 전 catalog export (3171행) |
| `outputs/recipe_prefer_ranked.csv` | warm-only ranked (참고) |
