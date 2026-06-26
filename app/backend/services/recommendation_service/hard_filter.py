"""Hard Filter: 절대 완화되지 않는 추천 제외 조건."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.backend.db.models import Recipe


@dataclass(frozen=True)
class UserHardFilterContext:
    # ponytail: 후속 티켓에서 allergy + disliked 통합 로드
    banned_names: frozenset[str]


def load_hard_filter_context(db: Session, user_id: int) -> UserHardFilterContext:
    del db, user_id
    return UserHardFilterContext(banned_names=frozenset())


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
    del ctx
    return scored
