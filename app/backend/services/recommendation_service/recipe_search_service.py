from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.backend.db.models import Recipe
from app.backend.services.recommendation_service._recipe_query import (
    build_recipe_query,
    recipe_to_list_item,
)


class RecipeSearchService:
    DEFAULT_PAGE_SIZE = 20
    MAX_PAGE_SIZE = 100

    def search_recipes(
        self,
        db: Session,
        query: str | None = None,
        ingredient: str | None = None,
        category: str | None = None,
        difficulty: str | None = None,
        max_cooking_time_min: int | None = None,
        cooking_time_label: str | None = None,
        main_ingredient_only: bool = False,
        page: int = 1,
        page_size: int | None = None,
    ) -> dict[str, Any]:
        """레시피명(title) 부분일치 검색 및 기본 필터·페이지네이션."""
        page = max(page, 1)
        if page_size is None:
            page_size = self.DEFAULT_PAGE_SIZE
        page_size = min(max(page_size, 1), self.MAX_PAGE_SIZE)

        query_recipes = build_recipe_query(
            db,
            query=query,
            ingredient=ingredient,
            category=category,
            difficulty=difficulty,
            max_cooking_time_min=max_cooking_time_min,
            cooking_time_label=cooking_time_label,
            main_ingredient_only=main_ingredient_only,
        )

        total = query_recipes.count()
        recipes = (
            query_recipes.order_by(Recipe.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        return {
            "items": [recipe_to_list_item(recipe) for recipe in recipes],
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_next": page * page_size < total,
        }


recipe_search_service = RecipeSearchService()
