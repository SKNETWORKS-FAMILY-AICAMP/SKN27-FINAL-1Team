from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.backend.api.deps import get_current_user_required
from app.backend.db.session import get_db
from app.backend.schemas.recommendations import (
    RecommendationSavedRecipe,
    RecommendationSaveRequest,
    RecommendationSaveResponse,
)
from app.backend.services.recommendation_service.recommendation_service import (
    recommendation_service,
)

router = APIRouter(prefix="/recommendations", tags=["Recommendations (추천 저장)"])


@router.get("", response_model=list[RecommendationSavedRecipe])
def list_saved_recommendations(
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_required),
):
    return recommendation_service.list_user_recipes(db, current_user_id)


@router.post("", response_model=RecommendationSaveResponse, status_code=status.HTTP_201_CREATED)
def save_recipe_recommendation(
    request_data: RecommendationSaveRequest,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_required),
):
    """레시피 상세에서 저장한 레시피를 추천 목록(recommendation_results)에 추가합니다."""
    return recommendation_service.save_recipe(
        db,
        current_user_id,
        request_data.recipe_id,
        request_data.recommendation_type,
    )


@router.delete("/{recommendation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_saved_recommendation(
    recommendation_id: int,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_required),
):
    recommendation_service.delete_user_recipe(db, current_user_id, recommendation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
