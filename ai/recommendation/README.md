# LightFM 추천 모델 — `ai/recommendation`

콜드스타트(히스토리 없는 유저)를 위한 **catalog 기본 추천 엔진**. LightFM hybrid 모델로 전체 3171 레시피에 대한 선호 점수를 생성하고, 점수 순으로 추천합니다.

---

## Quick Start

### 학습 실행 (Docker)

```powershell
cd ai\experiments
docker compose run --rm jupyter python evaluation.py
```

- Go 판정 (R0~R2 warm-fold CV) + full-catalog 진단 + export 실행
- 산출물: `outputs/recipe_lightfm.csv`, `outputs/prefer_eval_report.json`

### 노트북 실행 (대화형)

```powershell
cd ai\experiments
docker compose up --build
# http://localhost:8888 → LightFM_Model.ipynb
```

### 환경 검증 (스모크 테스트)

```powershell
cd ai\experiments
docker compose run --rm jupyter python -c "from lightfm import LightFM; print('ok')"
```

---

## 폴더 구조

```
ai/recommendation/
├── config.py              # 설정 (seed, epochs, paths, env override)
├── data_io.py             # CSV 로드/저장, JSON 리포트
├── preprocess.py          # 전처리, interactions, item features 구축
├── scoring.py             # catalog predict, export DataFrame 생성
├── evaluation.py          # CV Go (R0~R2) + full-catalog 진단
├── LightFM_Model.ipynb    # full-fit export 오케스트레이션 노트북
├── data/                  # 입력 CSV (review_by_llm, recipe_fix, alias)
├── outputs/               # 산출물 (recipe_lightfm.csv, JSON 리포트)
└── docs/                  # 문서
    ├── EXPERIMENTS.md     # 실험 §1~31 상세 기록
    └── METRICS.md         # 평가 지표 헌장 + 달성 수치
```

---

## 문서 안내

| 문서 | 역할 |
|------|------|
| **본 README** | 실행 방법, 구조, 운영 안내 |
| [`docs/METRICS.md`](docs/METRICS.md) | 평가 지표 정의, Go 조건, 현재 달성 수치 |
| [`docs/EXPERIMENTS.md`](docs/EXPERIMENTS.md) | 실험 §1~31 전체 상세 이력 + Phase 1 완료 요약 |

---

## 산출물

### `outputs/recipe_lightfm.csv` (3171행)

서비스에서 사용하는 catalog 추천 테이블.

| 컬럼 | 설명 |
|------|------|
| `recipe_id` | 레시피 ID |
| `recipe_name` | 레시피명 |
| `y_hat` / `s_pref` | LightFM catalog predict 점수 |
| `prefer_rank` | 점수 내림차순 전체 순위 (1=최고) |
| `is_warm` | 1=리뷰 있음(563), 0=cold(2608) |
| `y_prefer` | warm: 0/1 (y*), cold: -1 |
| `prefer_hat` | 모델 추정 선호 (t_star 기준) |
| `n_star5` | 5점 리뷰 수 |

**서비스 연동:** `prefer_rank` 상위 N개를 신규/무히스토리 유저에게 노출.

### `outputs/prefer_eval_report.json`

CV Go 결과 + full-catalog 진단 수치.

---

## 환경 변수

| 변수 | 기본값 | 용도 |
|------|--------|------|
| `SEED` | 42 | 학습·predict |
| `EPOCHS` | 30 | full-fit epoch 수 |
| `NUM_THREADS` | 2 | LightFM 병렬 |
| `POSITIVE_MODE` | `prefer_n_star5_ge2` | WARP matrix 필터 |
| `EXCLUDED_RECIPE_COLUMNS` | `ingredients` | feature 제외 컬럼 |

---

## 서비스 연동 (다음 단계)

### 1. 학습 파이프라인 스크립트화

노트북 → `train.py`로 전환. 모델 아티팩트 저장:
- `model.pkl` (LightFM 임베딩)
- `item_features.pkl` (cold item 점수용)
- `id_maps.pkl` (recipe_id ↔ 내부 인덱스)

### 2. 추론 서비스 모듈

```python
# inference.py 개요
model + maps + features 로드 → predict(user_idx, item_idxs) → Top-K
```

- cold user → catalog (`__catalog__` user) 점수
- warm user → 해당 `group_id`로 개인화 predict

### 3. 개인화 CF

유저 선호 데이터 축적 → 기존 데이터에 추가 → 배치 재학습 → per-user predict.  
catalog `y_hat`은 fallback으로 유지.

---

## 작업 이력

| 일자 | 마일스톤 |
|------|----------|
| 2026-07-09 | Docker 환경 구축, 실험 시작 (§1~10 Track A CF) |
| 2026-07-10 | Track B catalog export 확립 (§13~16) |
| 2026-07-13 | 콜드스타트 재정의, 모듈 5종 분리 (§17~18) |
| 2026-07-14 | Go 통과 (L0~L2), Bayesian bar, 이축 Go (§19~22) |
| 2026-07-14 | 별점 Recall@20 헌장 재구성, R0~R2 Go 5/5 (§28~29) |
| 2026-07-14 | 외부 축 실험 후 복귀, full-catalog 진단 (§30~31) |
| **2026-07-15** | **Phase 1 완료 — catalog 기본 추천 엔진 확정** |

---

## 주의사항

- **공식 실행 = Docker only** (`ai/experiments/docker-compose.yml`). WARP는 Linux에서만 안정.
- 모델 재실행 시 seed별 미세 변동 가능 (WARP drift) — 비교는 동일 seed fresh run 기준.
- `prefer_hat=1` on cold 레시피는 모델 추정이며 y* 검증된 값이 아님.
