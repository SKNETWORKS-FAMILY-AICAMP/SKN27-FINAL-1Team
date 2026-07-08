import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

class Settings:
    # App Settings
    PROJECT_NAME: str = "밥벌이 (Bobbeori)"
    DEV_MODE: bool = os.getenv("DEV_MODE", "True").lower() == "true"
    
    # Database Settings
    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_PORT: int = int(os.getenv("DB_PORT", 5432))
    DB_USER: str = os.getenv("DB_USER", "bobbeori_user")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "")
    DB_NAME: str = os.getenv("DB_NAME", "bobbeori_db")

    # Neo4j Settings
    NEO4J_URI: str = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    NEO4J_USER: str = os.getenv("NEO4J_USER", "neo4j")
    NEO4J_PASSWORD: str = os.getenv("NEO4J_PASSWORD", "")
    NEO4J_DATABASE: str = os.getenv("NEO4J_DATABASE", "neo4j")

    @property
    def DATABASE_URL(self) -> str:
        # PostgreSQL 연결 URL을 생성합니다.
        return f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    # JWT Settings
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "YOUR_JWT_SECRET_KEY_HERE")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 60 * 24 * 30)) # 개발 기간 편의를 위해 30일로 연장
    REFRESH_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_MINUTES", 60 * 24 * 30)) # 개발 기간 편의를 위해 30일로 연장
    
    # Kakao OAuth Settings
    KAKAO_CLIENT_ID: str = os.getenv("KAKAO_CLIENT_ID", "")
    KAKAO_CLIENT_SECRET: str = os.getenv("KAKAO_CLIENT_SECRET", "")
    KAKAO_REDIRECT_URI: str = os.getenv("KAKAO_REDIRECT_URI", "")
    
    # Naver OAuth Settings
    NAVER_CLIENT_ID: str = os.getenv("NAVER_CLIENT_ID", "")
    NAVER_CLIENT_SECRET: str = os.getenv("NAVER_CLIENT_SECRET", "")
    NAVER_REDIRECT_URI: str = os.getenv("NAVER_REDIRECT_URI", "")

    # Naver Shopping Search API Settings
    NAVER_SHOPPING_CLIENT_ID: str = os.getenv("NAVER_SHOPPING_CLIENT_ID", NAVER_CLIENT_ID)
    NAVER_SHOPPING_CLIENT_SECRET: str = os.getenv("NAVER_SHOPPING_CLIENT_SECRET", NAVER_CLIENT_SECRET)
    NAVER_SHOPPING_API_URL: str = os.getenv(
        "NAVER_SHOPPING_API_URL",
        "https://openapi.naver.com/v1/search/shop.json",
    )
    NAVER_SHOPPING_DISPLAY: int = int(os.getenv("NAVER_SHOPPING_DISPLAY", 1))
    NAVER_SHOPPING_TIMEOUT_SECONDS: int = int(os.getenv("NAVER_SHOPPING_TIMEOUT_SECONDS", 5))
    
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
    RUNPOD_CALENDAR_SERVERLESS_URL: str = os.getenv("RUNPOD_CALENDAR_SERVERLESS_URL", "")
    RUNPOD_API_KEY: str = os.getenv("RUNPOD_API_KEY", "")
    RUNPOD_INTERNAL_TOKEN: str = os.getenv("RUNPOD_INTERNAL_TOKEN", "")
    RUNPOD_TIMEOUT_SECONDS: int = int(os.getenv("RUNPOD_TIMEOUT_SECONDS", 60))

    # Receipt OCR Settings
    OCR_ENGINE: str = os.getenv("OCR_ENGINE", "openai_vision")
    OCR_MODEL: str = os.getenv("OCR_MODEL", OPENAI_MODEL)
    OCR_FALLBACK_MODEL: str = os.getenv("OCR_FALLBACK_MODEL", "")
    OCR_UPLOAD_DIR: str = os.getenv("OCR_UPLOAD_DIR", "storage/raw/receipts")
    OCR_OUTPUT_DIR: str = os.getenv("OCR_OUTPUT_DIR", "storage/processed/receipts")
    MAX_UPLOAD_SIZE_MB: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", 10))
    RECEIPT_UPLOAD_RATE_LIMIT_PER_MINUTE: int = int(os.getenv("RECEIPT_UPLOAD_RATE_LIMIT_PER_MINUTE", 5))
    RECEIPT_UPLOAD_RATE_LIMIT_PER_DAY: int = int(os.getenv("RECEIPT_UPLOAD_RATE_LIMIT_PER_DAY", 50))

settings = Settings()
