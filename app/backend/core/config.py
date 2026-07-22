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
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 60 * 24 * 30)) # 개발 기간 편의를 위해 30일로 연장
    REFRESH_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_MINUTES", 60 * 24 * 30)) # 개발 기간 편의를 위해 30일로 연장

    # 허용할 프론트엔드 출처를 쉼표로 구분해 설정합니다.
    CORS_ALLOWED_ORIGINS: list[str] = [
        origin.strip()
        for origin in os.getenv(
            "CORS_ALLOWED_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173" if DEV_MODE else "",
        ).split(",")
        if origin.strip()
    ]
    
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
    NAVER_SHOPPING_DISPLAY: int = int(os.getenv("NAVER_SHOPPING_DISPLAY", 10))
    NAVER_SHOPPING_SORT: str = os.getenv("NAVER_SHOPPING_SORT", "sim")
    NAVER_SHOPPING_EXCLUDE: str = os.getenv("NAVER_SHOPPING_EXCLUDE", "used:rental:cbshop")
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
    LANGFUSE_PUBLIC_KEY: str = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    LANGFUSE_SECRET_KEY: str = os.getenv("LANGFUSE_SECRET_KEY", "")
    LANGFUSE_BASE_URL: str = (
        os.getenv("LANGFUSE_BASE_URL") or os.getenv("LANGFUSE_HOST", "")
    ).rstrip("/")
    LANGFUSE_HOST: str = (os.getenv("LANGFUSE_HOST") or LANGFUSE_BASE_URL).rstrip("/")
    
    # Runpod MCP / AI Server
    RUNPOD_CALENDAR_MCP_URL: str = os.getenv("RUNPOD_CALENDAR_MCP_URL", "")
    RUNPOD_CALENDAR_SERVERLESS_URL: str = os.getenv("RUNPOD_CALENDAR_SERVERLESS_URL", "")
    RUNPOD_API_KEY: str = os.getenv("RUNPOD_API_KEY", "")
    RUNPOD_INTERNAL_TOKEN: str = os.getenv("RUNPOD_INTERNAL_TOKEN", "")
    RUNPOD_TIMEOUT_SECONDS: int = int(os.getenv("RUNPOD_TIMEOUT_SECONDS", 60))

    # Public MCP resource server. Local development can reuse the existing app
    # JWT, while production must validate OAuth access tokens from an issuer.
    MCP_DEV_TOKEN_AUTH: bool = os.getenv(
        "MCP_DEV_TOKEN_AUTH",
        "true" if DEV_MODE else "false",
    ).lower() == "true"
    MCP_ISSUER_URL: str = os.getenv("MCP_ISSUER_URL", "").rstrip("/")
    MCP_RESOURCE_URL: str = os.getenv("MCP_RESOURCE_URL", "").rstrip("/")
    MCP_JWKS_URL: str = os.getenv("MCP_JWKS_URL", "")
    MCP_USERINFO_URL: str = os.getenv("MCP_USERINFO_URL", "")
    MCP_JWT_AUDIENCE: str = os.getenv("MCP_JWT_AUDIENCE", "")
    MCP_JWT_ALGORITHMS: list[str] = [
        value.strip()
        for value in os.getenv("MCP_JWT_ALGORITHMS", "RS256").split(",")
        if value.strip()
    ]
    MCP_SCOPE_PREFIX: str = os.getenv("MCP_SCOPE_PREFIX", "bobbeori-mcp").strip().rstrip("/")
    _MCP_DEFAULT_SCOPES: str = (
        f"{MCP_SCOPE_PREFIX}/inventory.read,{MCP_SCOPE_PREFIX}/recipe.read,"
        f"{MCP_SCOPE_PREFIX}/guide.read,{MCP_SCOPE_PREFIX}/receipt.write,"
        f"{MCP_SCOPE_PREFIX}/shopping.write,{MCP_SCOPE_PREFIX}/calendar.write"
    )
    MCP_SUPPORTED_SCOPES: list[str] = [
        value.strip()
        for value in os.getenv(
            "MCP_SUPPORTED_SCOPES",
            _MCP_DEFAULT_SCOPES,
        ).split(",")
        if value.strip()
    ]
    MCP_REQUIRED_SCOPES: list[str] = [
        value.strip()
        for value in os.getenv(
            "MCP_REQUIRED_SCOPES",
            _MCP_DEFAULT_SCOPES,
        ).split(",")
        if value.strip()
    ]
    MCP_JWKS_CACHE_SECONDS: int = int(os.getenv("MCP_JWKS_CACHE_SECONDS", 300))
    MCP_PREVIEW_TOKEN_SECRET: str = os.getenv("MCP_PREVIEW_TOKEN_SECRET", JWT_SECRET_KEY)
    MCP_PREVIEW_TTL_SECONDS: int = int(os.getenv("MCP_PREVIEW_TTL_SECONDS", 600))
    MCP_PORT: int = int(os.getenv("MCP_PORT", 8001))
    MCP_ALLOWED_HOSTS: list[str] = [
        value.strip()
        for value in os.getenv("MCP_ALLOWED_HOSTS", "").split(",")
        if value.strip()
    ]
    MCP_ALLOWED_ORIGINS: list[str] = [
        value.strip()
        for value in os.getenv("MCP_ALLOWED_ORIGINS", "").split(",")
        if value.strip()
    ]
    OPENAI_APPS_CHALLENGE_TOKEN: str = os.getenv("OPENAI_APPS_CHALLENGE_TOKEN", "").strip()

    # Receipt OCR Settings
    OCR_ENGINE: str = os.getenv("OCR_ENGINE", "openai_vision")
    OCR_MODEL: str = os.getenv("OCR_MODEL", OPENAI_MODEL)
    OCR_FALLBACK_MODEL: str = os.getenv("OCR_FALLBACK_MODEL", "")
    OCR_UPLOAD_DIR: str = os.getenv("OCR_UPLOAD_DIR", "storage/raw/receipts")
    OCR_OUTPUT_DIR: str = os.getenv("OCR_OUTPUT_DIR", "storage/processed/receipts")
    RECEIPT_STORAGE_BACKEND: str = os.getenv("RECEIPT_STORAGE_BACKEND", "local").lower()
    AWS_REGION: str = os.getenv("AWS_REGION", "ap-northeast-2")
    S3_RECEIPT_BUCKET: str = os.getenv("S3_RECEIPT_BUCKET", "")
    S3_RECEIPT_PREFIX: str = os.getenv("S3_RECEIPT_PREFIX", "receipts")
    S3_ENDPOINT_URL: str = os.getenv("S3_ENDPOINT_URL", "")
    MAX_UPLOAD_SIZE_MB: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", 10))
    RECEIPT_UPLOAD_RATE_LIMIT_PER_MINUTE: int = int(os.getenv("RECEIPT_UPLOAD_RATE_LIMIT_PER_MINUTE", 5))
    RECEIPT_UPLOAD_RATE_LIMIT_PER_DAY: int = int(os.getenv("RECEIPT_UPLOAD_RATE_LIMIT_PER_DAY", 50))

    def validate_security(self) -> None:
        """운영 서버 시작 전에 필수 보안 설정을 검증합니다."""
        if not self.DEV_MODE and len(self.JWT_SECRET_KEY) < 32:
            raise RuntimeError("JWT_SECRET_KEY는 32자 이상의 임의 문자열로 설정해야 합니다.")

        if self.RECEIPT_STORAGE_BACKEND not in {"local", "s3"}:
            raise RuntimeError("RECEIPT_STORAGE_BACKEND must be local or s3")
        if self.RECEIPT_STORAGE_BACKEND == "s3" and not self.S3_RECEIPT_BUCKET:
            raise RuntimeError("S3_RECEIPT_BUCKET is required when receipt storage uses S3")

settings = Settings()
if settings.LANGFUSE_HOST and not os.getenv("LANGFUSE_HOST"):
    os.environ["LANGFUSE_HOST"] = settings.LANGFUSE_HOST
