from __future__ import annotations

import re
from typing import Any

from .recipe_config import (
    GUIDE_MATCH_ALIASES,
    GUIDE_MISLEADING_SUFFIXES,
    KEYWORD_TOKEN_STOPWORDS,
    PAIRING_JOSA,
    PAIRING_WORDS,
    RECIPE_INGREDIENT_EXCLUDE_KEYWORDS,
    RECIPE_KEYWORD_ALIASES,
    RECOMMEND_WORDS,
    REQUIRES_LOGIN_PERSONAL_WORDS,
    SEARCH_WORDS,
)

LOGIN_REQUIRED_REPLY = "로그인이 필요한 질문이에요. 비회원 상태에서는 보관법이나 일반 레시피 검색을 이용할 수 있어요."


def _extract_keyword(text: str) -> str:
    cleaned = re.sub(
        r"(냉장고|냉동고|냉장실|냉동실|실온|냉장|냉동|상온|먹다\s*남은|먹다남은|남은|먹다|어떡하지|어떡해|어떻게하지|보관법|보관방법|보관해|보관|세척법|세척방법|세척|씻|손질법|손질방법|손질|신선도|확인법|확인|어떻게|가이드|레시피|요리|추천|알려줘|찾아줘|해줘|좀|해먹을|만들|영양성분|영양|칼로리|열량|단백질|탄수화물|지방|당류|나트륨|제철)",
        " ",
        text,
    )
    words = [
        word.strip()
        for word in cleaned.split()
        if word.strip()
        and word.strip()
        not in ("내", "제", "나", "어떤", "무슨", "이", "그", "저", "이런", "그런", "저런", "수", "있어", "있어?", "있나요", "있나요?")
    ]
    return words[0] if words else ""


def _extract_recipe_ingredient(text: str) -> str:
    match = re.search(r"(?:남은\s*)?([가-힣A-Za-z0-9]+?)(?:으로|로).*(?:뭐|뭘|무엇|메뉴|레시피|요리|만들|추천)", text)
    if not match:
        match = re.search(r"(?:남은\s*)?([가-힣A-Za-z0-9]+?)\s*(?:빨리|먼저|써야|처리).*(?:뭐|뭘|무엇|메뉴|레시피|요리|추천|하지)", text)
    if not match:
        match = re.search(r"^\s*(?:먹다\s*남은|먹다남은|남은)?\s*([가-힣A-Za-z0-9]+?)\s*(?:어디에\s*)?(?:쓸\s*수|쓸수|활용|처리)", text)
    if not match:
        return ""
    keyword = match.group(1).strip()
    if keyword in RECIPE_INGREDIENT_EXCLUDE_KEYWORDS:
        return ""
    return _normalize_recipe_keyword(keyword)


def _normalize_recipe_keyword(keyword: str) -> str:
    return RECIPE_KEYWORD_ALIASES.get(keyword, keyword)


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
    """이전 봇 응답 레시피를 후보에서 제외한다. slots.shown_recipe_ids 우선."""
    shown_ids = extract_shown_recipe_ids(history)
    if shown_ids:
        filtered = [item for item in items if item.get("recipe_id") not in shown_ids]
        if not filtered:
            filtered = list(items)
        return filtered

    # ponytail: history slots가 없으면 문자열 기반 fallback 유지
    past_bot_texts = " ".join(
        msg.get("text", "") if isinstance(msg, dict) else getattr(msg, "text", "")
        for msg in history
        if (msg.get("role", "") if isinstance(msg, dict) else getattr(msg, "role", "")) == "bot"
    )
    filtered = [item for item in items if item.get("title", "") not in past_bot_texts]
    if not filtered:
        filtered = list(items)
    return filtered


def _apply_josa(word: str, josa_type: str) -> str:
    if not word:
        return ""
    last_char = word[-1]
    if not ("가" <= last_char <= "힣"):
        return word + ("가" if josa_type == "이가" else "는" if josa_type == "은는" else "를")
    has_jongseong = (ord(last_char) - 44032) % 28 > 0
    if josa_type == "이가":
        return word + ("이" if has_jongseong else "가")
    if josa_type == "은는":
        return word + ("은" if has_jongseong else "는")
    if josa_type == "을를":
        return word + ("을" if has_jongseong else "를")
    if josa_type == "과와":
        return word + ("과" if has_jongseong else "와")
    return word


def _requires_login(intent: str, text: str) -> bool:
    normalized = text.replace(" ", "").lower()
    if intent in ("inventory.list", "inventory.expiring"):
        return True
    if intent == "recipe.recommend" and any(word in normalized for word in REQUIRES_LOGIN_PERSONAL_WORDS):
        return True
    if intent == "recipe.recommend" and not _extract_recipe_ingredient(text):
        return True
    return False


def _is_cooking_time_question(text: str) -> bool:
    normalized = text.replace(" ", "").lower()
    return any(word in normalized for word in ("에어프라이", "몇분", "몇도", "온도", "조리시간", "굽는시간", "익히는시간"))


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


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text or "").lower()


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


def analyze_recipe_intent(text: str, history: list | None = None) -> str:
    """recipe.search / recipe.recommend / recipe.pairing 3-way 분류."""
    del history  # ponytail: P3 — 시그니처만 고정, follow-up/LLM은 P5

    if _is_cooking_time_question(text):
        return "recipe.search"

    compact = _compact(text)
    if any(word in compact for word in PAIRING_WORDS) or PAIRING_JOSA.search(compact):
        return "recipe.pairing"
    if any(word in compact for word in RECOMMEND_WORDS):
        return "recipe.recommend"
    if any(word in compact for word in SEARCH_WORDS):
        return "recipe.search"
    return "recipe.recommend"
