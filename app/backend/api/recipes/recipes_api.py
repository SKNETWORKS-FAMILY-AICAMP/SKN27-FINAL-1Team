from fastapi import APIRouter, Depends

from sqlalchemy.orm import Session

from app.backend.api.deps import get_current_user_required
from app.backend.db.session import get_db
from app.backend.schemas.recipes import (
    RecipeDetailResponse,
    RecipeRecommendItem,
    RecipeRecommendRequest,
    RecipeSearchResponse,
)
from app.backend.services.recommendation_service.recipe_search_service import recipe_search_service

router = APIRouter(prefix="/recipes", tags=["Recipes (레시피)"])


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


@router.post("/recommend", response_model=list[RecipeRecommendItem])
def recommend_recipes(
    request_data: RecipeRecommendRequest,
    current_user_id: int = Depends(get_current_user_required),
):
    """
    냉장고 재료, 취향, 소비 임박 정보를 종합해 레시피를 추천합니다.
    현재는 API 계약 확인용 임시 응답을 반환합니다.
    """
    return [
        {"recipe_id": 1, "title": "대파 볶음밥", "match_rate": 85},
        {"recipe_id": 2, "title": "두부 김치", "match_rate": 78},
    ]


@router.get("/{id}", response_model=RecipeDetailResponse)
def get_recipe_detail(
    id: int,
    current_user_id: int = Depends(get_current_user_required),
):
    """
    레시피 상세 조리법을 조회합니다.
    현재는 API 계약 확인용 임시 응답을 반환합니다.
    """
    return {
        "recipe_id": id,
        "title": "대파 볶음밥",
        "ingredients": ["밥", "대파", "계란", "간장"],
        "steps": ["대파를 썬다.", "팬에 볶는다.", "밥과 계란을 넣고 볶는다."],
    }
