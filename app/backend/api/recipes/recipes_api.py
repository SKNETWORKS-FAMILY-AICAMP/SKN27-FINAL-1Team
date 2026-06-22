from fastapi import APIRouter, Depends, Query

from app.backend.api.deps import get_current_user_required
from app.backend.schemas.recipes import (
    RecipeDetailResponse,
    RecipeRecommendItem,
    RecipeRecommendRequest,
    RecipeSearchItem,
)


router = APIRouter(prefix="/recipes", tags=["Recipes (레시피)"])


@router.get("/search", response_model=list[RecipeSearchItem])
def search_recipes(
    keyword: str = Query(..., description="검색할 식재료명"),
    current_user_id: int = Depends(get_current_user_required),
):
    """
    특정 식재료가 포함된 레시피를 검색합니다.
    현재는 API 계약 확인용 임시 응답을 반환합니다.
    """
    return [
        {"recipe_id": 1, "title": f"{keyword} 볶음밥"},
        {"recipe_id": 2, "title": f"{keyword} 전골"},
    ]


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
