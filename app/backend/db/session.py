from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.backend.core.config import settings

# SQLite는 멀티 스레드 테스트 시 동시성 충돌을 방지하기 위해 특별한 인자가 필요함
connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

# SQLAlchemy 데이터베이스 엔진 생성
engine = create_engine(
    settings.DATABASE_URL, 
    connect_args=connect_args
)

# 세션 생성기
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    """
    FastAPI 의존성 주입(Dependency Injection)용 DB 세션 생성 함수.
    API 요청이 끝나면 세션을 자동으로 close합니다.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
