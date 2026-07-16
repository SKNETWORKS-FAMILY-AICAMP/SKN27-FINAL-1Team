from __future__ import annotations

import re
from typing import Any

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
    if keyword in (
        "걸", "있는", "이걸", "이것", "그걸", "그것", "재료", "식재료", "보유재료", "냉장고",
        "내", "제", "나", "내식재료", "제식재료", "남은거",
    ):
        return ""
    return _normalize_recipe_keyword(keyword)


def _normalize_recipe_keyword(keyword: str) -> str:
    aliases = {"파": "대파"}
    return aliases.get(keyword, keyword)


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
    personal_recipe_words = ("내식재료", "내재료", "보유식재료", "보유재료", "냉장고재료", "있는걸로", "이걸로")
    if intent in ("inventory.list", "inventory.expiring"):
        return True
    if intent == "recipe.recommend" and any(word in normalized for word in personal_recipe_words):
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
    aliases = {"파": {"대파", "쪽파", "실파"}, "계란": {"달걀"}, "달걀": {"계란"}}
    if normalized_keyword == normalized_name or normalized_name in aliases.get(normalized_keyword, set()):
        return True
    if len(normalized_keyword) <= 1:
        return False
    misleading_suffixes = ("소스", "가루", "분말", "즙", "청", "오일", "잼", "스톡")
    if normalized_name.startswith(normalized_keyword) and normalized_name.endswith(misleading_suffixes):
        return False
    if normalized_name.startswith(normalized_keyword) and any(suffix in normalized_name for suffix in misleading_suffixes):
        return False
    return normalized_keyword in normalized_name or normalized_name in normalized_keyword


def _keyword_tokens(keyword: str) -> list[str]:
    stopwords = {
        "먹다남은", "남은", "먹다", "보관", "보관법", "보관방법", "세척", "세척법", "세척방법",
        "손질", "손질법", "손질방법", "신선도", "확인법", "알려줘", "식재료", "레시피", "어떡하지", "어떡해",
    }
    return [
        token
        for token in re.findall(r"[가-힣A-Za-z0-9]+", keyword.lower())
        if len(token) > 1 and token not in stopwords
    ]


def _is_relevant_search_result(keyword: str, item: dict[str, Any]) -> bool:
    tokens = _keyword_tokens(keyword)
    if not tokens:
        return False
    haystack = f"{item.get('title', '')} {item.get('content', '')}".lower()
    words = _keyword_tokens(haystack)
    primary = tokens[0]
    return any(_is_guide_result_match(primary, word) for word in words)
