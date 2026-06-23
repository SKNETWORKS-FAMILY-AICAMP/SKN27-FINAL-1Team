from __future__ import annotations

import re
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
        cooking_time_label: str | None = None,
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
            cooking_time_label=cooking_time_label,
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
        cooking_time_label: str | None = None,
    ) -> Query:
        query_recipes = db.query(Recipe)

        normalized_query = (query or "").strip()
        if normalized_query:
            query_recipes = query_recipes.filter(Recipe.title.ilike(f"%{normalized_query}%"))

        normalized_category = (category or "").strip()
        if normalized_category and normalized_category != "전체":
            query_recipes = query_recipes.filter(Recipe.category == normalized_category)

        normalized_difficulty = (difficulty or "").strip()
        if normalized_difficulty and normalized_difficulty != "전체":
            query_recipes = query_recipes.filter(Recipe.difficulty == normalized_difficulty)

        if max_cooking_time_min is not None:
            query_recipes = query_recipes.filter(
                Recipe.cooking_time.isnot(None),
                Recipe.cooking_time <= max_cooking_time_min,
            )

        query_recipes = self._apply_cooking_time_label_filter(query_recipes, cooking_time_label)

        return query_recipes

    def _apply_cooking_time_label_filter(self, query_recipes: Query, label: str | None) -> Query:
        normalized_label = (label or "").strip()
        if not normalized_label or normalized_label == "전체":
            return query_recipes

        if normalized_label == "확인필요":
            return query_recipes.filter(Recipe.cooking_time.is_(None))

        if normalized_label == "2시간이상":
            return query_recipes.filter(
                Recipe.cooking_time.isnot(None),
                Recipe.cooking_time >= 120,
            )

        if normalized_label.endswith("이내"):
            max_minutes = self._parse_time_label_to_minutes(normalized_label)
            if max_minutes is not None:
                return query_recipes.filter(
                    Recipe.cooking_time.isnot(None),
                    Recipe.cooking_time <= max_minutes,
                )

        return query_recipes

    def _parse_time_label_to_minutes(self, label: str) -> int | None:
        match = re.search(r"(\d+)", label)
        if not match:
            return None
        amount = int(match.group(1))
        if "시간" in label:
            return amount * 60
        if "분" in label:
            return amount
        return amount

    def _to_item(self, recipe: Recipe) -> dict[str, Any]:
        return {
            "recipe_id": recipe.id,
            "title": recipe.title,
            "category": recipe.category,
            "difficulty": recipe.difficulty,
            "cooking_time_min": recipe.cooking_time,
            "serving_count": recipe.serving_size,
            "main_image_url": recipe.image_url,
        }


recipe_search_service = RecipeSearchService()
