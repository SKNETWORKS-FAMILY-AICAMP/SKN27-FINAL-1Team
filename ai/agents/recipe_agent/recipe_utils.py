from __future__ import annotations

import re
from typing import Any, Literal

from .recipe_config import (
    GUIDE_MATCH_ALIASES,
    GUIDE_MISLEADING_SUFFIXES,
    KEYWORD_TOKEN_STOPWORDS,
)
from .recipe_state import RecipeToolPayload


def build_recipe_actions(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """레시피 목록을 화면 이동 액션으로 변환한다."""

    actions: list[dict[str, Any]] = []
    for item in items[:3]:
        recipe_id = item.get("recipe_id")
        title = item.get("title")
        if not recipe_id or not title:
            continue
        actions.append({"label": title, "url": f"/recipes/{recipe_id}", "data": {"recipe_id": recipe_id, "title": title}})
    return actions


def rank_recipe_search_results(keyword: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """검색어 일치도, 난이도, 조리 시간 순으로 레시피를 정렬한다."""

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


def sort_fridge_recommendations(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """보유 재료 활용도가 높은 냉장고 추천을 우선 배치한다."""

    return sorted(
        items,
        key=lambda x: (
            -x.get("owned_ingredient_count", 0),
            x.get("missing_ingredient_count", 0),
            -x.get("final_score", 0),
        ),
    )


def exclude_previously_shown_recipes(items: list[dict[str, Any]], history: list) -> list[dict[str, Any]]:
    """slots.shown_recipe_ids에 기록된 이전 추천을 후보에서 제외한다."""
    shown_ids = extract_shown_recipe_ids(history)
    filtered = [item for item in items if item.get("recipe_id") not in shown_ids]
    return filtered or list(items)


def matches_ingredient_keyword(keyword: str, candidate: str) -> bool:
    """별칭과 오인 가능 접미사를 고려해 식재료 키워드 일치 여부를 판단한다."""

    normalized_keyword = keyword.replace(" ", "").lower()
    normalized_name = candidate.replace(" ", "").lower()
    if normalized_keyword == normalized_name or normalized_name in GUIDE_MATCH_ALIASES.get(normalized_keyword, set()):
        return True
    if len(normalized_keyword) <= 1:
        return False
    if normalized_name.startswith(normalized_keyword) and normalized_name.endswith(GUIDE_MISLEADING_SUFFIXES):
        return False
    if normalized_name.startswith(normalized_keyword) and any(suffix in normalized_name for suffix in GUIDE_MISLEADING_SUFFIXES):
        return False
    return normalized_keyword in normalized_name or normalized_name in normalized_keyword


def extract_search_tokens(keyword: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[가-힣A-Za-z0-9]+", keyword.lower())
        if len(token) > 1 and token not in KEYWORD_TOKEN_STOPWORDS
    ]


def is_relevant_external_result(keyword: str, item: dict[str, Any]) -> bool:
    """외부 검색 결과가 요청한 핵심 식재료와 관련 있는지 확인한다."""

    tokens = extract_search_tokens(keyword)
    if not tokens:
        return False
    haystack = f"{item.get('title', '')} {item.get('content', '')}".lower()
    words = extract_search_tokens(haystack)
    primary = tokens[0]
    return any(matches_ingredient_keyword(primary, word) for word in words)


def build_tool_payload_json(
    *,
    tool_name: str,
    status: Literal["success", "empty", "error"],
    metadata_policy: Literal["actions", "sources", "both", "none"] = "none",
    message: str,
    actions: list[dict[str, Any]] | None = None,
    sources: list[dict[str, str]] | None = None,
    data: dict[str, Any] | None = None,
) -> str:
    """Recipe Tool의 공통 응답을 검증된 JSON 문자열로 직렬화한다."""

    return RecipeToolPayload(
        tool=tool_name,
        status=status,
        metadata_policy=metadata_policy,
        message=message,
        actions=actions or [],
        sources=sources or [],
        data=data or {},
    ).model_dump_json()


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
