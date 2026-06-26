"""Preference tier fallback 슬라이스."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.backend.services.recommendation_service.recommend_config import RecipeRecommendConfig
from app.backend.services.recommendation_service.recommend_evaluation import tier_config_penalty


def tier_fallback_configs(config: RecipeRecommendConfig) -> list[tuple[str, RecipeRecommendConfig]]:
    tiers: list[tuple[str, RecipeRecommendConfig]] = [("strict", config)]
    relaxed = replace(config, min_display_match_rate=None)
    if relaxed != config:
        tiers.append(("relaxed", relaxed))
    open_cfg = replace(config, require_any_owned=False, min_display_match_rate=None)
    if open_cfg != tiers[-1][1]:
        tiers.append(("open", open_cfg))
    return tiers


def candidates_for_tier(
    scored: list[dict[str, Any]],
    tier_config: RecipeRecommendConfig,
) -> list[dict[str, Any]]:
    return [
        row
        for row in scored
        if tier_config_penalty(
            row["_fridge_match"],
            row["_recipe_ingredients"],
            tier_config,
        )
        == 0
    ]


def slice_with_tier_fallback(
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
        pool = candidates_for_tier(scored, tier_config)
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
            pool = candidates_for_tier(scored, tier_config)
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
