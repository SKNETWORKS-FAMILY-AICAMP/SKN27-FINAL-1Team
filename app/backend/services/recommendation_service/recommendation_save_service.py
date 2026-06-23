from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.backend.db.models import Recipe, RecommendationResult

MANUAL_SAVE_TYPE = "manual_save"


class RecommendationSaveService:
    def save_recipe_recommendation(
        self,
        db: Session,
        user_id: int,
        recipe_id: int,
    ) -> dict[str, Any]:
        """레시피를 recommendation_results에 저장한다. 중복 검사 없이 매번 새 행을 만든다."""
        recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()
        if recipe is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="레시피를 찾을 수 없습니다.",
            )

        row = RecommendationResult(
            user_id=user_id,
            recipe_id=recipe_id,
            recommendation_type=MANUAL_SAVE_TYPE,
        )
        db.add(row)
        db.commit()
        db.refresh(row)

        return {
            "recommendation_id": int(row.id),
            "recipe_id": int(row.recipe_id),
            "recommendation_type": row.recommendation_type or MANUAL_SAVE_TYPE,
            "created_at": row.created_at,
        }


recommendation_save_service = RecommendationSaveService()
