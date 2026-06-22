from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.backend.db.session import get_db
from app.backend.schemas.recipe import RecipeSearchResponse
from app.backend.services.recommendation_service.recipe_search_service import recipe_search_service

router = APIRouter(prefix="/recipes", tags=["Recipes (레시피 검색)"])


def _normalize_filter(value: str | None) -> str | None:
    normalized = (value or "").strip()
    if not normalized or normalized == "전체":
        return None
    return normalized


@router.get("/search", response_model=RecipeSearchResponse)
def search_recipes(
    query: str | None = None,
    category: str | None = None,
    difficulty: str | None = None,
    cooking_time_label: str | None = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
):
    """레시피명 부분 일치 검색, 필터, 페이지네이션."""
    return recipe_search_service.search_recipes(
        db=db,
        query=query,
        category=_normalize_filter(category),
        difficulty=_normalize_filter(difficulty),
        cooking_time_label=_normalize_filter(cooking_time_label),
        page=page,
        page_size=page_size,
    )
