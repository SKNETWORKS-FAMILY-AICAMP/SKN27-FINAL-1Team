# Track B 평가 지표

**헌장 (1차 Go):** 실험 **29 (재구성)** — **추천 전용 R0~R3** (`exp29-recommend-go`).  
구현: [`evaluation.py`](evaluation.py) · 실행: [`exp29_star_only_prefer.py`](exp29_star_only_prefer.py).

| 문서 | 용도 |
|------|------|
| **본 문서** | R0~R3·임계·근거 |
| [TRACK_B_STATUS.md](TRACK_B_STATUS.md) | 상태·채택 export |
| [experiments.md](experiments.md) | §29 실측 |
| [README.md](README.md) | 팀 스냅샷 |

---

## 목표

warm 레시피(~563) 중 **5점 리뷰 ≥2** (~198)를 **관련 아이템**으로 두고, catalog 점수 `s_pref` **상위 K**에 선호 레시피가 얼마나 오는지 평가한다.

| 용어 | 정의 |
|------|------|
| **y\*** | `1` ⟺ `n_star5 ≥ 2` / warm 나머지 `0` |
| **s** | LightFM hybrid catalog `s_pref` |
| **평가 풀** | warm **CV test fold** (~113/fold) |
| **t\*, prefer_hat** | export·진단용 — **Go 아님** |

---

## 1차 Go — R0~R3

**프로토콜:** warm stratified **5-fold** × seeds `42/123/456/789/1024`.

```
go = R0 ∧ (R1∧R2∧R3 on ≥4/5 seeds, fold mean)
```

| 층 | 조건 | 통과 |
|----|------|------|
| **R0** | catalog `s` 유한·std>0 (3171 full-fit) | 필수 |
| **R1** | **P@20**(`s`, y\*) on test fold | ≥ **0.50** |
| **R2** | **NDCG@20** | ≥ **0.50** |
| **R3** | **Recall@20** | ≥ **0.24** |

**진단 only (Go 아님):** ROC-AUC, F1, Spec @ `t*`, popularity `log1p(view)+log1p(scrap)`.

**학습 (§29 ablation):** `POSITIVE_MODE` = baseline / `prefer_n_star5_ge2_five_star_rows`(29a) / `five_star_reviews_only`(29b).

---

## 레거시 — P0~P3 (§28, 폐기)

이진 분류 + pop beat. §29 재구성으로 **1차 Go 아님**.

| 층 | 요약 |
|----|------|
| P1 | AUC≥0.70 ∧ >pop |
| P2 | F1·Spec @ `t*=min(s)` |
| P3 | P@20≥0.75 ∧ >pop |

---

## 레거시 — L0~L5 dual (§22~26)

Spearman 이축 Go. 이력 → [experiments.md](experiments.md) §22~26.

---

## 변경 이력

| 일자 | 회차 | 내용 |
|------|------|------|
| 2026-07-14 | 28 | P0~P3 기준선 이진 (후 폐기) |
| 2026-07-14 | **29** | **R0~R3 추천 Go**; pop beat·t\* 이진 Go 제거 |
