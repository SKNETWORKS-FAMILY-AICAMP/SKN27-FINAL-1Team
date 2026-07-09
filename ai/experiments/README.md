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

브라우저: http://localhost:8888 → `LightFM_Model.ipynb` 열기

> 루트(`SKN27-FINAL-1Team/`)의 `docker compose up`은 backend 스택만 기동합니다.  
> LightFM 노트북은 **반드시 `ai/experiments/`에서** 별도 compose로 실행하세요.

### 종료

```powershell
docker compose down
```

## 검증

```powershell
cd ai\experiments

# 1) LightFM 스모크 테스트
docker compose run --rm lightfm-jupyter python scripts/verify_lightfm.py

# 2) 노트북 E2E (Unit 1~9 전체 실행)
docker compose run --rm lightfm-jupyter sh scripts/run_notebook_e2e.sh
```

## 구성

| 파일 | 역할 |
|------|------|
| `docker-compose.yml` | 독립 스택 (루트 compose와 분리, 포트 8888) |
| `Dockerfile` | Python 3.11 + lightfm + JupyterLab |
| `LightFM_Model.ipynb` | 실험 노트북 |
| `requirements.txt` | Docker 빌드 의존성 |

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
