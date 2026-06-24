from fastapi import FastAPI
import asyncio
from fastapi.middleware.cors import CORSMiddleware

from app.backend.core.config import settings
from app.backend.db.session import engine
from app.backend.db.base import Base
from app.backend.db import models
from app.backend.api.auth import auth_api
from app.backend.api.inventory import inventory_api
from app.backend.api.onboarding import onboarding_api
from app.backend.api.receipts import receipts_api
from app.backend.api.guide import guide_api
from app.backend.api.recipes import recipes_api
from app.backend.api.recommendations import recommendations_api
from app.backend.api.shopping import shopping_api
from app.backend.api.notifications import notifications_api
from app.backend.api.calendar import calendar_api
from app.backend.services.calendar_job import daily_calendar_loop


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="밥벌이(Bobbeori) 백엔드 API 서버입니다.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# 프론트엔드 로컬 개발 환경에서 API를 호출할 수 있도록 CORS를 허용합니다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 개발 모드에서는 SQLAlchemy 모델 기준으로 테이블을 자동 생성합니다.
if settings.DEV_MODE:
    try:
        Base.metadata.create_all(bind=engine)
        print(f"[DB Setup] DEV_MODE: {settings.DB_ENGINE} 테이블 확인/생성 완료")
    except Exception as e:
        print(f"[DB Setup] {settings.DB_ENGINE} 테이블 자동 생성 실패: {e}")


API_V1_PREFIX = "/api/v1"

app.include_router(auth_api.router, prefix=API_V1_PREFIX)
app.include_router(onboarding_api.router, prefix=API_V1_PREFIX)
app.include_router(inventory_api.router, prefix=API_V1_PREFIX)
app.include_router(receipts_api.router, prefix=API_V1_PREFIX)
app.include_router(guide_api.router, prefix=API_V1_PREFIX)
app.include_router(recipes_api.router, prefix=API_V1_PREFIX)
app.include_router(recommendations_api.router, prefix=API_V1_PREFIX)
app.include_router(shopping_api.router, prefix=API_V1_PREFIX)
app.include_router(notifications_api.router, prefix=API_V1_PREFIX)
app.include_router(calendar_api.router, prefix=API_V1_PREFIX)


@app.on_event("startup")
async def start_calendar_job():
    app.state.calendar_job_task = asyncio.create_task(daily_calendar_loop())


@app.on_event("shutdown")
async def stop_calendar_job():
    task = getattr(app.state, "calendar_job_task", None)
    if task:
        task.cancel()


@app.get("/", tags=["Health"])
def read_root():
    """
    서버가 정상적으로 실행 중인지 확인하는 기본 헬스체크 엔드포인트입니다.
    """
    return {
        "status": "ok",
        "message": f"Welcome to {settings.PROJECT_NAME} API Server",
        "dev_mode": settings.DEV_MODE,
        "docs_url": "/docs",
    }
