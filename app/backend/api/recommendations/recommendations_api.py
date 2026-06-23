from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.backend.api.deps import get_current_user_required
from app.backend.db.session import get_db
from app.backend.schemas.recommendations import (
    RecommendationSaveRequest,
    RecommendationSaveResponse,
)
from app.backend.services.recommendation_service.recommendation_save_service import (
    recommendation_save_service,
)

router = APIRouter(prefix="/recommendations", tags=["Recommendations (추천 저장)"])


@router.post("", response_model=RecommendationSaveResponse, status_code=status.HTTP_201_CREATED)
def save_recipe_recommendation(
    request_data: RecommendationSaveRequest,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_required),
):
    """레시피 상세에서 저장한 레시피를 추천 목록(recommendation_results)에 추가합니다."""
    return recommendation_save_service.save_recipe_recommendation(
        db,
        current_user_id,
        request_data.recipe_id,
    )
