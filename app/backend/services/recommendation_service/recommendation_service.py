"""사용자 추천 저장(recommendation_results) + 추천 엔진 facade."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.backend.db.models import Recipe, RecommendationResult
from app.backend.services.recommendation_service.recommend_pipeline import recommend_pipeline
from app.backend.services.recommendation_service.recommend_config import RecipeRecommendConfig

__all__ = [
    "RecipeRecommendConfig",
    "RecommendationService",
    "recommendation_service",
]


class RecommendationService:
    MANUAL_SAVE_TYPE = "manual_save"

    def save_recipe(
        self,
        db: Session,
        user_id: int,
        recipe_id: int,
        recommendation_type: str = MANUAL_SAVE_TYPE,
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
            recommendation_type=recommendation_type,
        )
        db.add(row)
        db.commit()
        db.refresh(row)

        return {
            "recommendation_id": int(row.id),
            "recipe_id": int(row.recipe_id),
            "recommendation_type": row.recommendation_type or recommendation_type,
            "created_at": row.created_at,
        }

    def list_user_recipes(self, db: Session, user_id: int) -> list[dict[str, Any]]:
        rows = (
            db.query(RecommendationResult)
            .filter(RecommendationResult.user_id == user_id)
            .order_by(RecommendationResult.created_at.desc())
            .all()
        )

        return [
            {
                "recommendation_id": int(row.id),
                "recipe_id": int(row.recipe_id),
                "title": row.recipe.title,
                "description": row.recipe.description,
                "category": row.recipe.category,
                "cooking_time_min": row.recipe.cooking_time,
                "difficulty": row.recipe.difficulty,
                "image_url": row.recipe.image_url,
                "recommendation_type": row.recommendation_type or self.MANUAL_SAVE_TYPE,
                "created_at": row.created_at,
            }
            for row in rows
            if row.recipe is not None
        ]

    def delete_user_recipe(self, db: Session, user_id: int, recommendation_id: int) -> None:
        row = (
            db.query(RecommendationResult)
            .filter(
                RecommendationResult.id == recommendation_id,
                RecommendationResult.user_id == user_id,
            )
            .first()
        )
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="저장 레시피를 찾을 수 없습니다.")

        db.delete(row)
        db.commit()

    def recommend_recipes(
        self,
        db: Session,
        user_id: int,
        config: RecipeRecommendConfig,
        *,
        exclude_recipe_ids: list[int] | None = None,
        refresh_pool: bool = False,
    ) -> dict[str, Any]:
        return recommend_pipeline.recommend(
            db,
            user_id,
            config,
            exclude_recipe_ids=exclude_recipe_ids,
            refresh_pool=refresh_pool,
        )


recommendation_service = RecommendationService()
