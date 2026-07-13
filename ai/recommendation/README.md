# LightFM Track B — `ai/recommendation`

코드·데이터·노트북·실험 기록은 **본 폴더**에 두고, **Docker 실행 환경**은 [`../experiments/`](../experiments/)에 둡니다.

| 경로 | 내용 |
|------|------|
| `data/` | 입력 CSV (`review_by_llm.csv`, `recipe_fix.csv`, …) |
| `outputs/` | `recipe_lightfm.csv`, `ablation_report.json` |
| `LightFM_Model.ipynb` | 실행 노트북 |
| `evaluation.py`, `scoring.py` | 평가·스코어 유틸 |
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
| **Track B v2 (현재)** | **17~** | 콜드스타트 Base Score | full train, B0~B3, `product_02_row` |

- **ablation·채택 근거** → §실험 1~11  
- **왜 Go 기준이 바뀌었는지** → §실험 12 → §실험 13 순  
- **지금 무엇을 구현할지** → §실험 17 · README §1.5

---

## 1. 실험 목적 및 목표

### 1.1 목적

- **1차 목표 (Track B):** 전 카탈로그(~3,171) 레시피에 **Base Score(ŷ)** 부여 — 콜드스타트 점수 추정.
- **LightFM hybrid**(CF + item feature)로 학습·predict. **목표 점수 = 리뷰만**; 조회·스크랩은 **feature**.
- **Track A (실험 1~12):** hold-out CF — **보류** (이력은 §실험 1~12).
- 데이터: `data/review_by_llm.csv`, `data/recipe_fix.csv`, `data/recipe_ingredient_alias.csv`

### 1.2 현재 진행 상황 (실험 17 완료)

| 영역 | 상태 | 비고 |
|------|------|------|
| 실행 환경 | 완료 | Docker, `LightFM_Model.ipynb` |
| **Track B v2** | **파이프라인 정리** | full train, `product_02_row` default |
| 평가 | B0·B3 통과, **B2 미달** | Spearman(ŷ,bar)=-0.052 |
| dead code | 정리 | `baseline_eval`, `bar_eval`, `plot/`, `figures/`, `samples/` 삭제 |

상세 → **[experiments.md §실험 17](experiments.md)**.

### 1.4 Track A vs Track B

| | Track A (2차) | Track B (**1차**) |
|---|---------------|-------------------|
| 과제 | user–item CF hold-out | **전 카탈로그 item 점수** |
| item | ~563 | **~3,100** |
| Go | L0 충족; L1/L2 보류 | **B0~B3** (§1.5) |
| 노트북 | `item_ids` = review만 | **13b**에서 전체 fit 예정 |

### 1.5 Track B 목표 (실험 13 — 리뷰 only)

**점수 정의**

| | 공식 | 비고 |
|---|------|------|
| 학습 `y` (현재) | `star + sentiment` | 실험 13~15 baseline; **17+ 기본 = `product_02_row`** |
| 관측 / bar `score_review` (현재) | `REVIEW_RANK_SCORE` (= 별점·감성 **합**) | T0 legacy; **17+ = `mean(star_02×sent_02)` (B3)** |
| **확정 (실험 16→17+)** | **0~2:** `star_02×sent_02` 행 단위 곱; bar = **`mean(star_02×sent_02)`** (B3) | §실험 16 |
| export `ŷ` | LightFM predict — **추정 리뷰 점수** | |
| view/scrap | **feature만** (target·bar·서비스 점수에 미포함) | |

**레거시 Neo4j fallback (리뷰+조회+스크랩) — 사용 안 함.** 정합: **서비스 → 실험** (코드 후속).

| 층 | 조건 |
|----|------|
| **B0** | 전 item 유한 `ŷ` (cold 포함) |
| **B2** | **1차 Go** — warm: Spearman(ŷ, bar) **≥ 0.30** |
| **B3** | warm: train 리뷰 신호와 Spearman **≥ 0.30** |
| **B4** | full vs view/scrap feature 제외 ablation (warm) |
| **B1′** | cold vs 인기 — **진단 only**, Go 아님 |

cold는 리뷰 정답 없음 → **B0 + warm B2/B3**로 간접 검증. 상세 → **[experiments.md §실험 13](experiments.md)**.

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
| **17** | 콜드스타트 파이프라인: full train, `product_02_row` default, CF path 제거 |

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
| `STAR_WEIGHT` / `SENTIMENT_WEIGHT` | 1.0 (`ratio_1_2`는 2.0) | interaction 가중 |
| `TARGET_MODE` | **`product_02_row`** | interaction target |

### 2.5 노트북 Unit

| Unit | 내용 |
|------|------|
| 1 | 설정·env |
| 2~4 | 데이터·Dataset (전 카탈로그) |
| 5 / 5b | interaction · item features |
| 6 | full train (`train = interactions`) |
| 7 | LightFM 학습 |
| 11 | catalog predict → `outputs/recipe_lightfm.csv` + `evaluation` |
| 9 | 리포트 JSON (`track_b_eval`, B0~B3 decision) |

### 2.6 파일

| 파일 | 역할 |
|------|------|
| [`LightFM_Model.ipynb`](LightFM_Model.ipynb) | 실행 노트북 |
| `experiments.md` | **실험 상세 로그** |
| `README.md` | 본 문서 |
| `data/*.csv` | 입력 데이터 |
| `evaluation.py` | Track B B0~B3, MAE/RMSE |
| `scoring.py` | 0~2 스케일·interaction target |
| `config.py` | env·시드·경로 |
| `data_io.py` | CSV load/export·JSON 리포트 |
| `preprocess.py` | 전처리·LightFM feature |
| `outputs/recipe_lightfm.csv` | 전 카탈로그 Base Score export |
| `outputs/ablation_report.json`, `outputs/exp*.json` | 임시 JSON (비커밋) |

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
print(r["track_b_eval"]["warm_spearman_review"], r["decision"])
```

### 3.4 LLM 체크리스트

1. 베이스라인 갱신인가? → 노트북 default + `experiments.md` + README §1.2·§4
2. 탐색만인가? → `experiments.md`만 + env; 노트북·스크립트 커밋 금지
3. WARP drift: 동일 설정 재실행 시 seed별 지표 변동 가능 → **당번 fresh run**을 비교 기준

---

## 4. 실험 회차 개요 (1~17)

상세 → **[experiments.md](experiments.md)** 해당 §. **1~12 = Track A(보류) / 13~16 = Track B v1 / 17+ = 콜드스타트**

| # | 목적 (한 줄) | 결론 | 비고 |
|---|-------------|------|------|
| 1~10 | CF hybrid ablation | feature/target 확정 | 이력 |
| 11~12 | baseline·평가 분석 | p@5 Go 폐기 | Track A 보류 |
| 13~16 | Track B v1 export·ablation | B0·B3 통과; B2 미달 | 산출물 폐기 |
| **17** | **콜드스타트 재정의·정리** | **파이프라인 정리; B2 미달** | full train, `product_02_row` |
| **18~** (계획) | B2 튜닝·multi-seed | Spearman ≥ 0.30 | |

**스냅샷**

- **Track B v2:** B0·B3 통과, B2 미달 (ρ=-0.052)
- **다음:** B2 튜닝, 실험 18 multi-seed stability

---

## 5. 업데이트 및 수정 이력

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
