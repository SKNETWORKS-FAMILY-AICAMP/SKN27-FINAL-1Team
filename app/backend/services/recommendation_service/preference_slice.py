"""Preference 슬라이스: 완화 가능한 선호 조건 gate + limit 채우기."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.backend.services.recommendation_service._recipe_query import recipe_to_list_item
from app.backend.services.recommendation_service.ingredient_ownership_service import passes_preference_gate
from app.backend.services.recommendation_service.recommend_config import RecipeRecommendConfig


def preference_tiers(config: RecipeRecommendConfig) -> list[tuple[str, RecipeRecommendConfig]]:
    tiers: list[tuple[str, RecipeRecommendConfig]] = [("strict", config)]
    relaxed = replace(config, min_display_match_rate=None)
    if relaxed != config:
        tiers.append(("relaxed", relaxed))
    open_cfg = replace(config, require_any_owned=False, min_display_match_rate=None)
    if open_cfg != tiers[-1][1]:
        tiers.append(("open", open_cfg))
    return tiers


def preference_pool(
    scored: list[dict[str, Any]],
    tier_config: RecipeRecommendConfig,
) -> list[dict[str, Any]]:
    return [
        row
        for row in scored
        if passes_preference_gate(
            row["_ownership"],
            row["_recipe_ingredients"],
            tier_config,
        )
    ]


def slice_by_preference_tiers(
    scored: list[dict[str, Any]],
    tiers: list[tuple[str, RecipeRecommendConfig]],
    limit: int,
) -> tuple[list[dict[str, Any]], bool, str, bool, str]:
    picked: list[dict[str, Any]] = []
    picked_ids: set[int] = set()
    applied_tier = "strict"
    fallback_used = False
    exhausted = False

    for tier_name, tier_config in tiers:
        pool = preference_pool(scored, tier_config)
        available = [row for row in pool if row["recipe_id"] not in picked_ids]

        if pool and not available:
            exhausted = True
            break

        if len(picked) >= limit:
            break

        take = available[: limit - len(picked)]
        if take:
            if tier_name != "strict":
                fallback_used = True
            applied_tier = tier_name
            picked.extend(take)
            picked_ids.update(row["recipe_id"] for row in take)

    has_more = False
    if not exhausted:
        for _, tier_config in tiers:
            pool = preference_pool(scored, tier_config)
            remaining = [row for row in pool if row["recipe_id"] not in picked_ids]
            if remaining:
                has_more = True
                break

    if picked:
        empty_reason = "none"
    elif exhausted:
        empty_reason = "exhausted"
    else:
        empty_reason = "ownership_blocked"

    return picked, has_more, applied_tier, fallback_used, empty_reason


def empty_recommend_result(empty_reason: str) -> dict[str, Any]:
    return {
        "items": [],
        "returned_count": 0,
        "has_more": False,
        "applied_tier": "strict",
        "fallback_used": False,
        "empty_reason": empty_reason,
    }


def build_recommend_result(
    items: list[dict[str, Any]],
    has_more: bool,
    applied_tier: str,
    fallback_used: bool,
    empty_reason: str,
) -> dict[str, Any]:
    response_items = []
    for row in items:
        base = recipe_to_list_item(row["recipe"])
        response_items.append(
            {
                **base,
                "match_rate": row["match_rate"],
                "display_match_rate": row["display_match_rate"],
                "owned_ingredient_count": row["owned_ingredient_count"],
                "missing_ingredient_count": row["missing_ingredient_count"],
                "expiry_score": row["expiry_score"],
                "reason": row["reason"],
            }
        )

    return {
        "items": response_items,
        "returned_count": len(response_items),
        "has_more": has_more,
        "applied_tier": applied_tier,
        "fallback_used": fallback_used,
        "empty_reason": empty_reason,
    }
