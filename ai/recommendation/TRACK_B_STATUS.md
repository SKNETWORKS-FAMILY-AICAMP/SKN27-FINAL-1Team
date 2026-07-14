# Track B Base Score — 상태 보고서

**갱신:** 2026-07-14 — **R0~R3** 추천 헌장 · §29 재실행.

상세 → [`METRICS.md`](METRICS.md) · 실측 → [`experiments.md`](experiments.md) §29.

---

## 1. 한 줄 결론

warm **n_star5≥2** 레시피를 **상위 K 추천**으로 맞추는지 **P@20·NDCG@20·Recall@20**으로 Go 판정.  
pop beat·AUC·Spec @ `t*`는 **진단만**.

---

## 2. 채택 설정

| 항목 | 값 |
|------|-----|
| y* | `n_star5 ≥ 2` |
| Go | **R0~R3** |
| 학습 ablation | baseline / 29a / 29b |
| 실행 | `exp29_star_only_prefer.py` |

---

## 3. export

| 파일 | 상태 |
|------|------|
| `exp29_report.json` | R0~R3 No-Go (3 arm) |
| `recipe_prefer_ranked_{arm}.csv` | 진단 |
| `recipe_lightfm.csv` | **미교체** |

§29 R-Go: P@20≈0.46, NDCG≈0.49, Recall≈0.23 — 임계(0.50/0.50/0.24) 근접하나 4/5 seed 미달.
