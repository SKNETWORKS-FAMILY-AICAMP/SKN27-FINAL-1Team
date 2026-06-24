from fastapi import APIRouter, Depends

from sqlalchemy.orm import Session

from app.backend.api.deps import get_current_user, get_current_user_required
from app.backend.db.session import get_db
from app.backend.schemas.recipes import (
    RecipeDetailResponse,
    RecipeRecommendItem,
    RecipeRecommendRequest,
    RecipeSearchResponse,
)
from app.backend.services.recommendation_service.recipe_detail_service import recipe_detail_service
from app.backend.services.recommendation_service.recipe_search_service import recipe_search_service
from app.backend.services.recommendation_service.recommendation_service import recommendation_service

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
    db: Session = Depends(get_db),
):
    recommendations = [
        {"recipe_id": 1, "title": "대파 볶음밥", "match_rate": 85},
        {"recipe_id": 2, "title": "두부 김치", "match_rate": 78},
    ]
    recommendation_service.save_many(
        db,
        current_user_id,
        [item["recipe_id"] for item in recommendations],
        "fridge_based",
    )
    return recommendations

@router.get("/{id}", response_model=RecipeDetailResponse)
def get_recipe_detail(
    id: int,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user),
):
    """레시피 상세 조회. 비로그인 시 보유 재료는 비어 있고 전체가 부족 재료로 반환됩니다."""
    return recipe_detail_service.get_recipe_detail(db, id, current_user_id)
