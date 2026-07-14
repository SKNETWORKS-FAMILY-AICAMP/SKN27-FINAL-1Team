# LightFM Track B — `ai/recommendation`

코드·데이터·노트북·실험 기록은 **본 폴더**에 두고, **Docker 실행 환경**은 [`../experiments/`](../experiments/)에 둡니다.

| 경로 | 내용 |
|------|------|
| `data/` | 입력 CSV (`review_by_llm.csv`, `recipe_fix.csv`, …) |
| `outputs/` | `recipe_lightfm.csv`, `ablation_report.json` |
| `LightFM_Model.ipynb` | 실행 노트북 |
| `evaluation.py`, `scoring.py` | 평가·스코어 유틸 |
| `METRICS.md` | **R0~R3 추천 Go** · 임계·프로토콜 |
| `config.py`, `data_io.py`, `preprocess.py` | 실행 설정·IO·전처리 |
| `experiments.md` | 회차별 상세 로그 |

**공식 실행 = Docker only** (`cd ai/experiments` → `docker compose up`). 마운트 경로는 `ai/experiments/.env.example` 참고.

| 문서 | 용도 |
|------|------|
| **본 README** | 목표·진행·실행 방법 |
| **[experiments.md](experiments.md)** | 회차별 **상세** 기록 |

### experiments.md 읽는 법 (실험 1~12 vs 13~)

`experiments.md`는 **한 파일**에 이어지지만, 회차마다 **성격이 다릅니다.** 아래로 구간을 나눠 읽으면 됩니다.

| 구간 | 회차 | 성격 | 무엇을 보나 |
|------|------|------|-------------|
| **Track A 실행 로그** | **1~11** | 노트북 run·ablation | feature/target 확정, p@5·baseline **숫자** |
| **분석** | **12** | 재학습 없음 | Track A metric·이론 상한·L0~L2 해석 |
| **사양·실행** | **13** | Track B export run | `outputs/recipe_lightfm.csv`, B0~B3 |
| **Track B 개선** | **14** | target ablation | subset×bar 분해·H1~H4 |
| **Track B 개선** | **15** | bar-only (0~2 곱) | 천장 std 2×, ρ +0.05 미달 |
| **Track B 개선** | **16** | interaction·bar 곱 재학습 | bar·학습 정합 |
| **Track B v2** | **17~** | 콜드스타트 Base Score | full train, `product_02_row` |
| **Track B v2** | **18** | **L0~L5 지표 재정의** | Go = L0+L1+L2; §[METRICS.md](METRICS.md) |
| **Track B v2** | **19** | **L1 평가 보완** | informative + ρ(pop,bar); Go 통과 |
| **Track B v2 (현재)** | **20** | **Bayesian bar** | ceiling 개수 분리; **채택** |

- **ablation·채택 근거** → §실험 1~11  
- **왜 Go 기준이 바뀌었는지** → §실험 12 → §실험 13 순  
- **지표·Go·bar** → §실험 20 · [METRICS.md](METRICS.md) · README §1.5

---

## 1. 실험 목적 및 목표

### 1.1 목적

- **Track B (1차):** warm 레시피 중 **5점 리뷰 ≥2** 를 선호(y\*)로 두고, catalog **`s_pref`** 로 추천 순위 생성.
- **LightFM hybrid** (prefer WARP + item feature). 조회·스크랩은 **feature만**.
- **Go:** `s_pref` 상위 K에 y\*=1이 얼마나 오는지 — **P@20·NDCG@20·Recall@20** ([METRICS.md](METRICS.md)).
- **Track A (실험 1~12):** hold-out CF — **보류** (이력은 `experiments.md` §1~12).
- 데이터: `data/review_by_llm.csv`, `data/recipe_fix.csv`, `data/recipe_ingredient_alias.csv`

### 1.2 현재 진행 상황 (Track B · §29 R-Go)

| 영역 | 상태 | 비고 |
|------|------|------|
| 실행 환경 | 완료 | `python evaluation.py` |
| **Go 헌장** | **R0~R3** | P@20·NDCG@20·Recall@20 (warm test fold) |
| **§28** | No-Go (구 P0~P3) | 레거시 |
| **§29** | R-Go **No-Go** (0/5×3) | P@20≈0.46·NDCG≈0.49·Recall≈0.23 |
| **export** | 진단 CSV | `recipe_lightfm.csv` 동결 |

베이스라인 실행: `python evaluation.py`. 회차 표 → [experiments.md](experiments.md) §28~29 · 헌장 → [METRICS.md](METRICS.md).

### 1.4 Track A vs Track B

| | Track A (2차 · **다음**) | Track B (**1차 · 현재**) |
|---|---------------|-------------------|
| 과제 | user–item CF hold-out | **선호 레시피 추천** (y\*=n_star5≥2) |
| 점수 | personalized predict | catalog **`s_pref`** 정렬 |
| Go | L0 충족; L1/L2 보류 | **R0~R3** (P@20·NDCG·Recall) |
| 실행 | 노트북 export | `python evaluation.py` (CV Go) |

### 1.5 레거시 Track B (§1~26, 폐기)

Spearman·bar·감성 곱·L0~L5 dual Go는 **코드·헌장에서 제거**. 숫자·맥락만 [experiments.md](experiments.md) §1~26에 보존.

### 1.6 Track A 목표 (2차·보류)

| 층 | 조건 | 상태 |
|----|------|------|
| L0 | random 대비 우위 | **충족** |
| L1/L2 | personalized 인기 이상 / +10% | **보류** |

상세 Mode G/P·이론 상한 → **[experiments.md §실험 12](experiments.md)**.

### 1.3 문서·커밋 정책

| 작업 | `LightFM_Model.ipynb` | `experiments.md` | README | 임시 스크립트 / `outputs/*.json` |
|------|----------------------|------------------|--------|-------------------------|
| **베이스라인 갱신** | **커밋** | 해당 회차 상세 추가 | §1.2·§4·§5 요약 갱신 | 삭제 |
| **탐색 실험만** | 커밋 안 함 (env override) | **상세 결과 추가** | §4 한 줄만 필요 시 | 실행 후 삭제 |

- **상세 숫자·표·JSON** → 항상 `experiments.md`.
- **README** → 팀이 한눈에 보는 스냅샷; 회차마다 전체 복사하지 않음.
- 노트북/스크립트가 실수로 커밋되면 `experiments.md`의 **베이스라인 갱신 여부** + README §5 이력으로 revert 근거.

**베이스라인 갱신 (노트북 커밋 이력)**

| 회차 | 내용 |
|------|------|
| 4~5 | hybrid item feature ablation 경로 |
| **7** | `EXCLUDED_RECIPE_COLUMNS = ["ingredients"]` |
| **7·8** | popularity `log1p` |
| **9·10** | target·가중치 확정 (노트북 default 변경 없음) |
| **17** | 콜드스타트 파이프라인: full train, `product_02_row` default |
| **18** | L0~L5 평가·[METRICS.md](METRICS.md) |
| **19** | L1 informative + ρ(pop,bar); Go 통과 |
| **20** | Bayesian WR bar default (m=3) |

---

## 2. 실행 환경 및 테스트 방법

### 2.1 사전 요구

- Docker Desktop / Docker Engine
- 작업 경로: `ai/experiments/` (루트 compose와 **별도**, 포트 8888)

### 2.2 JupyterLab (대화형)

```powershell
cd ai\experiments
docker compose up --build
# http://localhost:8888 → LightFM_Model.ipynb
docker compose down
```

### 2.3 환경 검증

**빌드**

```powershell
cd ai\experiments
docker compose build
```

**스모크** (warp + precision/recall, 수 초)

```powershell
docker compose run --rm jupyter python -c @"
import numpy as np
from scipy.sparse import csr_matrix
from lightfm import LightFM
from lightfm.evaluation import precision_at_k, recall_at_k
rng = np.random.default_rng(42)
n_users, n_items = 20, 30
rows, cols = rng.integers(0, n_users, 80), rng.integers(0, n_items, 80)
interactions = csr_matrix((np.ones(80, np.float32), (rows, cols)), shape=(n_users, n_items))
model = LightFM(loss='warp', random_state=42)
model.fit(interactions, epochs=2, num_threads=2)
p5 = float(precision_at_k(model, interactions, k=5).mean())
print(f'lightfm ok: precision@5={p5:.4f}')
"@
```

**노트북 E2E** (Unit 1~11)

```powershell
docker compose run --rm jupyter jupyter nbconvert `
  --to notebook `
  --execute /workspace/project/LightFM_Model.ipynb `
  --output /tmp/LightFM_Model.executed.ipynb `
  --ExecutePreprocessor.timeout=600
```

통과: exit 0, `outputs/ablation_report.json`, `outputs/recipe_lightfm.csv` (3,171행).

### 2.4 실험 진행 방식

**A. 베이스라인 확인 / 단일 run**

- 위 E2E 한 번 → `outputs/ablation_report.json` 확인.
- 필요 시 `experiments.md`에 기록.

**B. 탐색 실험 (ablation, multi-seed 등)**

1. **임시** `run_experimentN.ps1` 또는 루프 스크립트 작성.
2. `docker compose run --rm -e SEED=... -e EXCLUDED_RECIPE_COLUMNS=...` 등으로 nbconvert 반복.
3. `outputs/ablation_report.json` → `outputs/expN_....json` 복사.
4. **`experiments.md`에 회차 섹션 작성·갱신** (표, 해석, JSON).
5. 베이스라인 채택 시에만 노트북 default 수정 + 커밋; README §1.2·§4·§5 요약 갱신.
6. 임시 스크립트·`outputs/exp*.json` **삭제** (커밋하지 않음).

**환경 변수 (override)**

| 변수 | 기본 | 용도 |
|------|------|------|
| `SEED` | 42 | 학습·predict |
| `EXCLUDED_RECIPE_COLUMNS` | `ingredients` | feature ablation |
| `POSITIVE_MODE` | `prefer_n_star5_ge2` | WARP matrix 필터 (§29 ablation) |
| `EPOCHS` / `FULL_EPOCHS` | 10 / 30 | CV / full-fit (`evaluation.py`) |

### 2.5 노트북 Unit

| Unit | 내용 |
|------|------|
| 1 | 설정·env |
| 2~4 | 데이터·Dataset (전 카탈로그) |
| 5 | prefer WARP matrix · item features |
| 6~7 | full train |
| 11 | catalog `s_pref` export → `recipe_lightfm.csv` |
| 9 | CV Go: `python evaluation.py` |

### 2.6 파일

| 파일 | 역할 |
|------|------|
| [`LightFM_Model.ipynb`](LightFM_Model.ipynb) | full-fit export 노트북 |
| `evaluation.py` | R0~R3 CV · Go (`python evaluation.py`) |
| `scoring.py` | `s_pref` predict · export DataFrame |
| `experiments.md` | 실험 상세 로그 (§1~26 레거시 · §28~29 현재) |
| `README.md` | 본 문서 |
| `METRICS.md` | R0~R3 헌장 |
| `config.py` | env·시드·경로 |
| `data_io.py` | CSV load/export·JSON 리포트 |
| `preprocess.py` | 전처리·prefer labels·LightFM feature |
| `outputs/recipe_lightfm.csv` | 전 카탈로그 export (Go 전 동결 가능) |
| `outputs/prefer_eval_report.json` | CV Go 리포트 |

---

## 3. LLM 구축 시 동작 예시

### 3.1 베이스라인 1 run

```powershell
cd ai\experiments
docker compose run --rm jupyter jupyter nbconvert `
  --to notebook --execute /workspace/project/LightFM_Model.ipynb `
  --output /tmp/out.ipynb --ExecutePreprocessor.timeout=600
```

### 3.2 multi-seed 탐색 (실험 후 스크립트 삭제)

```powershell
$Seeds = @(42, 123, 456, 789, 1024)
foreach ($seed in $Seeds) {
  docker compose run --rm -e "SEED=$seed" -e "SENTIMENT_WEIGHT=2" `
    jupyter jupyter nbconvert `
      --to notebook --execute /workspace/project/LightFM_Model.ipynb `
      --output /tmp/out.ipynb --ExecutePreprocessor.timeout=600
  Copy-Item outputs/ablation_report.json "outputs/exp11_s${seed}.json" -Force
}
# → metrics를 experiments.md §실험 11에 정리 → 스크립트·runs 삭제
```

### 3.3 JSON에서 지표 읽기

```python
import json
from pathlib import Path
r = json.loads(Path("outputs/ablation_report.json").read_text(encoding="utf-8"))
print(r["track_b_eval"]["l2_spearman_informative"], r["decision"])
```

### 3.4 LLM 체크리스트

1. 베이스라인 갱신인가? → 노트북 default + `experiments.md` + README §1.2·§4
2. 탐색만인가? → `experiments.md`만 + env; 노트북·스크립트 커밋 금지
3. WARP drift: 동일 설정 재실행 시 seed별 지표 변동 가능 → **당번 fresh run**을 비교 기준

---

## 4. 실험 회차 개요 (1~22)

상세 → **[experiments.md](experiments.md)** 해당 §. **1~12 = Track A(보류) / 13~16 = Track B v1 / 17+ = 콜드스타트**

| # | 목적 (한 줄) | 결론 | 비고 |
|---|-------------|------|------|
| 1~10 | CF hybrid ablation | feature/target 확정 | 이력 |
| 11~12 | baseline·평가 분석 | p@5 Go 폐기 | Track A 보류 |
| 13~16 | Track B v1 export·ablation | B0·B3 통과; B2 미달 | 산출물 폐기 |
| **17** | **콜드스타트 재정의·정리** | 파이프라인 정리 | full train |
| **18** | **L0~L5·Cohen 0.30 근거** | L0·L2 OK; L1 0/5 (구 축) | calibration |
| **19** | **L1 informative·bar 정합** | **Go 통과** | 공정 순위 평가 |
| **20** | **Bayesian average bar** | **채택** (ceiling ρ↑, Go 유지) | m=3 |
| **21** | **독립 감성 재분석 + 혼합 ablation** | T0 Go·uniq↑; **T1 미채택** | MIX_GAMMA=0 |
| **22** | **평가 헌장 이축 Go** | **채택** L1c+L2c(0.25) | 모델 ceiling 경계 4/5 |

**스냅샷**

- **Go:** `L0 ∧ L1i ∧ L2i ∧ L1c ∧ L2c(≥0.25)` — 헌장 **채택** (실험 22)
- **bar:** WR on `mean(star_02×sentiment_02)`; `BAR_MODE=mean`으로 레거시 mean 가능
- **원칙:** 상대 순위 구분력 (Spearman·unique/슬라이스). §[METRICS.md](METRICS.md)
- **잔여:** ceiling ρ를 **전 seed ≥0.25**로 안정화 후 stretch **0.30**
- **다음:** ceiling ρ 개선 (기준 하향 없음)

---

## 5. 업데이트 및 수정 이력

### 2026-07-14 (실험 22)

- **Go 헌장:** informative+ceiling **이축** (`L2c≥0.25`, L1c vs pop). [METRICS.md](METRICS.md) · §[experiments.md](experiments.md) 실험 22.
- **현 모델:** dual single-seed **4/5** (ceiling 경계); stretch 0.30 미달.

### 2026-07-14 (실험 21)

- **Goal0:** v1_all5 uniq 24→295 (독립 감성 재분석, 학습 전).
- **T0/T1:** 5-seed Go 유지; T1은 informative ρ↑·ceiling ρ↓ → **혼합 미채택** (`MIX_GAMMA=0`). §[experiments.md](experiments.md) 실험 21.

### 2026-07-14 (코드 정리 · §29 축)

- **헌장:** R0~R3만 유지 ([METRICS.md](METRICS.md)). L0~L5·P0~P3·Spearman/bar 코드 **제거**.
- **core:** `preprocess` prefer WARP · `scoring` predict+export · `evaluation` CV Go.
- **삭제:** `exp28_prefer_threshold.py`, `exp29_star_only_prefer.py`, `TRACK_B_STATUS.md`.
- **실행:** Go = `python evaluation.py`; 노트북 = full-fit export.

### 2026-07-14 (실험 20)

- **bar:** IMDb식 Bayesian average (m=3) on product mean; default `BAR_MODE=bayesian`.
- **20A/20B:** 라벨 개수 분리 + 재학습 5-seed Go 유지·ceiling ρ≈0.24~0.29. §[experiments.md](experiments.md) 실험 20.

### 2026-07-14 (실험 19)

- **L1:** informative + `Spearman(popularity, bar)` 정합; 구 `Spearman(ŷ, pop)` 버그 수정.
- **calibration (5-seed):** L0·L1·L2 통과 → **Go true**. §[experiments.md](experiments.md) 실험 19 — 공정 순위 평가·**다음=ceiling(실험 20)** 명시.
- **METRICS.md / README:** L1 헌장·스냅샷·해석 범위 갱신.

### 2026-07-13 (실험 18)

- **L0~L5:** [METRICS.md](METRICS.md) — Cohen 0.30 근거, Go = L0+L1+L2, L4 DATASET_EXCEPTION.
- **`evaluation.py`:** R0~R3 CV (`run_prefer_cv`, `python evaluation.py`).
- **calibration (5-seed):** L0·L2 통과, L1 0/5 vs popularity → Go false. §[experiments.md](experiments.md) 실험 18.

### 2026-07-13 (모듈 분리)

- **모듈 5종:** `config.py`, `data_io.py`, `preprocess.py`, `scoring.py`, `evaluation.py` (`catalog_eval`·`score_02` 통합·rename)
- **노트북:** 오케스트레이션만 유지 (fit/predict/export 호출)

### 2026-07-13

- **폴더 분리:** 코드·데이터·노트북·산출물 → `ai/recommendation/` (`data/`, `outputs/`); Docker 실행 환경 → `ai/experiments/`.
- **실험 17:** Track B 콜드스타트 재정의 — full train, `product_02_row` default. B0·B3 통과, B2 미달 (ρ=-0.052).

### 2026-07-10

- **실험 16:** `scoring.py`, `product_02_row` target·B3 bar, `EXP16` 2-run (T0/T1). H2·H3·H4 지지 → **17+ `product_02_row` + B3 bar** 확정. H1 ceiling +0.05·B2 Go 0.30 미달.
- **실험 15:** `bar_eval.py` — 0~2 스케일 bar 4종, 고정 `ŷ` bar-only. B2 vs B3 해석·**17+ `mean(star×sent)` (B3) 방향** 기록.
- **실험 14:** `TARGET_MODE` 4종 ablation, `decomposed_track_b_metrics`, `plot_decompose` / `plot_exp14_compare`. B2 미달 유지; subset 신호(H2) 지지; 1차 채택 target `star_only` (탐색, 노트북 default 미변경).
- **실험 13 실행:** `evaluation.py`, Unit 11, `recipe_lightfm.csv` (3,171행, `y_hat_linear` 선형보정 컬럼). B0·B3 통과, B2 미달 (MAE raw 1.6→linear 0.17, R²≈0, Spearman≈0).
- **실험 13 (리뷰-only):** target/bar = 리뷰 점수만; view/scrap=feature; 레거시 fallback bar 폐기; 서비스→실험 정합 (코드 후속).
- **실험 12:** 평가 Mode(G/P)·이론 상한·Track A L0~L2. 구 **p@5≥0.05** 폐기.
- **실험 11:** Unit 10 Random / train-popularity baseline (`baseline_eval.py`).
- 상세 실험 기록 **`experiments.md`** (실험 1~13).

### 2026-07-09

- Docker 공식 실행, 실험 1~10 수행 시작.

---

## 부록

**보안:** JupyterLab 토큰 비활성 — 외부 노출 금지.

**Windows 로컬 (비공식, import만):** Unit 1은 `LIGHTFM_RUNTIME=linux-docker` 필수. WARP는 Docker에서만 안정.
