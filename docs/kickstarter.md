# 로컬 실행 가이드

## Docker — 프론트·백·DB 일괄 기동

1. 프로젝트 루트에 `.env` 준비 (`.env.sample` 복사 후 `DB_PASSWORD`, `NEO4J_PASSWORD` 등 설정)
2. 한 번에 기동:

```powershell
docker compose up -d --build
```

3. 접속 주소

| 서비스 | URL |
|--------|-----|
| 프론트 (Vite) | http://localhost:5173 |
| 백엔드 API | http://localhost:8000 |
| API 문서 (Swagger) | http://localhost:8000/docs |
| Neo4j Browser | http://localhost:7474 |

프론트는 브라우저에서 `http://localhost:8000`으로 API를 호출합니다 (`VITE_API_URL`).

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
