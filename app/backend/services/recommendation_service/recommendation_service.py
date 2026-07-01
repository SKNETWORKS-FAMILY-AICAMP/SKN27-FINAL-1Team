"""사용자 추천 저장(recommendation_results) + 추천 엔진."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.backend.db.models import Recipe, RecommendationResult
from app.backend.services.recommendation_service.hard_filter import (
    filter_candidates_by_id,
    filter_recipes_by_banned,
    load_hard_filter_context,
)
from app.backend.services.recommendation_service.recipe_candidate_query import (
    build_recipe_query,
    load_recipe_ingredients_bulk,
    recipe_to_list_item,
)
from app.backend.services.recommendation_service.recommend_config import RecipeRecommendConfig

__all__ = [
    "RecipeRecommendConfig",
    "RecommendationService",
    "recommendation_service",
]


def _empty_recommend_result(empty_reason: str) -> dict[str, Any]:
    return {
        "items": [],
        "returned_count": 0,
        "has_more": False,
        "empty_reason": empty_reason,
    }


def _build_recommend_result(
    items: list[dict[str, Any]],
    has_more: bool,
    empty_reason: str,
) -> dict[str, Any]:
    response_items = [recipe_to_list_item(row["recipe"]) for row in items]
    return {
        "items": response_items,
        "returned_count": len(response_items),
        "has_more": has_more,
        "empty_reason": empty_reason,
    }


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
        hard_ctx = load_hard_filter_context(db, user_id)
        exclude = [] if refresh_pool else (exclude_recipe_ids or [])

        recipes = self._generate_candidates(db, config)
        recipes = filter_candidates_by_id(recipes, exclude)
        if not recipes:
            return _empty_recommend_result("no_sql_match")

        ingredients_by_recipe = load_recipe_ingredients_bulk(db, [recipe.id for recipe in recipes])
        recipes = filter_recipes_by_banned(recipes, ingredients_by_recipe, hard_ctx)
        if not recipes:
            return _empty_recommend_result("no_scorable_recipes")

        recipes = recipes[: config.pool_size]

        scored = self._evaluate_candidates(recipes, ingredients_by_recipe, config)
        self._rank_candidates(scored, config)

        items = scored[: config.limit]
        has_more = len(scored) > config.limit
        empty_reason = "none" if items else "no_scorable_recipes"
        return _build_recommend_result(items, has_more, empty_reason)

    @staticmethod
    def _generate_candidates(db: Session, config: RecipeRecommendConfig) -> list[Recipe]:
        query_recipes = build_recipe_query(
            db,
            query=config.query,
            category=config.category,
            difficulty=config.difficulty,
            cooking_time_label=config.cooking_time_label,
        ).order_by(Recipe.id.desc())

        return query_recipes.all()

    @staticmethod
    def _evaluate_candidates(
        recipes: list[Recipe],
        ingredients_by_recipe: dict[int, list[dict[str, Any]]],
        config: RecipeRecommendConfig,
    ) -> list[dict[str, Any]]:
        del config  # ponytail: mode별 evaluation 추후 config.mode 분기
        ranked: list[dict[str, Any]] = []

        for recipe in recipes:
            recipe_ingredients = ingredients_by_recipe[recipe.id]
            ranked.append(
                {
                    "recipe_id": recipe.id,
                    "recipe": recipe,
                    "_recipe_ingredients": recipe_ingredients,
                    "final_score": 0,
                }
            )

        return ranked

    @staticmethod
    def _rank_candidates(ranked: list[dict[str, Any]], config: RecipeRecommendConfig) -> None:
        del config
        ranked.sort(
            key=lambda row: (
                -row["final_score"],
                -row["recipe_id"],
            )
        )


recommendation_service = RecommendationService()
