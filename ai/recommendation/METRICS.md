# Track B 평가 지표 (L0~L5 dual)

Track B 콜드스타트 Base Score(ŷ)의 **1차 Go**·진단 지표 정의. 구현: [`evaluation.py`](evaluation.py).  
**헌장 버전:** 실험 **22** (`L0-L5-dual`) — informative + ceiling **이축 Go**.  
**동결:** 2026-07-14 — 헌장·임계 **잠금**. 실측·슬라이스 신뢰·기각 이력 → [`TRACK_B_STATUS.md`](TRACK_B_STATUS.md).

| 문서 | 용도 |
|------|------|
| **본 문서** | 지표·임계값·근거 (헌장) |
| [TRACK_B_STATUS.md](TRACK_B_STATUS.md) | **동결 상태 보고서** |
| [README.md](README.md) §1.2·§1.5 | 팀 스냅샷 |
| [experiments.md](experiments.md) | 회차별 실측 수치 |

---

## Spearman 기준 (Cohen)

| 효과 크기 | r | 본 프로젝트 사용 |
|-----------|---|------------------|
| Small | 0.10 | L1i ρ 하한 |
| Medium | **0.30** | **L2i** (informative) Go; L4·L2c stretch 목표 |
| Large | 0.50 | 장기 목표 |

**Track B 설계 원칙 (절대 점수 ≠ 목표)**

1. Base Score는 regression target이 아니라 **상대 순위**를 실을 용기다.  
2. 동점·천장 붕괴를 줄여 **구분력**을 확보하는 것이 개선이다.  
3. 스케일·오프셋은 부차 — Go는 Spearman·baseline 대비·슬라이스 구분력.

---

## 이축 Go 도입 근거 (실험 21→22)

실험 14~20 헌장은 ceiling bar가 **사실상 동점**이라 Spearman이 무의미하다고 보고 Go를 **informative만**에 걸었다.

실험 21(독립 감성 재분석) 이후:

| 사실 | 함의 |
|------|------|
| v1_all5 uniq **24 → 295** (uniq% 0.07 → 0.83) | ceiling에서 **순위축 성립** |
| warm 대다수 ≈ ceiling | 서비스 Base Score 품질을 informative(~8%)만으로 승인하면 **다수 구간을 놓침** |
| T1이 informative ρ↑ · ceiling ρ↓ | Go 축이 하나면 채택/기각이 **엇갈림** |

→ **Go = informative 품질 ∧ ceiling 품질** (이축).

---

## 핵심 용어

| 용어 | 의미 | 사용 |
|------|------|------|
| **ŷ** | LightFM catalog predict | 모델 점수·순위 |
| **bar** | Bayesian WR on `mean(star_02×sentiment_02)` (m=3) | warm 관측 정답 |
| **popularity** | `log1p(view)+log1p(scrap)` | 인기 baseline |
| **informative** | `star_varies ∨ low_tail` | 소수·변동 구간; **L1i·L2i** |
| **ceiling** | `star_norm_avg >= 1` | 다수·만점 구간; **L1c·L2c** |
| **ρ_model** | `Spearman(ŷ, bar)` on 해당 슬라이스 | L1*/L2* |
| **ρ_pop** | `Spearman(popularity, bar)` on **동일** 슬라이스 | L1* 인기 대비 |

슬라이스 멤버십 정의는 실험 14와 동일 (`evaluation.build_warm_subsets`).

---

## 1차 Go (서비스 반영) — 실험 22+

```
go = L0
   AND L1i (informative Anti-Random, 4/5 seeds)
   AND L2i (informative Spearman ≥ 0.30)
   AND L1c (ceiling vs pop, 4/5 seeds)
   AND L2c (ceiling Spearman ≥ 0.25)
```

| 층 | 이름 | 조건 | 역할 |
|----|------|------|------|
| **L0** | Operational | coverage=1.0, score_std>1e-6 | 전 item 유한 ŷ |
| **L1i** | Anti-Random (informative) | ρ>0.10, null p<0.05; **ρ>ρ_pop** **4/5** | 소수 구간 랜덤·인기 대비 |
| **L2i** | Ranking (informative) | ρ ≥ **0.30** | Cohen Medium |
| **L1c** | Anti-Pop (ceiling) | **ρ_model > ρ_pop** **4/5** | 다수 구간 인기 대비 |
| **L2c** | Ranking (ceiling) | ρ ≥ **0.25** | 현 베이스라인 비퇴보 바닥 |
| L3 | Train Consistency | Spearman(ŷ, train) ≥ 0.30 | 진단 |
| L4 | Full Warm | all warm ρ (목표 0.30) | **Go 아님** — 슬라이스 **혼합** |
| L5 | Cold | ŷ_cold vs popularity | 진단 |

**단일 seed:** `go_single` = L0 ∧ L1i_single ∧ L2i ∧ L1c_single ∧ L2c.  
**최종 Go:** 위 + L1i multi-seed ∧ L1c multi-seed (각 4/5).

### L2c = 0.25 근거

- exp21 T0 mean ceiling ρ ≈ **0.257** → 즉시 Cohen 0.30을 ceiling Go로 걸면 “기준만 올려 탈락”이 됨.  
- 1차 Go 바닥 = **비퇴보(≥0.25) + L1c(인기 대비)**.  
- **stretch:** `L2c_target = 0.30` (Cohen Medium) — Go 아님. 실험 26에서 ceiling **v≥2** 기준 확인 결과 **미달**(mean ρ≈0.281); Track B 지표 동결 후 재개는 STATUS 합의 후.

### L4 예외 문구 (개정)

예전: “ceiling bar 분산≈0 → Spearman 무의미”.  
지금: ceiling는 **순위 성립**; all-warm은 informative+ceiling **혼합**이라 단일 ρ로 Go하기 부적합 → **진단만**.

---

## L0 — Operational

| 지표 | 임계값 |
|------|--------|
| coverage | = 1.0 |
| score_std(ŷ) | > 1e-6 |

---

## L1i — Anti-Random (informative)

| 기호 | 정의 |
|------|------|
| ρ_model | `Spearman(ŷ, bar)` on informative |
| ρ_pop | `Spearman(popularity, bar)` on informative |
| null p | informative ŷ 순열 vs bar (1000회) |

| 조건 | 임계값 |
|------|--------|
| ρ_model | > 0.10 |
| null p | < 0.05 |
| vs pop | **4/5 seed** ρ_model > ρ_pop |

---

## L2i — Ranking Quality (informative)

**informative** = `star_varies` ∪ `low_tail`

| subset | 정의 |
|--------|------|
| ceiling | `star_norm_avg >= 1` |
| star_varies | `star_norm_avg < 1` |
| low_tail | `legacy_review_rank < 1.5` |
| **informative** | star_varies ∨ low_tail |

**Go:** Spearman(ŷ, bar) on informative **≥ 0.30**.

---

## L1c — Anti-Pop (ceiling)

| 조건 | 임계값 |
|------|--------|
| vs pop | **4/5 seed**에서 `Spearman(ŷ, bar) > Spearman(pop, bar)` on **ceiling** |

(단건: `l1c_single_pass` = ρ_ceil_model > ρ_ceil_pop.)

---

## L2c — Ranking Quality (ceiling)

**Go:** Spearman(ŷ, bar) on ceiling **≥ 0.25**.  
**Stretch (기록):** ≥ 0.30.

---

## L3 / L4 / L5

- **L3:** Spearman(ŷ, train_item_signal) ≥ 0.30 — 진단.  
- **L4:** all-warm ρ 목표 0.30 — Go 제외 (혼합).  
- **L5:** cold vs popularity — 진단. 정답 없음 → warm 이축 Go로 간접 검증.

---

## B0~B3 → L0~L5 매핑

| 구 | 신 | Go |
|----|-----|-----|
| B0 | L0 | **예** |
| B2 informative | **L2i** | **예** |
| (없음→22) | **L2c** ceiling | **예** (≥0.25) |
| B2 all warm | L4 | **아니오** (혼합) |
| B3 | L3 | 진단 |
| B1′ | L5 | 진단 |
| L1 (19) | **L1i** | **예** |
| (없음→22) | **L1c** | **예** (4/5) |

---

## 변경 이력

| 일자 | 회차 | 내용 |
|------|------|------|
| 2026-07-13 | **18** | L0~L5·Cohen 0.30; Go = L0+L1+L2 |
| 2026-07-14 | **19** | L1 = informative + ρ(pop,bar) |
| 2026-07-14 | **20** | Bayesian WR bar; ceiling ρ↑ |
| 2026-07-14 | **21** | 독립 감성 uniq↑; 혼합 미채택 |
| 2026-07-14 | **22** | **이축 Go** L1i+L2i+L1c+L2c(0.25); L4 예외 문구 개정 |
