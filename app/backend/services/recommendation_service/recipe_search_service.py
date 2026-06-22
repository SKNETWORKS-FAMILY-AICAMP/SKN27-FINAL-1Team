from __future__ import annotations

from typing import Any
from sqlalchemy.orm import Query, Session
from app.backend.db.models import Recipe

class RecipeSearchService:
    DEFAULT_PAGE_SIZE = 20
    MAX_PAGE_SIZE = 100

    def search_recipes(
        self,
        db: Session,
        query: str | None = None,
        category: str | None = None,
        difficulty: str | None = None,
        max_cooking_time_min: int | None = None,
        page: int = 1,
        page_size: int | None = None,
    ) -> dict[str, Any]:
        """레시피명(title) 부분일치 검색 및 기본 필터·페이지네이션."""
        page = max(page, 1)
        if page_size is None:
            page_size = self.DEFAULT_PAGE_SIZE
        page_size = min(max(page_size, 1), self.MAX_PAGE_SIZE)

        query_recipes = self._build_query(
            db=db,
            query=query,
            category=category,
            difficulty=difficulty,
            max_cooking_time_min=max_cooking_time_min,
        )

        total = query_recipes.count()
        recipes = (
            query_recipes.order_by(Recipe.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        return {
            "items": [self._to_item(recipe) for recipe in recipes],
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_next": page * page_size < total,
        }

    def _build_query(
        self,
        db: Session,
        query: str | None,
        category: str | None,
        difficulty: str | None,
        max_cooking_time_min: int | None,
    ) -> Query:
        query_recipes = db.query(Recipe)

        normalized_query = (query or "").strip()
        if normalized_query:
            query_recipes = query_recipes.filter(Recipe.title.ilike(f"%{normalized_query}%"))

        normalized_category = (category or "").strip()
        if normalized_category:
            query_recipes = query_recipes.filter(Recipe.category == normalized_category)

        normalized_difficulty = (difficulty or "").strip()
        if normalized_difficulty:
            query_recipes = query_recipes.filter(Recipe.difficulty == normalized_difficulty)

        if max_cooking_time_min is not None:
            query_recipes = query_recipes.filter(
                Recipe.cooking_time.isnot(None),
                Recipe.cooking_time <= max_cooking_time_min,
            )

        return query_recipes

    def _to_item(self, recipe: Recipe) -> dict[str, Any]:
        return {
            "recipe_id": recipe.id,
            "recipe_name": recipe.title,
            "category": recipe.category,
            "difficulty": recipe.difficulty,
            "cooking_time_min": recipe.cooking_time,
            "serving_count": recipe.serving_size,
            "main_image_url": recipe.image_url,
        }


recipe_search_service = RecipeSearchService()
