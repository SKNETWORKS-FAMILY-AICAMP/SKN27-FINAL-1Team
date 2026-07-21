from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.backend.db.models import Recipe, RecipeIngredient
from app.backend.services.recommendation_service.fridge import classify_fridge_match, fetch_fridge_snapshots
from app.backend.services.recommendation_service.recipe_image_urls import (
    build_main_image_url,
    build_step_image_url,
)


class RecipeDetailService:
    def get_recipe_detail(self, db: Session, recipe_id: int, user_id: int) -> dict[str, Any]:
        recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()
        if not recipe:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="레시피를 찾을 수 없습니다.",
            )

        ingredients = self._fetch_ingredients(db, recipe_id)
        ownership = self._classify_ownership(ingredients, user_id, db)

        return {
            "recipe_id": recipe.id,
            "title": recipe.title,
            "category": recipe.category,
            "difficulty": recipe.difficulty,
            "cooking_time_min": recipe.cooking_time,
            "serving_count": recipe.serving_size,
            "main_image_url": build_main_image_url(recipe.id),
            "owned_ingredients": ownership.owned,
            "maybe_owned_ingredients": ownership.maybe_owned,
            "missing_ingredients": ownership.missing,
            "match_rate": ownership.match_rate,
            "display_match_rate": ownership.display_match_rate,
            "steps": self._to_steps(recipe.id, recipe.recipe_steps),
            "source_url": recipe.source_url,
        }

    def _fetch_ingredients(self, db: Session, recipe_id: int) -> list[dict[str, Any]]:
        rows = (
            db.query(RecipeIngredient)
            .filter(RecipeIngredient.recipe_id == recipe_id)
            .order_by(RecipeIngredient.is_main_ingredient.desc(), RecipeIngredient.id)
            .all()
        )

        return [
            {
                "name": row.raw_ingredient_name or "",
                "amount": self._format_amount(row.required_quantity, row.unit),
                "ingredient_id": int(row.ingredient_id) if row.ingredient_id else None,
            }
            for row in rows
            if row.raw_ingredient_name
        ]

    def _classify_ownership(
        self,
        ingredients: list[dict[str, Any]],
        user_id: int,
        db: Session,
    ):
        if user_id <= 0:
            return classify_fridge_match(ingredients, [])

        fridge_items = fetch_fridge_snapshots(db, user_id, statuses=("normal", "expiring", "expired"))
        return classify_fridge_match(ingredients, fridge_items)

    def _format_amount(self, quantity: Decimal | float | int | None, unit: str | None) -> str | None:
        if quantity is None and not unit:
            return None
        if quantity is None:
            return unit
        # ponytail: strip trailing zeros only in the fractional part (200 must stay 200, not 2)
        value = quantity if isinstance(quantity, Decimal) else Decimal(str(quantity))
        normalized = format(value, "f")
        if "." in normalized:
            normalized = normalized.rstrip("0").rstrip(".")
        if unit:
            return f"{normalized}{unit}"
        return normalized

    def _to_steps(
        self,
        recipe_id: int,
        recipe_steps: list[dict[str, Any]] | None,
    ) -> list[dict[str, Any]]:
        if not recipe_steps:
            return []

        steps: list[dict[str, Any]] = []
        for step in recipe_steps:
            text = step.get("text")
            if not text:
                continue
            steps.append(
                {
                    "title": step.get("title") or f"{step.get('step_no', len(steps) + 1)}단계",
                    "text": str(text),
                    "image_url": build_step_image_url(recipe_id, len(steps) + 1),
                }
            )
        return steps


recipe_detail_service = RecipeDetailService()
