# 노트북 실험 Docker 환경

**역할:** `ai/` 하위 프로젝트의 **Docker·Jupyter 실행 환경**입니다. 실험 코드·데이터·노트북은 마운트 대상 폴더에 둡니다.

| 위치 | 내용 |
|------|------|
| **본 폴더** (`ai/experiments/`) | `Dockerfile`, `docker-compose.yml`, `.env` |
| **프로젝트 폴더** (기본 `../recommendation/`) | 노트북·코드·데이터·산출물 |

## 빠른 시작

```powershell
cd ai\experiments
copy .env.example .env   # 최초 1회
docker compose up --build
# http://localhost:8888 — /workspace/project (기본: recommendation)
```

## 마운트 설정 (`.env`)

| 변수 | 기본 | 의미 |
|------|------|------|
| `MOUNT_PROJECT` | `../recommendation` | **노트북·코드·데이터·산출물** 호스트 경로 |
| `MOUNT_EXPERIMENTS` | `.` | **Docker 설정** 호스트 경로 |
| `CONTAINER_PROJECT` | `/workspace/project` | 컨테이너 내 프로젝트 루트 (`PROJECT_ROOT`) |
| `CONTAINER_EXPERIMENTS` | `/workspace/experiments` | 컨테이너 내 Docker 설정 경로 |

다른 실험 폴더를 쓰려면 `MOUNT_PROJECT`만 바꾸면 됩니다.

E2E (LightFM 예시):

```powershell
docker compose run --rm jupyter jupyter nbconvert `
  --execute /workspace/project/LightFM_Model.ipynb `
  --output /tmp/out.ipynb --ExecutePreprocessor.timeout=600
```

상세 실험 문서 → [`../recommendation/README.md`](../recommendation/README.md)
