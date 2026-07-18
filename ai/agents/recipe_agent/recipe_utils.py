from __future__ import annotations

import re
from typing import Any

from .recipe_config import (
    GUIDE_MATCH_ALIASES,
    GUIDE_MISLEADING_SUFFIXES,
    KEYWORD_TOKEN_STOPWORDS,
)


def _recipe_actions(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for item in items[:3]:
        recipe_id = item.get("recipe_id")
        title = item.get("title")
        if not recipe_id or not title:
            continue
        actions.append({"label": title, "url": f"/recipes/{recipe_id}", "data": {"recipe_id": recipe_id, "title": title}})
    return actions


def _rank_recipe_items(keyword: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized_keyword = keyword.replace(" ", "")

    def score(item: dict[str, Any]) -> tuple[int, int, int]:
        title = (item.get("title") or "").replace(" ", "")
        difficulty = item.get("difficulty") or ""
        cooking_time = item.get("cooking_time_min") or 9999
        return (
            0 if normalized_keyword and normalized_keyword in title else 1,
            0 if difficulty == "초급" else 1,
            int(cooking_time),
        )

    return sorted(items, key=score)


def _sort_fridge_candidates(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        items,
        key=lambda x: (
            -x.get("owned_ingredient_count", 0),
            x.get("missing_ingredient_count", 0),
            -x.get("final_score", 0),
        ),
    )


def _exclude_previous_items(items: list[dict[str, Any]], history: list) -> list[dict[str, Any]]:
    """slots.shown_recipe_ids에 기록된 이전 추천을 후보에서 제외한다."""
    shown_ids = extract_shown_recipe_ids(history)
    filtered = [item for item in items if item.get("recipe_id") not in shown_ids]
    return filtered or list(items)


def _is_guide_result_match(keyword: str, guide_name: str) -> bool:
    normalized_keyword = keyword.replace(" ", "").lower()
    normalized_name = guide_name.replace(" ", "").lower()
    if normalized_keyword == normalized_name or normalized_name in GUIDE_MATCH_ALIASES.get(normalized_keyword, set()):
        return True
    if len(normalized_keyword) <= 1:
        return False
    if normalized_name.startswith(normalized_keyword) and normalized_name.endswith(GUIDE_MISLEADING_SUFFIXES):
        return False
    if normalized_name.startswith(normalized_keyword) and any(suffix in normalized_name for suffix in GUIDE_MISLEADING_SUFFIXES):
        return False
    return normalized_keyword in normalized_name or normalized_name in normalized_keyword


def _keyword_tokens(keyword: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[가-힣A-Za-z0-9]+", keyword.lower())
        if len(token) > 1 and token not in KEYWORD_TOKEN_STOPWORDS
    ]


def _is_relevant_search_result(keyword: str, item: dict[str, Any]) -> bool:
    tokens = _keyword_tokens(keyword)
    if not tokens:
        return False
    haystack = f"{item.get('title', '')} {item.get('content', '')}".lower()
    words = _keyword_tokens(haystack)
    primary = tokens[0]
    return any(_is_guide_result_match(primary, word) for word in words)


def extract_shown_recipe_ids(history: list | None) -> set[int]:
    """history의 bot slots.shown_recipe_ids에서 recipe_id를 수집한다."""
    shown: set[int] = set()
    for message in history or []:
        role = message.get("role", "") if isinstance(message, dict) else getattr(message, "role", "")
        if role != "bot":
            continue
        slots = message.get("slots", {}) if isinstance(message, dict) else getattr(message, "slots", {}) or {}
        if not isinstance(slots, dict):
            continue
        ids = slots.get("shown_recipe_ids") or []
        if not isinstance(ids, list):
            continue
        for rid in ids:
            try:
                shown.add(int(rid))
            except (TypeError, ValueError):
                continue
    return shown
