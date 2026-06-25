from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.backend.core.config import settings

# SQLAlchemy 데이터베이스 엔진 생성
engine = create_engine(settings.DATABASE_URL)

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
