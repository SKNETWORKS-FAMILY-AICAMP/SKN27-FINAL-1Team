from __future__ import annotations

import re

from .recipe_utils import _is_cooking_time_question

_RECOMMEND_WORDS = (
    "추천", "뭐해먹", "뭐먹", "뭐하지", "뭘", "만들지", "만들수", "만들수있는", "만들수있",
    "할수", "할수있는", "메뉴", "냉장고파먹", "쓸수", "쓸수있", "활용", "어디에쓸", "다른거", "딴거",
)
_SEARCH_WORDS = ("레시피", "요리법", "요리")

_GOLDEN_CASES = (
    ("김치볶음밥 레시피", "recipe.search"),
    ("에어프라이어 치킨 몇 분?", "recipe.search"),
    ("두부로 뭐 해먹지?", "recipe.recommend"),
    ("오늘 뭐 해먹지?", "recipe.recommend"),
    ("냉장고 재료로 뭐 해먹지?", "recipe.recommend"),
)


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text or "").lower()


def analyze_recipe_intent(text: str, history: list | None = None) -> str:
    """recipe.search / recipe.recommend 2-way 분류."""
    del history  # ponytail: P3 — 시그니처만 고정, follow-up/LLM은 P5

    if _is_cooking_time_question(text):
        return "recipe.search"

    compact = _compact(text)
    if any(word in compact for word in _RECOMMEND_WORDS):
        return "recipe.recommend"
    if any(word in compact for word in _SEARCH_WORDS):
        return "recipe.search"
    return "recipe.recommend"


if __name__ == "__main__":
    for utterance, expected in _GOLDEN_CASES:
        actual = analyze_recipe_intent(utterance)
        assert actual == expected, f"{utterance!r}: expected {expected!r}, got {actual!r}"
    print("recipe_intents ok")
