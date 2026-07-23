from __future__ import annotations

from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Query, Session

from app.backend.db.models import Recipe
from app.backend.services.recommendation_service.recipe_query import (
    build_recipe_query,
    recipe_to_list_item,
)


class RecipeSearchService:
    DEFAULT_PAGE_SIZE = 20
    MAX_PAGE_SIZE = 100
    COOKING_TIME_LABELS = ("15분이내", "30분이내", "30분이상")

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

        facets = self._build_facets(
            db=db,
            total=total,
            query=query,
            ingredient=ingredient,
            category=category,
            difficulty=difficulty,
            max_cooking_time_min=max_cooking_time_min,
            cooking_time_label=cooking_time_label,
            main_ingredient_only=main_ingredient_only,
        )

        return {
            "items": [recipe_to_list_item(recipe) for recipe in recipes],
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_next": page * page_size < total,
            "facets": facets,
        }

    def _build_facets(
        self,
        *,
        db: Session,
        total: int,
        query: str | None,
        ingredient: str | None,
        category: str | None,
        difficulty: str | None,
        max_cooking_time_min: int | None,
        cooking_time_label: str | None,
        main_ingredient_only: bool,
    ) -> dict[str, list[str]]:
        if total <= 0:
            return {"categories": [], "difficulties": [], "cooking_time_labels": []}

        common = {
            "db": db,
            "query": query,
            "ingredient": ingredient,
            "max_cooking_time_min": max_cooking_time_min,
            "main_ingredient_only": main_ingredient_only,
        }
        category_query = build_recipe_query(
            **common,
            category=None,
            difficulty=difficulty,
            cooking_time_label=cooking_time_label,
        )
        difficulty_query = build_recipe_query(
            **common,
            category=category,
            difficulty=None,
            cooking_time_label=cooking_time_label,
        )
        cooking_time_query_args = {
            **common,
            "category": category,
            "difficulty": difficulty,
        }

        return {
            "categories": self._distinct_strings(category_query, Recipe.category),
            "difficulties": self._distinct_strings(difficulty_query, Recipe.difficulty),
            "cooking_time_labels": [
                label
                for label in self.COOKING_TIME_LABELS
                if build_recipe_query(
                    **cooking_time_query_args,
                    cooking_time_label=label,
                ).limit(1).first()
                is not None
            ],
        }

    @staticmethod
    def _distinct_strings(query: Query, column: Any) -> list[str]:
        rows = (
            query.with_entities(column)
            .filter(column.isnot(None), func.trim(column) != "")
            .distinct()
            .order_by(column.asc())
            .all()
        )
        return [str(row[0]).strip() for row in rows if row[0] and str(row[0]).strip()]


recipe_search_service = RecipeSearchService()
