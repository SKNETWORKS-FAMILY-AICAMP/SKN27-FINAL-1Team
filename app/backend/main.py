import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.backend.api.auth import auth_api
from app.backend.api.calendar import calendar_api
from app.backend.api.chat import chat_api
from app.backend.api.guide import guide_api
from app.backend.api.inventory import inventory_api
from app.backend.api.notifications import notifications_api
from app.backend.api.onboarding import onboarding_api
from app.backend.api.receipts import receipts_api
from app.backend.api.recipes import recipes_api
from app.backend.api.recommendations import recommendations_api
from app.backend.api.shopping import shopping_api
from app.backend.core.config import settings
from app.backend.services.inventory_service.inventory_seed import seed_common_inventory_standards


logger = logging.getLogger(__name__)

settings.validate_security()
app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Bobbeori API server",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
app.include_router(chat_api.router, prefix=API_V1_PREFIX)


@app.on_event("startup")
def seed_inventory_standards():
    """Ensure common ingredient standards exist before serving requests."""
    try:
        created_ingredients, created_standards = seed_common_inventory_standards()
        logger.info(
            "Inventory seed ready: ingredients=%s standards=%s",
            created_ingredients,
            created_standards,
        )
    except Exception:
        logger.exception("Inventory seed failed")


@app.get("/", tags=["Health"])
def read_root():
    return {
        "status": "ok",
        "message": f"Welcome to {settings.PROJECT_NAME} API Server",
        "dev_mode": settings.DEV_MODE,
        "docs_url": "/docs",
    }
