# Track B 평가 지표 (L0~L5)

Track B 콜드스타트 Base Score(ŷ)의 **1차 Go**·진단 지표 정의. 구현: [`evaluation.py`](evaluation.py).

| 문서 | 용도 |
|------|------|
| **본 문서** | 지표·임계값·근거 (헌장) |
| [README.md](README.md) §1.5 | 팀 스냅샷 |
| [experiments.md](experiments.md) | 회차별 실측 수치 |

---

## Spearman 0.30 (Cohen Medium) 기준 선정

### 배경

추천 시스템은 단순히 점수를 정확하게 예측하는 것이 아니라, 사용자가 실제로 선호할 아이템의 **순위(Ranking)** 를 얼마나 잘 재현하는지가 중요하다. 따라서 본 프로젝트에서는 순위 품질 평가를 위해 **Spearman Rank Correlation**을 핵심 성능 지표로 사용하였다.

### Spearman Rank Correlation

Spearman 상관계수는 모델이 예측한 레시피의 순위와 실제 데이터의 순위가 얼마나 일치하는지를 측정하는 지표이다.

| Spearman | 의미 |
|----------|------|
| 1.0 | 순위가 완전히 동일 |
| 0.5 이상 | 높은 순위 일치 |
| 0.3 | 의미 있는 순위 상관관계 |
| 0 | 랜덤 수준 |
| -1 | 완전히 반대 순위 |

추천 시스템에서는 예측 점수 자체보다 실제 추천 순서가 얼마나 올바른지가 중요하므로 Spearman을 주요 평가 지표로 사용하였다.

### Cohen Medium (0.30)의 의미

실험에서는 Spearman **0.30 이상**을 목표로 설정하였다. 이 기준은 Jacob Cohen이 제안한 효과 크기(Effect Size) 해석을 참고하였다.

| 효과 크기 | 상관계수 (r) |
|-----------|-------------|
| Small | 0.10 |
| Medium | **0.30** |
| Large | 0.50 |

원래는 Pearson Correlation 기준이나, 실무·추천 시스템 연구에서는 Spearman에도 동일 수준의 해석을 적용하는 경우가 많다. 따라서 **Spearman ≥ 0.30**은 모델이 랜덤 수준을 넘어 실제 사용자 선호 순서를 **의미 있게** 학습했다고 판단할 수 있는 **최소 기준**으로 정의한다.

### 프로젝트 적용 기준

- 전체 레시피 약 **3,100**개 (warm ≈ 600, cold ≈ 2,500)
- Cold item은 상호작용 정답이 없으므로 **순위 성능 평가는 warm에서 수행**
- **서비스 반영(1차 Go):** L0(정상 동작) + L1(Random·Popularity baseline 대비 우수) + **L2(Spearman ≥ 0.30)**

### 선정 이유

Spearman 0.30은 최고 성능은 아니지만 (1) 랜덤 추천이 아님을 확인하고 (2) 사용자 선호 순서를 일정 수준 재현하며 (3) 콜드스타트 환경에서 **서비스 가능한 최소 품질**을 확보하는 기준이다. Interaction 축적 후 **0.40~0.50**(Cohen Large)으로 단계 상향을 목표로 한다.

### L2 보완 (기술적 정합)

공식 문안의 “Warm Dataset Spearman ≥ 0.30”은 **순위가 성립하는 warm 구간(informative subset, n≈49)** 에 적용한다. warm 563개 중 약 94%는 별점 천장(ceiling)으로 관측 bar 분산이 없어 Spearman이 정의상 무의미하다(§[experiments.md](experiments.md) 실험 14). **전체 warm Spearman**은 범용 목표(Cohen 0.30)를 유지하되 **Go에서 제외(L4, DATASET_EXCEPTION)** 하고 calibration 수치만 기록한다.

---

## 핵심 용어

| 용어 | 의미 | 사용 |
|------|------|------|
| **ŷ** | LightFM catalog predict | 모델 점수·순위 |
| **bar** | `mean(star_02×sentiment_02)` | warm 관측 정답 순위 (ρ 비교 축) |
| **popularity** | `log1p(view)+log1p(scrap)` | 인기-only baseline |
| **informative** | `star_varies ∨ low_tail` (n≈49) | 순위가 성립하는 warm 구간; **L1·L2 공통** |
| **ρ_model** | `Spearman(ŷ, bar)` on informative | L1·L2 모델 상관 |
| **ρ_pop** | `Spearman(popularity, bar)` on informative | L1 인기 baseline (동일 bar축) |
| **null p** | ŷ 순열 vs bar | L1 Anti-random 유의성 |

---

## 1차 Go (서비스 반영)

```
go = L0_pass AND L1_pass AND L2_pass
```

| 층 | 이름 | 조건 | 역할 |
|----|------|------|------|
| **L0** | Operational | coverage = 1.0, score_std > 1e-6 | 전 item(cold 포함) 유한 ŷ |
| **L1** | Anti-Random | informative에서 ρ_model > 0.10, null p < 0.05; **ρ_model > ρ_pop** 를 **4/5 seed** | **순위 성립 구간**에서 랜덤·인기 대비 (L2와 동일 축) |
| **L2** | Ranking Quality | warm **informative** ρ_model **≥ 0.30** | Cohen Medium |
| L3 | Train Consistency | Spearman(ŷ, train) ≥ 0.30 | 진단 only |
| L4 | Full Warm Spearman | all warm ρ (목표 0.30) | **DATASET_EXCEPTION** — Go 아님 |
| L5 | Cold Diagnostic | ŷ_cold vs popularity | 진단 only |

**L1 multi-seed:** 단일 run은 `l1_single_pass`. 최종 `L1_pass`는 5 seed에서 ρ_model > ρ_pop **4/5** ([실험 19](experiments.md)).

**해석 범위 (실험 19):** Go는 “**순위가 성립하는 informative**에서 공정한 축(동일 subset·ρ_pop=Spearman(pop,bar)·L2≥0.30 유지)으로 확인”한 것이다. 임계 완화 아님. **ceiling(5점 포화 추정)·L4**에서의 순위 개선은 Go에 포함되지 않으며 → [실험 19 §다음](experiments.md) / 실험 20.

---

## L0 — Operational (구 B0)

| 지표 | 임계값 |
|------|--------|
| coverage | = 1.0 |
| score_std(ŷ) | > 1e-6 |

---

## L1 — Anti-Random

L2와 **같은 informative**에서 평가한다. all-warm은 ceiling 혼합으로 ρ·null p가 왜곡되므로 Go에 쓰지 않는다([실험 19](experiments.md)).

| 기호 | 정의 |
|------|------|
| **ρ_model** | `Spearman(ŷ, bar)` on informative |
| **ρ_pop** | `Spearman(popularity, bar)` on informative — **ŷ vs pop 아님** |
| **null p** | informative에서 ŷ 순열 vs bar (1000회) |

| 조건 | 임계값 | 근거 |
|------|--------|------|
| ρ_model | **> 0.10** | Cohen small |
| null 대비 | permutation **p < 0.05** | 통계적 유의 |
| popularity 대비 | **4/5 seed**에서 ρ_model > ρ_pop | [실험 11·19](experiments.md) |

기록(Go 아님): all-warm legacy ρ, informative Top-10/20 overlap.

---

## L2 — Ranking Quality (구 B2 개정)

**informative subset** = `star_varies` ∪ `low_tail` (실험 14·15·16과 동일 정의)

| subset | 정의 |
|--------|------|
| ceiling | `star_norm_avg >= 1` |
| star_varies | `star_norm_avg < 1` |
| low_tail | `legacy_review_rank < 1.5` (= `star_norm_avg + sentiment_avg`) |
| **informative** | star_varies ∨ low_tail |

**Go:** Spearman(ŷ, bar) on informative **≥ 0.30** (= ρ_model ≥ 0.30)

보조(기록): Top-50(관측) ∩ Top-100(예측). NDCG@50는 Go **아님**(bar 쏠림 시 과대평가, 실험 13·17).

---

## L3 — Train Consistency (구 B3, 진단)

Spearman(ŷ, train_item_signal) ≥ 0.30 — 학습 신호 정합 sanity. **Go 아님.**

---

## L4 — Full Warm Spearman (DATASET_EXCEPTION)

| 항목 | 내용 |
|------|------|
| 범용 목표 | Cohen medium **0.30** on all warm |
| 본 데이터셋 | **Go 제외** — ceiling 혼합으로 구조적 미달 |
| 예외 사유 | warm 563 중 ~94% ceiling — 관측 bar 분산 ≈ 0 |
| 실측 상한 (거친) | 529×0 + 49×0.5 / 563 ≈ **0.04** |
| 대체 Go | L2 informative |
| 재검토 | ceiling 비율 < 80% 시 전역 L4 Go 재활성화 검토 |

---

## L5 — Cold Diagnostic (구 B1′)

- Spearman(ŷ_cold, popularity_proxy)
- cold score_std

정답 없음 → **L0 + warm L1/L2**로 간접 검증.

---

## B0~B3 → L0~L5 매핑

| 구 (실험 13~17) | 신 (실험 18+) | Go |
|-----------------|---------------|-----|
| B0 | L0 | **예** |
| B2 (전체 warm ρ) | L4 | **아니오** (예외) |
| B2 (informative ρ) | L2 | **예** |
| B3 | L3 | 진단 |
| B1′ | L5 | 진단 |
| (없음) | L1 (19: informative·bar) | **예** |
| B4 | (미실행) | L1 popularity와 연계 진단 |

---

## 변경 이력

| 일자 | 회차 | 내용 |
|------|------|------|
| 2026-07-13 | **18** | L0~L5 체계·Cohen 0.30 근거 확정; Go = L0+L1+L2 |
| 2026-07-14 | **19** | L1 = informative + ρ(pop,bar); 공정 순위 평가 명시; Go 통과; ceiling→실험 20 |