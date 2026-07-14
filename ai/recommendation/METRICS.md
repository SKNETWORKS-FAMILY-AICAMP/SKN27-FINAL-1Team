# Track B 평가 지표

**헌장:** y\*=`n_star5≥2` · 점수=`s_pref` · **Recall@20** vs **5점 비율 Bayesian Pop**.  
구현: [`evaluation.py`](evaluation.py) · Pop: [`scoring.star_popularity_scores`](scoring.py).

---

## 목표

warm test fold에서 `s_pref` 상위 20으로 **y\*=1 레시피를 얼마나 회수(Recall)하는지** 평가한다.

| 용어 | 정의 |
|------|------|
| **y\*** | `n_star5 ≥ 2` → 1 |
| **s_pref** | LightFM catalog predict |
| **Pop** | train fold **5점 비율** Bayesian WR 순위 (룰 베이스) |
| **평가 풀** | warm CV test fold (~113/fold) |

### Pop (5점 인기도)

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

**산출:** `outputs/prefer_eval_report.json` · `recipe_prefer_ranked.csv` · Go 시 `recipe_lightfm.csv` (3171행, warm+cold `y_hat`)

### Export (`recipe_lightfm.csv`)

| 컬럼 | 설명 |
|------|------|
| `y_hat` / `s_pref` | full-fit catalog predict (전 item) |
| `is_warm` | 1=리뷰 있음(563), 0=cold(2608) |
| `y_prefer` | warm: 0/1, cold: -1 |

---

## Full-catalog 진단 (Go 제외)

full-fit 후 **전체 3171** 순위에서 warm y\*=1 회수 (cold 희석 관측).  
리포트: `prefer_eval_report.json` → `full_catalog_eval` (K=20/50/100)

| 지표 | 의미 |
|------|------|
| `warm_recall_at_k` | 전역 y\*=1(198) 중 Top-K 포함 비율 |
| `warm_precision_at_k` | Top-K 중 y\*=1 비율 |
| `cold_share_at_k` | Top-K 중 cold 비율 |
| `*_pop` | 동일 풀, `star_pop`(전체 review) 순위 |

warm-fold CV Recall@20보다 **낮을 수 있음** (풀 113 → 3171).

---

## 실험 30 (이력)

외부 축(감성·참여·user holdout) 평가는 콜드스타트 단계에서 과도하다고 판단, **코드는 별점 헌장으로 복귀**. 수치는 [`experiments.md`](experiments.md) §30 참고.

---

## 레거시

mean(star_count) Pop · view/scrap Pop · external-recall-vs-pop — 폐기.
