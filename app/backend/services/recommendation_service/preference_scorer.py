"""Preference 점수·패널티 (tier slice + final_score 합산)."""

from __future__ import annotations

from typing import Any, Literal

from app.backend.services.recommendation_service.ingredient_ownership_service import (
    OwnershipResult,
    compute_match_rates,
)
from app.backend.services.recommendation_service.recommend_config import RecipeRecommendConfig

# ponytail: expiry_score 상한 ~수십, fridge_score 0-100 → expiry 우선 lexicographic; 초과 시 가중치 상향
EXPIRY_WEIGHT_FRIDGE_CONSUME = 1000


def preference_penalty(
    ownership: OwnershipResult,
    recipe_ingredients: list[dict[str, Any]],
    config: RecipeRecommendConfig,
) -> int:
    """미충족 시 양수 패널티, 충족 시 0 (preference_slice tier pool)."""
    owned_count = len(ownership.owned)
    maybe_count = len(ownership.maybe_owned) if config.include_maybe_owned else 0

    if config.require_any_owned and (owned_count + maybe_count) < 1:
        return 1

    if config.min_display_match_rate is not None:
        rates = compute_match_rates(
            owned_count,
            maybe_count,
            len(recipe_ingredients),
        )
        if rates.display_match_rate < config.min_display_match_rate:
            return 1

    return 0


def preference_score_for_rank(
    ownership: OwnershipResult,
    recipe_ingredients: list[dict[str, Any]],
    config: RecipeRecommendConfig,
) -> int:
    """strict config 충족 시 소량 보너스; 미충족은 slice fallback이 처리."""
    return 1 if preference_penalty(ownership, recipe_ingredients, config) == 0 else 0


def build_final_score(
    mode: Literal["fridge_consume", "menu_custom"],
    fridge_score: int,
    expiry_score: int,
    preference_score: int,
    missing_penalty: int,
    *,
    global_score: int = 0,
    personal_score: int = 0,
) -> int:
    # ponytail: global_score / personal_score — 후속 user_cache·global_pool
    base = global_score + personal_score + preference_score - missing_penalty
    if mode == "fridge_consume":
        return expiry_score * EXPIRY_WEIGHT_FRIDGE_CONSUME + fridge_score + base
    return fridge_score + expiry_score + base
