"""추천 API 응답 조립."""

from __future__ import annotations

from typing import Any

from app.backend.services.recommendation_service.recipe_candidate_query import recipe_to_list_item


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
