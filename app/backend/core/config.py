import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

class Settings:
    # App Settings
    PROJECT_NAME: str = "밥벌이 (Bobbeori)"
    DEV_MODE: bool = os.getenv("DEV_MODE", "True").lower() == "true"
    
    # Database Settings
    DB_ENGINE: str = os.getenv("DB_ENGINE", "sqlite")
    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_PORT: int = int(os.getenv("DB_PORT", 5432))
    DB_USER: str = os.getenv("DB_USER", "bobbeori_user")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "")
    DB_NAME: str = os.getenv("DB_NAME", "bobbeori_db")
    
    # SQLite Fallback (DB 인프라 미구축 시 가볍게 로컬 파일 DB 사용)
    SQLITE_URL: str = "sqlite:///./test2.db"
    
    @property
    def DATABASE_URL(self) -> str:
        # DB_ENGINE이 postgresql로 명시되어 있으면 무조건 도커/실제 DB 연결
        if self.DB_ENGINE == "postgresql":
            return f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        
        # 그 외의 경우(기본값) 가벼운 로컬 SQLite 사용 (팀원들 도커 없이 테스트용)
        return self.SQLITE_URL
    
    # JWT Settings
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "YOUR_JWT_SECRET_KEY_HERE")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 60))
    
    # Kakao OAuth Settings
    KAKAO_CLIENT_ID: str = os.getenv("KAKAO_CLIENT_ID", "")
    KAKAO_CLIENT_SECRET: str = os.getenv("KAKAO_CLIENT_SECRET", "")
    KAKAO_REDIRECT_URI: str = os.getenv("KAKAO_REDIRECT_URI", "")
    
    # Naver OAuth Settings
    NAVER_CLIENT_ID: str = os.getenv("NAVER_CLIENT_ID", "")
    NAVER_CLIENT_SECRET: str = os.getenv("NAVER_CLIENT_SECRET", "")
    NAVER_REDIRECT_URI: str = os.getenv("NAVER_REDIRECT_URI", "")
    
    # Google OAuth Settings
    GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    GOOGLE_REDIRECT_URI: str = os.getenv("GOOGLE_REDIRECT_URI", "")
    GOOGLE_CALENDAR_REDIRECT_URI: str = os.getenv(
        "GOOGLE_CALENDAR_REDIRECT_URI",
        "http://localhost:5173/auth/callback/google-calendar",
    )

    # OpenAI & AI Tools Settings
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "")
    
    # Runpod MCP / AI Server
    RUNPOD_CALENDAR_MCP_URL: str = os.getenv("RUNPOD_CALENDAR_MCP_URL", "")
    RUNPOD_INTERNAL_TOKEN: str = os.getenv("RUNPOD_INTERNAL_TOKEN", "")
    RUNPOD_TIMEOUT_SECONDS: int = int(os.getenv("RUNPOD_TIMEOUT_SECONDS", 20))

settings = Settings()
