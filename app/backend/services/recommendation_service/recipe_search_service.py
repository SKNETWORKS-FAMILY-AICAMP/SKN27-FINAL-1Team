from __future__ import annotations

import math
import re
from collections.abc import Callable
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Query, Session

from app.backend.db.models import Ingredient, IngredientAlias, Recipe, RecipeIngredient
from app.backend.services.recommendation_service.recipe_query import (
    build_recipe_query,
    recipe_to_list_item,
)


class RecipeSearchService:
    DEFAULT_PAGE_SIZE = 20
    MAX_PAGE_SIZE = 100
    SIMILARITY_THRESHOLD = 0.30
    MIN_SIMILARITY_QUERY_LENGTH = 3
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

        query_builder, order_by = self._select_query_builder(
            db=db,
            query=query,
            ingredient=ingredient,
            category=category,
            difficulty=difficulty,
            max_cooking_time_min=max_cooking_time_min,
            cooking_time_label=cooking_time_label,
            main_ingredient_only=main_ingredient_only,
        )
        query_recipes = query_builder(category, difficulty, cooking_time_label)

        total = query_recipes.count()
        recipes = (
            query_recipes.order_by(*order_by)
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        facets = self._build_facets(
            db=db,
            total=total,
            query_builder=query_builder,
            category=category,
            difficulty=difficulty,
            cooking_time_label=cooking_time_label,
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
        query_builder: Callable[[str | None, str | None, str | None], Query],
        category: str | None,
        difficulty: str | None,
        cooking_time_label: str | None,
    ) -> dict[str, list[str]]:
        if total <= 0:
            return {"categories": [], "difficulties": [], "cooking_time_labels": []}

        category_query = query_builder(None, difficulty, cooking_time_label)
        difficulty_query = query_builder(category, None, cooking_time_label)

        return {
            "categories": self._distinct_strings(category_query, Recipe.category),
            "difficulties": self._distinct_strings(difficulty_query, Recipe.difficulty),
            "cooking_time_labels": [
                label
                for label in self.COOKING_TIME_LABELS
                if query_builder(category, difficulty, label).limit(1).first()
                is not None
            ],
        }

    def _select_query_builder(
        self,
        *,
        db: Session,
        query: str | None,
        ingredient: str | None,
        category: str | None,
        difficulty: str | None,
        max_cooking_time_min: int | None,
        cooking_time_label: str | None,
        main_ingredient_only: bool,
    ) -> tuple[Callable[[str | None, str | None, str | None], Query], tuple[Any, ...]]:
        def existing_builder(
            selected_category: str | None,
            selected_difficulty: str | None,
            selected_time: str | None,
        ) -> Query:
            return build_recipe_query(
                db,
                query=query,
                ingredient=ingredient,
                category=selected_category,
                difficulty=selected_difficulty,
                max_cooking_time_min=max_cooking_time_min,
                cooking_time_label=selected_time,
                main_ingredient_only=main_ingredient_only,
            )

        normalized_query = (query or "").strip()
        if not normalized_query or (ingredient or "").strip():
            return existing_builder, (Recipe.id.desc(),)

        if existing_builder(category, difficulty, cooking_time_label).count() > 0:
            return existing_builder, (Recipe.id.desc(),)

        search_text = normalize_recipe_search_text(normalized_query)
        ingredient_ids = self._extract_ingredient_ids(db, search_text)
        if ingredient_ids:
            minimum_matches = minimum_ingredient_matches(len(ingredient_ids))
            matched_counts = (
                db.query(
                    RecipeIngredient.recipe_id.label("recipe_id"),
                    func.count(func.distinct(RecipeIngredient.ingredient_id)).label("matched_count"),
                )
                .filter(RecipeIngredient.ingredient_id.in_(ingredient_ids))
            )
            if main_ingredient_only:
                matched_counts = matched_counts.filter(RecipeIngredient.is_main_ingredient.is_(True))
            matched_counts = (
                matched_counts.group_by(RecipeIngredient.recipe_id)
                .having(func.count(func.distinct(RecipeIngredient.ingredient_id)) >= minimum_matches)
                .subquery()
            )

            def ingredient_builder(
                selected_category: str | None,
                selected_difficulty: str | None,
                selected_time: str | None,
            ) -> Query:
                return (
                    build_recipe_query(
                        db,
                        category=selected_category,
                        difficulty=selected_difficulty,
                        max_cooking_time_min=max_cooking_time_min,
                        cooking_time_label=selected_time,
                    )
                    .join(matched_counts, matched_counts.c.recipe_id == Recipe.id)
                )

            ingredient_query = ingredient_builder(category, difficulty, cooking_time_label)
            if ingredient_query.count() > 0:
                return ingredient_builder, (matched_counts.c.matched_count.desc(), Recipe.id.desc())

        if len(_compact_search_text(search_text)) >= self.MIN_SIMILARITY_QUERY_LENGTH:
            similarity_score = func.similarity(Recipe.title, search_text)

            def similarity_builder(
                selected_category: str | None,
                selected_difficulty: str | None,
                selected_time: str | None,
            ) -> Query:
                return build_recipe_query(
                    db,
                    category=selected_category,
                    difficulty=selected_difficulty,
                    max_cooking_time_min=max_cooking_time_min,
                    cooking_time_label=selected_time,
                ).filter(similarity_score >= self.SIMILARITY_THRESHOLD)

            return similarity_builder, (similarity_score.desc(), Recipe.id.desc())

        def empty_builder(
            selected_category: str | None,
            selected_difficulty: str | None,
            selected_time: str | None,
        ) -> Query:
            return build_recipe_query(
                db,
                category=selected_category,
                difficulty=selected_difficulty,
                max_cooking_time_min=max_cooking_time_min,
                cooking_time_label=selected_time,
            ).filter(Recipe.id.is_(None))

        return empty_builder, (Recipe.id.desc(),)

    @staticmethod
    def _extract_ingredient_ids(db: Session, search_text: str) -> list[int]:
        compact_query = _compact_search_text(search_text)
        if not compact_query:
            return []

        rows = (
            db.query(Ingredient.id, Ingredient.name, Ingredient.normalized_name, IngredientAlias.alias_name)
            .outerjoin(IngredientAlias, IngredientAlias.ingredient_id == Ingredient.id)
            .all()
        )
        candidates: set[tuple[str, int]] = set()
        for ingredient_id, name, normalized_name, alias_name in rows:
            for candidate in (name, normalized_name, alias_name):
                compact_candidate = _compact_search_text(candidate or "")
                if compact_candidate:
                    candidates.add((compact_candidate, int(ingredient_id)))

        occupied = [False] * len(compact_query)
        matched_ids: list[int] = []
        for candidate, ingredient_id in sorted(candidates, key=lambda item: (-len(item[0]), item[0], item[1])):
            start = compact_query.find(candidate)
            while start >= 0:
                end = start + len(candidate)
                if not any(occupied[start:end]):
                    occupied[start:end] = [True] * len(candidate)
                    if ingredient_id not in matched_ids:
                        matched_ids.append(ingredient_id)
                    break
                start = compact_query.find(candidate, start + 1)
        return matched_ids

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


_GENERIC_SEARCH_SUFFIX = re.compile(r"(?:\s*(?:요리|레시피|메뉴|음식)\s*)+$")
_SEARCH_SEPARATOR = re.compile(r"[\s,;/|+&·]+")
_NON_WORD_SEARCH_CHARACTER = re.compile(r"[^0-9A-Za-zㄱ-ㆎ가-힣]+")


def normalize_recipe_search_text(value: str) -> str:
    normalized = _SEARCH_SEPARATOR.sub(" ", (value or "").strip())
    normalized = _GENERIC_SEARCH_SUFFIX.sub("", normalized).strip()
    return re.sub(r"\s+", " ", normalized)


def _compact_search_text(value: str) -> str:
    return _NON_WORD_SEARCH_CHARACTER.sub("", (value or "").lower())


def minimum_ingredient_matches(recognized_count: int) -> int:
    if recognized_count <= 0:
        return 0
    if recognized_count == 1:
        return 1
    if recognized_count == 2:
        return 2
    return math.ceil(recognized_count * 0.5)
