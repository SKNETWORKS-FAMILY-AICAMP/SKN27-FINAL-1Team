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

**산출:** `outputs/prefer_eval_report.json` · `recipe_prefer_ranked.csv`

---

## 레거시

mean(star_count) Pop · view/scrap Pop — 폐기.
