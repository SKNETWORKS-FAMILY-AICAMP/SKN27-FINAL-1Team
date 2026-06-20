from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.backend.core.config import settings
from app.backend.db.session import engine
from app.backend.db.base import Base

# DB 모델 로드 (create_all 호출 시 테이블들이 감지되도록 임포트)
from app.backend.db import models

# FastAPI 인스턴스 생성
app = FastAPI(
    title=settings.PROJECT_NAME,
    description="밥벌이 (Bobbeori) 프로젝트의 백엔드 모의(Mock) API 및 선행 개발 서버입니다.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS 설정 (프론트엔드 UI 연동 지원)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 로컬 개발 환경용 전체 허용 (배포 시 특정 도메인으로 축소 필요)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 로컬 개발(DEV_MODE) 시 가벼운 SQLite 테이블 자동 생성
if settings.DEV_MODE:
    try:
        # base.py에 선언된 메타데이터를 기반으로 SQLite 데이터베이스 테이블을 자동 생성합니다.
        Base.metadata.create_all(bind=engine)
        print("💡 [Local DB] DEV_MODE가 활성화되어 SQLite 테이블이 정상적으로 자동 생성되었습니다.")
    except Exception as e:
        print(f"⚠️ [Local DB] SQLite 테이블 자동 생성 중 실패: {e}")

# API 라우터 등록
from app.backend.api.auth import auth_mock, auth_api
from app.backend.api.inventory import inventory_api
from app.backend.api.onboarding import onboarding_api

# v1 API 엔드포인트 바인딩 (DEV_MODE 여부에 따라 Mock과 실구현 라우터 분기 등록)
if settings.DEV_MODE:
    app.include_router(auth_api.router, prefix="/api/v1")
    app.include_router(inventory_api.router, prefix="/api/v1")
    app.include_router(onboarding_api.router, prefix="/api/v1")
    print("💡 [Router] DEV_MODE 활성화로 인해 Mock API(일부) 라우터가 등록되었습니다.")
else:
    app.include_router(auth_api.router, prefix="/api/v1")
    app.include_router(inventory_api.router, prefix="/api/v1")
    app.include_router(onboarding_api.router, prefix="/api/v1")
    print("🚀 [Router] 프로덕션 모드 활성화로 인해 실제 DB 연동 API 라우터가 등록되었습니다.")

# 기본 웰컴 API 엔드포인트
@app.get("/")
def read_root():
    return {
        "message": f"Welcome to {settings.PROJECT_NAME} API Server",
        "dev_mode": settings.DEV_MODE,
        "docs_url": "/docs"
    }
