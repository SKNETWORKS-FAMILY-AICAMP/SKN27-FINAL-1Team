# Track B Base Score — 상태 보고서 (지표 동결)

**동결일:** 2026-07-14  
**동결 범위:** Track B 콜드스타트 Base Score (실험 **17~26**).  
**다음 축:** Track A 협업필터링 **설계** (본 문서 범위 밖).

상세 수치·회차 표 → [`experiments.md`](experiments.md) · 헌장 → [`METRICS.md`](METRICS.md).

---

## 1. 한 줄 결론

전 카탈로그 LightFM hybrid Base Score(ŷ)는 **informative·리뷰 다건(v≥2) 구간에서 리뷰 품질 순위에 쓸 수 있고**, **만점+리뷰 1건(v=1) 구간은 품질 미세 순위로 overclaim하면 안 된다.**  
추가 모델 ablation으로 v1·전체 ceiling L2c 5/5·v≥2 Cohen 0.30을 여는 실험은 **여기서 중단**한다.

---

## 2. 동결된 채택 설정

| 항목 | 값 |
|------|-----|
| 학습 target | `product_02_row` (`star_02 × sentiment_02`) |
| bar | Bayesian WR, m=3 (`BAR_MODE=bayesian`) |
| `MIX_GAMMA` | **0** (실험 21 T1 기각) |
| features | hybrid; `EXCLUDED=ingredients`; view/scrap **포함** (log1p) |
| `SAMPLE_WEIGHT_MODE` | **`none`** (실험 24 기각; 코드 손잡이만 잔류) |
| loss / epochs | WARP / 30 |
| Go 헌장 | 실험 **22** 이축 `L0-L5-dual` (변경 없음) |
| export | `outputs/recipe_lightfm.csv` |
| 태그 | `experiment: 22_eval_recalib` |

**Go (서비스 1차, 헌장 유지):**

```text
go = L0 ∧ L1i ∧ L2i(≥0.30) ∧ L1c ∧ L2c(≥0.25)
```

stretch(전체 ceiling 또는 v≥2에서 ρ≥0.30)는 **Go가 아님**.

---

## 3. 슬라이스 신뢰 (제품 해석)

| 슬라이스 | 대략 n | ŷ vs bar | 신뢰·사용 |
|----------|--------|-----------|-----------|
| **informative** | ~54 | L2i ≥0.30 (5/5) | **높음** — 품질 상대 순위에 사용 |
| **ceiling v≥2** | 185 | mean ρ≈0.28 (0.30 미달) | **중** — v1보다  believable; stretch 미달 명시 |
| **ceiling v=1** | 344 | ρ≈0 | **낮음** — 품질 미세 순위 **금지**; 동점·보조(인기 등) |
| **ceiling 전체** | 529 | L2c mean≈0.25권, dual Go **4/5** | v1 비중으로 상한; 단일 ρ overclaim 주의 |
| **cold** | ~2600 | bar 없음 | 콜드 Base Score; 리뷰 품질 주장이 아님 |

**제품 문구 (실험 25 고정):**  
Base Score의 ceiling·v=1(만점+리뷰1건)은 카탈로그 feature만으로 리뷰 품질 bar를 재현하기 어렵다. 서비스에서는 informative·v≥2에 더 높은 신뢰, v=1은 동점·보조 정렬로 취급한다.

---

## 4. 동결 실측 스냅샷

### 4.1 이축 Go 베이스 (실험 22)

| 집계 | 값 |
|------|-----|
| mean ρ_inf (L2i) | ≈0.362 |
| mean ρ_ceil (L2c) | ≈0.257 |
| go_dual single-seed | **4/5** (1024 L2c&lt;0.25) |
| L1i / L1c vs pop | 5/5 |

### 4.2 슬라이스 확인 (실험 26, weight=none)

| seed | L2i | L2c | ρ_vge2 | ρ_v1 | go_dual |
|------|-----|-----|--------|------|---------|
| 42 | 0.360 | 0.264 | 0.261 | 0.043 | ✓ |
| 123 | 0.308 | 0.263 | 0.285 | 0.003 | ✓ |
| 456 | 0.364 | 0.255 | 0.277 | 0.010 | ✓ |
| 789 | 0.391 | 0.263 | 0.290 | 0.024 | ✓ |
| 1024 | 0.396 | 0.230 | 0.291 | 0.008 | ✗ |

| 확인 | 결과 |
|------|------|
| L2i ≥0.30 | **5/5** |
| L1i / L1c | **5/5** |
| L2c ≥0.25 | 4/5 |
| v≥2 stretch ≥0.30 | **미달** (0/5, mean≈0.281) |
| v1 | ρ≈0 재확인 |

---

## 5. 시도·기각 (동결 근거)

| 회차 | 개입 | 판정 |
|------|------|------|
| 21 | 독립 감성; MIX γ=0.5 | T0 채택, T1 기각 |
| 22 | 이축 Go | **헌장 채택** |
| 23 | view/scrap feature 제외 | **기각** (L2c·L2i 악화) |
| 24 | `sample_weight∝review_n` | **기각** (L2c 5/5 미달; mean만 소폭↑) |
| 25 | v1 bar ← catalog feature Ridge OOF | **불가** (ρ_OOF≈0.02) → 모델 경로 중단 |
| 26 | v≥2 stretch 0.30 확인 | **미달** |

**의도적 미완료 (상한·비목표):** dual Go 5/5, L2c/v≥2에서 Cohen 0.30 안정 달성, v1 ρ 회복.

---

## 6. 지표 잠금 규칙

동결 이후 Track B에서 **하지 않음** (별도 재개 합의 전):

- target / MIX / Go 임계 변경
- v1 품질 ρ를 올리기 위한 feature·가중·용량 실험
- stretch를 dual Go에 편입하거나 임계 하향으로 “통과” 연출

허용:

- export·에이전트 소비 경로·슬라이스 신뢰 문서 반영
- Track A CF **설계·구현** (Base Score를 콜드/폴백으로 사용)
- 평가 report에 v1/vge2 ρ **기록 유지** (진단; Go 변경 아님)

---

## 7. 산출물·실행

| 경로 | 역할 |
|------|------|
| `LightFM_Model.ipynb` | Docker 공식 학습·export |
| `outputs/recipe_lightfm.csv` | 전 카탈로그 ŷ |
| `evaluation.py` | L0~L5-dual + ceiling_v1/vge2 진단 키 |
| `config.py` | seed / excluded / `SAMPLE_WEIGHT_MODE` |

재현: `ai/experiments`에서 `SAMPLE_WEIGHT_MODE` 미설정(default `none`) nbconvert.

---

## 8. CF로 넘기기 전 체크

- [x] Go 헌장·채택 설정 문서화  
- [x] 슬라이스 신뢰·overclaim 금지 명시  
- [x] 기각 실험·상한 기록  
- [ ] (후속) README/에이전트가 export를 **슬라이스 규칙에 맞게** 읽는 한 줄  
- [ ] (후속) Track A: 이력 유저 개인화 + 무이력 시 B 점수 폴백 설계  
