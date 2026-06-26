"""레시피 검색·목록용 SQLAlchemy 쿼리 빌더 (서비스 간 내부 공유)."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Query, Session

from app.backend.db.models import Ingredient, Recipe, RecipeIngredient


def build_recipe_query(
    db: Session,
    *,
    query: str | None = None,
    ingredient: str | None = None,
    category: str | None = None,
    difficulty: str | None = None,
    max_cooking_time_min: int | None = None,
    cooking_time_label: str | None = None,
) -> Query:
    query_recipes = db.query(Recipe)

    normalized_query = (query or "").strip()
    if normalized_query:
        query_recipes = query_recipes.filter(Recipe.title.ilike(f"%{normalized_query}%"))

    normalized_ingredient = (ingredient or "").strip()
    if normalized_ingredient:
        like_pattern = f"%{normalized_ingredient}%"
        query_recipes = (
            query_recipes.join(RecipeIngredient, RecipeIngredient.recipe_id == Recipe.id)
            .join(Ingredient, Ingredient.id == RecipeIngredient.ingredient_id)
            .filter(
                or_(
                    RecipeIngredient.raw_ingredient_name.ilike(like_pattern),
                    Ingredient.name.ilike(like_pattern),
                    Ingredient.normalized_name.ilike(like_pattern),
                )
            )
            .distinct()
        )

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

    return _apply_cooking_time_label_filter(query_recipes, cooking_time_label)


def recipe_to_list_item(recipe: Recipe) -> dict[str, Any]:
    return {
        "recipe_id": recipe.id,
        "title": recipe.title,
        "category": recipe.category,
        "difficulty": recipe.difficulty,
        "cooking_time_min": recipe.cooking_time,
        "serving_count": recipe.serving_size,
        "main_image_url": recipe.image_url,
    }


def _apply_cooking_time_label_filter(query_recipes: Query, label: str | None) -> Query:
    normalized_label = (label or "").strip()
    if not normalized_label or normalized_label == "전체":
        return query_recipes

    if normalized_label == "2시간이상":
        return query_recipes.filter(
            Recipe.cooking_time.isnot(None),
            Recipe.cooking_time >= 120,
        )

    if normalized_label.endswith("이내"):
        max_minutes = _parse_time_label_to_minutes(normalized_label)
        if max_minutes is not None:
            return query_recipes.filter(
                Recipe.cooking_time.isnot(None),
                Recipe.cooking_time <= max_minutes,
            )

    return query_recipes


def _parse_time_label_to_minutes(label: str) -> int | None:
    match = re.search(r"(\d+)", label)
    if not match:
        return None
    amount = int(match.group(1))
    if "시간" in label:
        return amount * 60
    if "분" in label:
        return amount
    return amount


def load_recipe_ingredients_bulk(
    db: Session,
    recipe_ids: list[int],
) -> dict[int, list[dict[str, Any]]]:
    if not recipe_ids:
        return {}

    rows = (
        db.query(RecipeIngredient)
        .filter(RecipeIngredient.recipe_id.in_(recipe_ids))
        .order_by(RecipeIngredient.is_main_ingredient.desc(), RecipeIngredient.id)
        .all()
    )

    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        if not row.raw_ingredient_name:
            continue
        grouped.setdefault(row.recipe_id, []).append(
            {
                "name": row.raw_ingredient_name or "",
                "amount": None,
                "ingredient_id": int(row.ingredient_id) if row.ingredient_id else None,
            }
        )
    return grouped
