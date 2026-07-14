# Track B 평가 지표

**헌장:** y\*=`n_star5≥2` · 추천 점수=`s_pref` · **s_pref 상위 K** 적중률.  
구현: [`evaluation.py`](evaluation.py) (CV·Go) · [`scoring.py`](scoring.py) (predict·export).

| 문서 | 용도 |
|------|------|
| **본 문서** | R0~R3·임계·프로토콜 |
| [README.md](README.md) | 실행 |
| [experiments.md](experiments.md) | 회차별 실측 이력 |

---

## 목표

warm(~563) 중 **5점 리뷰 ≥2** (~198)를 y\*로 두고,  
`model.predict(__catalog__)` → **s_pref** 내림차순 상위 K에 얼마나 포함되는지 평가.

| 용어 | 정의 |
|------|------|
| **y\*** | `n_star5 ≥ 2` → 1, else 0 |
| **s_pref** | LightFM catalog predict |
| **평가 풀** | warm CV **test fold** (~113/fold) |

---

## Go — R0~R3

**실행:** `python evaluation.py` (Docker)  
**프로토콜:** stratified 5-fold × seeds `42/123/456/789/1024`

```
go = R0 ∧ (R1∧R2∧R3 on ≥4/5 seeds)
```

| 층 | 조건 | 통과 |
|----|------|------|
| **R0** | full-fit `s_pref` 유한·std>0 | 필수 |
| **R1** | P@20 | ≥ 0.50 |
| **R2** | NDCG@20 | ≥ 0.50 |
| **R3** | Recall@20 | ≥ 0.24 |

**학습:** `POSITIVE_MODE` (default `prefer_n_star5_ge2`) — y\*=1 레시피 리뷰만 WARP matrix.

**산출:** `outputs/prefer_eval_report.json` · `recipe_prefer_ranked.csv` · Go 시 `recipe_lightfm.csv` 교체.

---

## §29 실측 (2026-07-14, 이력)

baseline P@20≈0.46 · NDCG≈0.48 · Recall≈0.23 — **No-Go**.  
상세 → [experiments.md](experiments.md) §28~29.

---

## 레거시

§1~26 Spearman·bar·감성 곱 — 코드 제거, `experiments.md`에만 보존.
