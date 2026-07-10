# LightFM Experiments

LightFM 하이브리드 추천 오프라인 실험 환경입니다. **공식 실행 = Docker only.**

| 문서 | 용도 |
|------|------|
| **본 README** | 전체 목표·진행 상황·실행 방법·실험 **개요** |
| **[experiments.md](experiments.md)** | 회차별 **상세** 기록 (설정·표·JSON·해석) — **실험할 때마다 여기만 갱신** |

### experiments.md 읽는 법 (실험 1~12 vs 13~)

`experiments.md`는 **한 파일**에 이어지지만, 회차마다 **성격이 다릅니다.** 아래로 구간을 나눠 읽으면 됩니다.

| 구간 | 회차 | 성격 | 무엇을 보나 |
|------|------|------|-------------|
| **Track A 실행 로그** | **1~11** | 노트북 run·ablation | feature/target 확정, p@5·baseline **숫자** |
| **분석** | **12** | 재학습 없음 | Track A metric·이론 상한·L0~L2 해석 |
| **사양·실행** | **13** | Track B export run | `recipe_lightfm.csv`, B0~B3 |
| **Track B 개선** | **14** | target ablation | subset×bar 분해·H1~H4 |
| **Track B 개선** | **15** | bar-only (0~2 곱) | 천장 std 2×, ρ +0.05 미달 |
| **Track B 개선** | **16** | interaction·bar 곱 재학습 | bar·학습 정합 |
| **Track B 개선** | **17~** | `mean(star×sent)` bar/target (B3) | 실험 16 이후 기본 축 |

- **ablation·채택 근거** → §실험 1~11  
- **왜 Go 기준이 바뀌었는지** → §실험 12 → §실험 13 순  
- **지금 무엇을 구현할지** → §실험 13 · README §1.5

---

## 1. 실험 목적 및 목표

### 1.1 목적

- **LightFM hybrid**(CF + item feature)로 레시피 **점수·추천**을 검증한다.
- **1차 목표 (Track B):** 전 카탈로그(~3,100)에 **추정 리뷰 점수** `ŷ` 부여. **목표 점수 = 리뷰만**; 조회·스크랩은 **feature**. 서비스도 실험 정의에 맞춤 (코드 후속).
- **Track A (실험 1~12, 전제 검증):** `review_by_llm.csv` proxy(~563 item) hold-out CF. **L0 통과** — 상세 실행 로그는 §실험 1~11, 해석은 §실험 12.
- 데이터: interaction `review_by_llm.csv` / feature `recipe_fix.csv`, `recipe_ingredient_alias.csv`.

### 1.2 현재 진행 상황 (실험 16 실행 완료)

| 영역 | 상태 | 비고 |
|------|------|------|
| 실행 환경 | 완료 | Docker, `LightFM_Model.ipynb` Unit 1~11 |
| hybrid·feature·target | **확정** | 실험 7~10 → Track B 재사용 |
| **Track A** | **전제 완료 (L0)** | random 우위 5/5; L1/L2 **보류** |
| **Track B** | **export + 0~2 곱 재학습** | B0·B3 통과; B2 미달; **T1 ALL·subset ρ &gt; T0** |
| **17+ 축** | **`product_02_row` + B3 bar** | H2·H3·H4 지지; H1 ceiling +0.05 미달 |

상세 → **[experiments.md §실험 16](experiments.md)**.

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
| **B2** | **1차 Go** — **warm:** NDCG@50(ŷ) ≥ NDCG@50(`score_review`) 또는 Spearman **≥ 0.30** |
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

| 작업 | `LightFM_Model.ipynb` | `experiments.md` | README | 임시 스크립트 / `runs/` |
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
docker compose run --rm lightfm-jupyter python -c @"
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
docker compose run --rm lightfm-jupyter jupyter nbconvert `
  --to notebook `
  --execute LightFM_Model.ipynb `
  --output /tmp/LightFM_Model.executed.ipynb `
  --ExecutePreprocessor.timeout=600
```

통과: exit 0, Unit 9 → `runs/ablation_report.json` 생성, Unit 11 → `recipe_lightfm.csv` 생성, stderr traceback 없음.

### 2.4 실험 진행 방식

**A. 베이스라인 확인 / 단일 run**

- 위 E2E 한 번 → `runs/ablation_report.json` 확인.
- 필요 시 `experiments.md`에 기록.

**B. 탐색 실험 (ablation, multi-seed 등)**

1. **임시** `run_experimentN.ps1` 또는 루프 스크립트 작성.
2. `docker compose run --rm -e SEED=... -e EXCLUDED_RECIPE_COLUMNS=...` 등으로 nbconvert 반복.
3. `runs/ablation_report.json` → `runs/expN_....json` 복사.
4. **`experiments.md`에 회차 섹션 작성·갱신** (표, 해석, JSON).
5. 베이스라인 채택 시에만 노트북 default 수정 + 커밋; README §1.2·§4·§5 요약 갱신.
6. 임시 스크립트·`runs/exp*.json` **삭제** (커밋하지 않음).

**환경 변수 (override)**

| 변수 | 기본 | 용도 |
|------|------|------|
| `SEED` | 42 | split·학습 |
| `EXCLUDED_RECIPE_COLUMNS` | `ingredients` | feature ablation |
| `STAR_WEIGHT` / `SENTIMENT_WEIGHT` | 1.0 (`ratio_1_2`는 2.0) | interaction 가중 |
| `TARGET_MODE` | `star_sentiment_sum` | `star_sentiment_sum` \| `sentiment_only` \| `star_only` \| `ratio_1_2` \| **`product_02_row`** |
| `EXPORT_TAG` | `TARGET_MODE` | export CSV·JSON suffix (`recipe_lightfm_exp16_<tag>.csv` 등) |
| `EXP14` | (unset) | `1`이면 `experiment: 14_track_b_target_<tag>` |
| `EXP16` | (unset) | `1`이면 `experiment: 16_track_b_<tag>`, exp16 export |
| `BASELINE_ONLY` | (unset) | `1`이면 Unit 5b·7·8·9 스킵, Unit 10만 실행 |

### 2.5 노트북 Unit

| Unit | 내용 |
|------|------|
| 1 | 설정·env |
| 2~4 | 데이터·Dataset |
| 5 / 5b | interaction · item features |
| 6 | split |
| **10** | **Random / train-popularity baseline** (`baseline_eval.py`) |
| 7~8 | 학습 · 평가 |
| **11** | **Track B export** (`recipe_lightfm.csv`, `catalog_eval`) |
| 9 | 리포트 JSON (`track_b_eval` 포함) |

### 2.6 파일

| 파일 | 역할 |
|------|------|
| `LightFM_Model.ipynb` | 베이스라인 (커밋) |
| `experiments.md` | **실험 상세 로그** (커밋) |
| `README.md` | 개요 (커밋) |
| `docker-compose.yml`, `Dockerfile`, `requirements.txt`, `*.csv` | 실행·데이터 |
| `baseline_eval.py` | bar baseline 평가 (Unit 10) |
| `catalog_eval.py` | Track B B0~B3 (Unit 11) |
| `bar_eval.py` | 실험 15 bar-only (0~2 곱 bar, 재학습 없음) |
| `score_02.py` | 0~2 스케일 공유 (`star_02`, `sentiment_02`, row product) |
| `plot/` | 차트 스크립트 (`metrics.py`, `plot_decompose.py`, `plot_exp14_compare.py`, `plot_exp15_bar_compare.py`, **`plot_exp16_compare.py`**) → `figures/` |
| `figures/` | 산점도 PNG·지표 txt·`exp14_*`·`exp15_bar_*`·**`exp16_*`** CSV/PNG |
| `recipe_lightfm.csv` | 전 카탈로그 점수 export (T0 legacy; `recipe_lightfm_exp16_<tag>.csv` 병행) |
| `runs/` | 임시 JSON (비커밋 권장) |

---

## 3. LLM 구축 시 동작 예시

### 3.1 베이스라인 1 run

```powershell
cd ai\experiments
docker compose run --rm lightfm-jupyter jupyter nbconvert `
  --to notebook --execute LightFM_Model.ipynb `
  --output /tmp/out.ipynb --ExecutePreprocessor.timeout=600
```

### 3.2 multi-seed 탐색 (실험 후 스크립트 삭제)

```powershell
$Seeds = @(42, 123, 456, 789, 1024)
foreach ($seed in $Seeds) {
  docker compose run --rm -e "SEED=$seed" -e "SENTIMENT_WEIGHT=2" `
    lightfm-jupyter jupyter nbconvert `
      --to notebook --execute LightFM_Model.ipynb `
      --output /tmp/out.ipynb --ExecutePreprocessor.timeout=600
  Copy-Item runs/ablation_report.json "runs/exp11_s${seed}.json" -Force
}
# → metrics를 experiments.md §실험 11에 정리 → 스크립트·runs 삭제
```

### 3.3 JSON에서 지표 읽기

```python
import json
from pathlib import Path
r = json.loads(Path("runs/ablation_report.json").read_text(encoding="utf-8"))
print(r["metrics"]["precision@5"], r.get("excluded_recipe_columns"))
```

### 3.4 LLM 체크리스트

1. 베이스라인 갱신인가? → 노트북 default + `experiments.md` + README §1.2·§4
2. 탐색만인가? → `experiments.md`만 + env; 노트북·스크립트 커밋 금지
3. WARP drift: 동일 설정 재실행 시 seed별 p@5 ±0.002 가능 → **당번 fresh run**을 비교 기준

---

## 4. 실험 회차 개요 (1~16)

상세 → **[experiments.md](experiments.md)** 해당 §. **1~11 = Track A / 12 = 분석 / 13~16 = Track B**

| # | 목적 (한 줄) | 결론 | 비고 |
|---|-------------|------|------|
| 1~10 | CF hybrid ablation | feature/target 확정 | Track B 재사용 |
| 11 | random + train 인기 | mean 인기 > LightFM | Unit 10 |
| 12 | 평가·이론 상한·L0~L2 | 0.05 폐기 | Track A 사양 |
| **13** | **Track B export·eval** | **B0·B3 통과; `recipe_lightfm.csv`** | B2 미달 |
| **14** | **target 4종 × subset 분해** | **B2 미달; H2 지지; Simpson 해석** | 탐색 `star_only` |
| **15** | **bar-only 0~2 곱** | **천장 std 2×; B3 bar 후보** | 고정 ŷ |
| **16** | **0~2 곱 interaction·B3 재학습** | **H2·H3·H4 지지; 17+ B3 축 확정** | B2 Go 미달 |
| **17~** (계획) | B2 Go·multi-seed·ETL | ceiling +0.05·0.30 | `product_02_row` 기본 |

**스냅샷**

- **Track A:** L0 통과 — LightFM ≠ 무의미, **1차 Go 아님**
- **Track B:** B0·B3 통과, B2 미달 — **T1 product가 T0 전 subset ρ 우위**
- **다음:** **17** B2 튜닝·ETL/Neo4j `REVIEW_RANK_SCORE` 반영 검토

---

## 5. 업데이트 및 수정 이력

### 2026-07-10

- **실험 16:** `score_02.py`, `product_02_row` target·B3 bar, `EXP16` 2-run (T0/T1). H2·H3·H4 지지 → **17+ `product_02_row` + B3 bar** 확정. H1 ceiling +0.05·B2 Go 0.30 미달.
- **실험 15:** `bar_eval.py` — 0~2 스케일 bar 4종, 고정 `ŷ` bar-only. B2 vs B3 해석·**17+ `mean(star×sent)` (B3) 방향** 기록.
- **실험 14:** `TARGET_MODE` 4종 ablation, `decomposed_track_b_metrics`, `plot_decompose` / `plot_exp14_compare`. B2 미달 유지; subset 신호(H2) 지지; 1차 채택 target `star_only` (탐색, 노트북 default 미변경).
- **실험 13 실행:** `catalog_eval.py`, Unit 11, `recipe_lightfm.csv` (3,171행, `y_hat_linear` 선형보정 컬럼). B0·B3 통과, B2 미달 (MAE raw 1.6→linear 0.17, R²≈0, Spearman≈0).
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
