# Track B 평가 지표

**헌장 (1차 Go):** 실험 **28** (`exp28-prefer-threshold`) — **기준선 이진** (Spearman Go **폐기**).  
구현: [`evaluation.py`](evaluation.py) · 실행: [`exp28_prefer_threshold.py`](exp28_prefer_threshold.py).

| 문서 | 용도 |
|------|------|
| **본 문서** | P0~P3·임계·근거 |
| [TRACK_B_STATUS.md](TRACK_B_STATUS.md) | 상태·채택 export |
| [experiments.md](experiments.md) | §28 실측 |
| [README.md](README.md) | 팀 스냅샷 |

---

## 목표 (실험 28+)

메타데이터(hybrid item feature)로 catalog 점수 `s_pref`를 내고, warm에서 **5점 리뷰 ≥2** 클래스의 **기준선 위/아래**를 맞춘다.  
정확한 bar 순위(Spearman)는 **Go 아님** (진단만).

| 용어 | 정의 |
|------|------|
| **y\*** | `1` ⟺ 레시피 `n_star5 ≥ 2` / `0` ⟺ warm 나머지 |
| **s** | LightFM `__catalog__` predict (`s_pref` = `y_hat`) |
| **t\*** | **train fold True의 `min(s)`** (고정) |
| **prefer_hat** | `1[s ≥ t*]` |
| **cold** | y\* 없음 — warm Go 후 `s`·`prefer_hat` export |

---

## 1차 Go — P0~P3

**프로토콜:** warm recipe stratified **5-fold** CV × seeds `42/123/456/789/1024`.

```
go = P0 ∧ (P1∧P2∧P3 on ≥4/5 seeds, fold mean)
```

| 층 | 조건 | 통과 |
|----|------|------|
| **P0** | catalog `s` 유한·std>0 (3171) | 필수 |
| **P1** | ROC-AUC(s, y\*) | ≥ **0.70** ∧ **> popularity** |
| **P2** | F1·Spec @ t* | F1 ≥ **0.55** ∧ Spec ≥ **0.70** |
| **P3** | P@20 · NDCG@20 | P@20 ≥ **0.75** ∧ **> pop@20** |

비교군: `log1p(view)+log1p(scrap)`.

**학습:** `POSITIVE_MODE=prefer_n_star5_ge2` — interaction 양성 = y\*=1 리뷰만 (WARP).

---

## 레거시 — L0~L5 dual (실험 22~26, 2026-07-14 동결 해제)

Spearman(ŷ, bar) 이축 Go. 실험 28부터 **1차 Go 아님**. 이력·실측 → [experiments.md](experiments.md) §22~26.

```
go_legacy = L0 ∧ L1i ∧ L2i(≥0.30) ∧ L1c ∧ L2c(≥0.25)
```

---

## 변경 이력

| 일자 | 회차 | 내용 |
|------|------|------|
| 2026-07-13 | 18 | L0~L5·Cohen 0.30 |
| 2026-07-14 | 22 | 이축 Go L1i+L2i+L1c+L2c |
| 2026-07-14 | 26 | v≥2 stretch 미달 → 동결 |
| 2026-07-14 | **28** | **P0~P3 기준선 이진 Go**; Spearman 1차 Go 폐기 |
