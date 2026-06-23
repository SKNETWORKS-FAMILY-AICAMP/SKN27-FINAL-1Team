# 로컬 실행 가이드

## Docker — 프론트·백·DB 일괄 기동

1. 프로젝트 루트에 `.env` 준비 (`.env.sample` 복사 후 `DB_PASSWORD`, `NEO4J_PASSWORD` 등 설정)
2. 레시피 적재용 CSV가 로컬 `storage/`에 있는지 확인
   - `storage/processed/recipe/recipe_fix.csv` (전처리 결과)
   - `storage/raw/recipe/cooking_steps.csv` (조리단계)
3. 한 번에 기동:

```powershell
docker compose up -d --build
```

4. 접속 주소

| 서비스 | URL |
|--------|-----|
| 프론트 (Vite) | http://localhost:5173 |
| 백엔드 API | http://localhost:8000 |
| API 문서 (Swagger) | http://localhost:8000/docs |
| Neo4j Browser | http://localhost:7474 |

프론트는 브라우저에서 `http://localhost:8000`으로 API를 호출합니다 (`VITE_API_URL`).

### 기동 순서

`docker compose up` 시 서비스는 아래 순서로 올라갑니다.

```
postgres (healthcheck 통과)
    → recipe_load (CSV → PostgreSQL 적재, 완료 후 종료)
    → backend
    → frontend
```

`neo4j`는 `backend`와 병렬로 기동됩니다.

### 레시피 PostgreSQL 자동 적재 (`recipe_load`)

Docker Compose에 **일회성(one-shot) ETL 서비스** `recipe_load`가 포함되어 있습니다.

| 항목 | 내용 |
|------|------|
| 이미지 | `etl/Dockerfile` |
| 실행 명령 | `python -m etl.recipe.load_to_postgres` |
| 데이터 소스 | 호스트 `./storage` 볼륨 마운트 (`/project/storage:ro`) |
| DB 연결 | `.env` + `DB_HOST=postgres` (컨테이너 네트워크) |
| 재시작 정책 | `restart: "no"` — 적재 완료 후 컨테이너 종료 |

적재가 끝나면 `recipe_load`는 **Exited (0)** 상태로 내려가며, 이는 정상 동작입니다. 데이터는 `postgres` 볼륨에 유지되고 `backend` / `frontend`는 계속 실행됩니다.

`backend`는 `recipe_load`가 성공적으로 끝난 뒤에만 기동합니다 (`depends_on: service_completed_successfully`).

**적재만 다시 실행할 때** (CSV 갱신 후 등):

```powershell
docker compose run --rm recipe_load
```

**DB 연결만 확인할 때:**

```powershell
docker compose run --rm recipe_load python -m etl.recipe.load_to_postgres --test-conn
```

**적재 로그 확인:**

```powershell
docker compose logs recipe_load
```

**Postgres가 `initdb ... not empty`로 실패할 때** (로컬 DB 초기화 OK인 경우):

```powershell
docker compose down
Remove-Item -Recurse -Force .\storage\postgres\data\*
docker compose up -d
```

## Docker 없이

백엔드 (프로젝트 루트에서):

```powershell
.\.venv\Scripts\activate
uvicorn app.backend.main:app --reload --host 0.0.0.0 --port 8000
```

프론트 (`app/frontend`):

```powershell
npm install
npm run dev
```

프론트 환경변수는 `app/frontend/.env` (`VITE_API_URL=http://localhost:8000`).

### 레시피 PostgreSQL 수동 적재 (Docker 없이)

Postgres가 로컬 또는 Docker로 이미 떠 있고 `.env`의 `DB_HOST`가 맞게 설정된 경우:

```powershell
.\.venv\Scripts\activate
pip install -r etl/requirements.txt
python -m etl.recipe.load_to_postgres
```

옵션 예시:

```powershell
python -m etl.recipe.load_to_postgres --test-conn
python -m etl.recipe.load_to_postgres --recipe-csv storage/processed/recipe/recipe_fix.csv --cooking-steps-csv storage/raw/recipe/cooking_steps.csv
```
