from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.backend.db.session import get_db
from app.backend.schemas.recipe import RecipeSearchResponse
from app.backend.services.recommendation_service.recipe_search_service import recipe_search_service

router = APIRouter(prefix="/recipes", tags=["Recipes (레시피 검색)"])


@router.get("/search", response_model=RecipeSearchResponse)
def search_recipes(
    query: str | None = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
):
    """레시피명 부분 일치 검색 및 페이지네이션."""
    return recipe_search_service.search_recipes(
        db=db,
        query=query,
        page=page,
        page_size=page_size,
    )
