"""Hard Filter: 절대 완화되지 않는 추천 제외 조건."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.backend.db.models import Ingredient, Recipe, UserPreference
from app.backend.services.recommendation_service.fridge_ingredient_match import (
    FridgeItemSnapshot,
    recipe_contains_banned,
)


@dataclass(frozen=True)
class UserHardFilterContext:
    banned_items: tuple[FridgeItemSnapshot, ...]


def _split_csv_names(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def _normalize_ingredient_name(name: str) -> str:
    return name.strip().replace(" ", "").lower()


def _resolve_ingredient_id(db: Session, name: str) -> int | None:
    normalized = _normalize_ingredient_name(name)
    if not normalized:
        return None
    row = db.query(Ingredient).filter(Ingredient.normalized_name == normalized).first()
    return int(row.id) if row else None


def load_hard_filter_context(db: Session, user_id: int) -> UserHardFilterContext:
    pref = db.query(UserPreference).filter(UserPreference.user_id == user_id).first()
    if pref is None:
        return UserHardFilterContext(banned_items=())

    seen: set[str] = set()
    names: list[str] = []
    for field in (pref.allergies, pref.disliked_ingredients):
        for name in _split_csv_names(field):
            key = _normalize_ingredient_name(name)
            if key and key not in seen:
                seen.add(key)
                names.append(name)

    banned_items = tuple(
        FridgeItemSnapshot(
            ingredient_id=_resolve_ingredient_id(db, name),
            fridge_name=name,
        )
        for name in names
    )
    return UserHardFilterContext(banned_items=banned_items)


def filter_candidates_by_id(
    recipes: list[Recipe],
    exclude_ids: list[int],
) -> list[Recipe]:
    if not exclude_ids:
        return recipes
    exclude = set(exclude_ids)
    return [recipe for recipe in recipes if recipe.id not in exclude]


def filter_scored_by_banned(
    scored: list[dict[str, Any]],
    ctx: UserHardFilterContext,
) -> list[dict[str, Any]]:
    if not ctx.banned_items:
        return scored
    banned = list(ctx.banned_items)
    return [
        row
        for row in scored
        if not recipe_contains_banned(row["_recipe_ingredients"], banned)
    ]
