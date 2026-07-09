# LightFM Experiments

LightFM 추천 실험 노트북 공식 실행 환경입니다.

**공식 실행 = Docker only.** Windows 로컬 `.venv`에서는 WARP loss·평가 함수가 커널 크래시를 일으킬 수 있어 지원하지 않습니다.

## 사전 요구

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows/Mac) 또는 Docker Engine (Linux)

## 실행

```powershell
cd ai\experiments
docker compose up --build
```

브라우저: http://localhost:8888 → `LightFM_Model.ipynb` 열기 → Unit 1부터 순서대로 실행

> 루트(`SKN27-FINAL-1Team/`)의 `docker compose up`은 backend 스택만 기동합니다.  
> LightFM 노트북은 **반드시 `ai/experiments/`에서** 별도 compose로 실행하세요.

### 종료

```powershell
docker compose down
```

## 환경 재현·검증

이미지 재빌드, 다른 PC 세팅, 노트북 수정 후 아래 순서로 확인한다.

### 1) 이미지 빌드

```powershell
cd ai\experiments
docker compose build
```

### 2) LightFM 스모크 테스트

warp fit + `precision_at_k` / `recall_at_k` 동작 확인 (수 초).

```powershell
docker compose run --rm lightfm-jupyter python -c @"
import numpy as np
from scipy.sparse import csr_matrix
from lightfm import LightFM
from lightfm.evaluation import precision_at_k, recall_at_k

rng = np.random.default_rng(42)
n_users, n_items = 20, 30
rows, cols = rng.integers(0, n_users, 80), rng.integers(0, n_items, 80)
data = np.ones(80, dtype=np.float32)
interactions = csr_matrix((data, (rows, cols)), shape=(n_users, n_items))

model = LightFM(loss='warp', random_state=42)
model.fit(interactions, epochs=2, num_threads=2)

p5 = float(precision_at_k(model, interactions, k=5).mean())
r5 = float(recall_at_k(model, interactions, k=5).mean())
assert 0.0 <= p5 <= 1.0 and 0.0 <= r5 <= 1.0
print(f'lightfm ok: precision@5={p5:.4f}, recall@5={r5:.4f}')
"@
```

**통과:** `lightfm ok: precision@5=...` 출력, exit code 0

### 3) 노트북 E2E (Unit 1~9 전체 실행)

`LightFM_Model.ipynb`를 헤드리스로 실행한다 (수 분, epoch 100 기준).

```powershell
docker compose run --rm lightfm-jupyter jupyter nbconvert `
  --to notebook `
  --execute LightFM_Model.ipynb `
  --output /tmp/LightFM_Model.executed.ipynb `
  --ExecutePreprocessor.timeout=600
```

**통과 조건**

| 항목 | 확인 |
|------|------|
| exit code | 0 |
| Unit 1 | `LIGHTFM_RUNTIME=linux-docker` 가드 통과 |
| Unit 7 | epoch 로그 출력 (warp 학습 완료) |
| Unit 8 | `precision@5`, `recall@5` 등 metrics dict 출력 |
| Unit 9 | `experiment_report` dict 출력 |
| stderr | Python traceback 없음 |

실행 결과 노트북은 컨테이너 `/tmp/`에만 저장되며 원본 `.ipynb`는 수정되지 않는다.

## 구성

| 파일 | 역할 |
|------|------|
| `docker-compose.yml` | 독립 스택 (루트 compose와 분리, 포트 8888) |
| `Dockerfile` | Python 3.11 + lightfm + JupyterLab |
| `LightFM_Model.ipynb` | 실험 노트북 |
| `requirements.txt` | Docker 빌드 의존성 |
| `experiments.md` | 실험 결과 기록 |

- 컨테이너명: `lightfm_experiments_jupyter`
- Compose project: `lightfm-experiments`
- 루트 backend(8000/5173/5432 등)와 **동시 기동 가능**

## 비공식: Windows 로컬 설치 (import 확인용)

공식 실행에는 사용하지 마세요. lightfm 1.17은 Windows에서 빌드·실행이 불안정합니다.

```powershell
cd ai\experiments
uv python install 3.11
uv venv .venv --python 3.11
.\.venv\Scripts\activate
python -m pip install --upgrade "pip<25" "setuptools==69.5.1" "wheel==0.43.0" "cython==3.0.11"
python -m pip install --no-use-pep517 --no-build-isolation lightfm==1.17
python -m pip install -r requirements.txt
python -c "from lightfm import LightFM; print('import ok')"
```

노트북 Unit 1은 `LIGHTFM_RUNTIME=linux-docker`가 없으면 즉시 오류를 냅니다.

## 보안 참고

로컬 개발 편의를 위해 JupyterLab 토큰/비밀번호를 비활성화했습니다.  
외부 네트워크에 노출하지 마세요.
