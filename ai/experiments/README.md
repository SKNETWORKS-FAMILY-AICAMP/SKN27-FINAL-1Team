# LightFM Experiments

LightFM 하이브리드 추천 오프라인 실험 환경입니다. **공식 실행 = Docker only.**

| 문서 | 용도 |
|------|------|
| **본 README** | 전체 목표·진행 상황·실행 방법·실험 **개요** |
| **[experiments.md](experiments.md)** | 회차별 **상세** 기록 (설정·표·JSON·해석) — **실험할 때마다 여기만 갱신** |

---

## 1. 실험 목적 및 목표

### 1.1 목적

- **LightFM hybrid**(CF + item feature)가 proxy 리뷰 interaction으로 오프라인 추천에 쓸 만한지 검증한다.
- 학습 데이터: `review_by_llm.csv` (`group_id`, `recipe_id`, 별점·감성).
- item feature: `recipe_fix.csv` 등 (전체 레시피 feature, interaction은 ~563개 item).
- ExtraTrees / Neo4j `review_rank_score` 랭킹은 **대체 대상**이며 본 실험 범위 밖.

### 1.2 현재 진행 상황 (실험 10까지)

| 영역 | 상태 | 채택 (노트북 기본) |
|------|------|-------------------|
| 실행 환경 | 완료 | Docker, `LightFM_Model.ipynb` Unit 1~9 |
| hybrid pipeline | 완료 | `build_item_features` + warp |
| item feature | **확정** | `ingredients` 제외, `view_count`/`scrap_count` **log1p** |
| interaction target | **확정** | `star_sentiment_sum`, 가중치 **1:1** |
| loss / 학습 | 고정 | warp, 30 epoch, test 0.2 |
| Go (p@5 ≥ 0.05) | **전 회차 No-Go** | 절대 기준 미달 — ablation·seed로 상대 비교 |

**다음 후보:** Unit 10 인기 baseline, 서비스 POC (본 README 범위 밖).

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

**노트북 E2E** (Unit 1~9)

```powershell
docker compose run --rm lightfm-jupyter jupyter nbconvert `
  --to notebook `
  --execute LightFM_Model.ipynb `
  --output /tmp/LightFM_Model.executed.ipynb `
  --ExecutePreprocessor.timeout=600
```

통과: exit 0, Unit 9 → `runs/ablation_report.json` 생성, stderr traceback 없음.

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
| `STAR_WEIGHT` / `SENTIMENT_WEIGHT` | 1.0 | interaction 가중 |

### 2.5 노트북 Unit

| Unit | 내용 |
|------|------|
| 1 | 설정·env |
| 2~4 | 데이터·Dataset |
| 5 / 5b | interaction · item features |
| 6~8 | split · 학습 · 평가 |
| 9 | 리포트 JSON |
| 10 | 인기 baseline (미구현) |

### 2.6 파일

| 파일 | 역할 |
|------|------|
| `LightFM_Model.ipynb` | 베이스라인 (커밋) |
| `experiments.md` | **실험 상세 로그** (커밋) |
| `README.md` | 개요 (커밋) |
| `docker-compose.yml`, `Dockerfile`, `requirements.txt`, `*.csv` | 실행·데이터 |
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

## 4. 실험 회차 개요 (1~10)

상세 표·JSON·해석 → **[experiments.md](experiments.md)** 해당 §.

| # | 목적 (한 줄) | 결론 | baseline 갱신 |
|---|-------------|------|---------------|
| 1 | `star_sentiment_sum`+WARP 100ep | p@5 0.0079, 과적합 | — |
| 2 | 별점/감성/합산·epoch | sentiment only 소폭 우세 | — |
| 3 | view/scrap popularity ablation | view 포함이 유리 | — |
| 4 | 컬럼 1개씩 제외 (13) | `cooking_method` critical | hybrid 방법 |
| 5 | 2컬럼 조합 (32) | ingr+cooking_method 1위(42) | — |
| 6 | exp5 seed 검증 | candidate 보류 (1/3) | — |
| 7 | ingredients_only vs 5c | **ingredients만 제외** | **Yes** |
| 8 | log1p (view/scrap) | log1p 채택 | **Yes** (§7과 통합) |
| 9 | target 4종 × 5 seed | **star_sentiment_sum** | 선택 확정 |
| 10 | sent 가중 1:2, 1:3 | **1:1 유지** | — |

**현재 베이스라인 (실험 10 Phase A 기준)**

- feature: `ingredients` 제외, log1p popularity  
- target: `star + sentiment`, weights 1:1, warp, 30ep  
- mean p@5 (5 seed): **0.0083** — Go 미달  

---

## 5. 업데이트 및 수정 이력

### 2026-07-10

- README를 **전체 개요·운행 가이드**로 재구성.
- `LIGHTFM_NOTEBOOK_EXECUTION_PLAN.md`, `lightfm_recommendation_plan.md` 제거 → README로 통합.
- 상세 실험 기록은 **`experiments.md` 유지** (실험 1~10).

### 2026-07-09

- Docker 공식 실행, 실험 1~10 수행 시작.

---

## 부록

**보안:** JupyterLab 토큰 비활성 — 외부 노출 금지.

**Windows 로컬 (비공식, import만):** Unit 1은 `LIGHTFM_RUNTIME=linux-docker` 필수. WARP는 Docker에서만 안정.
