from __future__ import annotations

import re

#
# Agent identity
#
AGENT_NAME = "recipe"

#
# Templates / fields
#
TEMPLATE_RECIPE_SEARCH = "RECIPE_SEARCH"
TEMPLATE_INGREDIENT_RECOMMEND = "INGREDIENT_RECOMMEND"
TEMPLATE_FRIDGE_RECOMMEND = "FRIDGE_RECOMMEND"
TEMPLATE_RECIPE_PAIRING = "RECIPE_PAIRING"

SEARCH_TEMPLATE_FIELDS = (
    "keyword",
    "recipe_candidates",
    "selected_recipes",
    "actions",
    "sources",
)

INGREDIENT_TEMPLATE_FIELDS = (
    "ingredient",
    "constraints",
    "recipe_candidates",
    "selected_recipes",
    "actions",
)

FRIDGE_TEMPLATE_FIELDS = (
    "inventory_status",
    "user_preferences",
    "recipe_candidates",
    "ranked_recipes",
    "owned_ingredient_count",
    "missing_ingredient_count",
    "actions",
)

TEMPLATE_FIELDS_BY_NAME = {
    TEMPLATE_RECIPE_SEARCH: SEARCH_TEMPLATE_FIELDS,
    TEMPLATE_INGREDIENT_RECOMMEND: INGREDIENT_TEMPLATE_FIELDS,
    TEMPLATE_FRIDGE_RECOMMEND: FRIDGE_TEMPLATE_FIELDS,
}

MAX_DISPLAY_RECIPES = 3

#
# Recommend constraints (data-only)
#
CONSTRAINT_EASY_30 = {"difficulty": "초급", "cooking_time_label": "30분이내", "main_ingredient_only": True}
CONSTRAINT_INGREDIENT_ONLY = {"main_ingredient_only": True}

#
# External tool allowlist (used by orchestrator filters)
#
EXTERNAL_TOOLS = frozenset({"external_search_tool"})

#
# Intent classification (data-only)
#
RECOMMEND_WORDS = (
    "추천",
    "뭐해먹",
    "뭐먹",
    "뭐하지",
    "뭘",
    "만들지",
    "만들수",
    "만들수있는",
    "만들수있",
    "할수",
    "할수있는",
    "메뉴",
    "냉장고파먹",
    "쓸수",
    "쓸수있",
    "활용",
    "어디에쓸",
    "다른거",
    "딴거",
)

SEARCH_WORDS = ("레시피", "요리법", "요리")
PAIRING_WORDS = ("같이먹", "함께먹", "곁들임", "어울리는", "이랑먹", "랑먹", "먹기좋은")
PAIRING_JOSA = re.compile(r".+(?:이랑|랑|와|과|하고).+(?:먹|어울|곁들|좋은)")

#
# Template selection keywords
#
INGREDIENT_KEYWORDS = ("냉장고", "재료", "있는 것", "남은")

#
# Pairing menu (data-only)
#
# ponytail: 정적 dict — LLM 기반 pairing은 Backlog
PAIRING_MENU = {
    "김치볶음밥": ["계란국", "어묵국", "단무지", "오이무침", "군만두"],
    "파스타": ["마늘빵", "샐러드", "피클", "구운 채소"],
    "라면": ["김치", "단무지", "계란말이", "주먹밥"],
}

#
# Keyword normalization / extraction config (data-only)
#
RECIPE_KEYWORD_ALIASES = {"파": "대파"}

RECIPE_INGREDIENT_EXCLUDE_KEYWORDS = (
    "걸",
    "있는",
    "이걸",
    "이것",
    "그걸",
    "그것",
    "재료",
    "식재료",
    "보유재료",
    "냉장고",
    "내",
    "제",
    "나",
    "내식재료",
    "제식재료",
    "남은거",
)

REQUIRES_LOGIN_PERSONAL_WORDS = (
    "내식재료",
    "내재료",
    "보유식재료",
    "보유재료",
    "냉장고재료",
    "있는걸로",
    "이걸로",
)

GUIDE_MATCH_ALIASES = {"파": {"대파", "쪽파", "실파"}, "계란": {"달걀"}, "달걀": {"계란"}}
GUIDE_MISLEADING_SUFFIXES = ("소스", "가루", "분말", "즙", "청", "오일", "잼", "스톡")

KEYWORD_TOKEN_STOPWORDS = {
    "먹다남은",
    "남은",
    "먹다",
    "보관",
    "보관법",
    "보관방법",
    "세척",
    "세척법",
    "세척방법",
    "손질",
    "손질법",
    "손질방법",
    "신선도",
    "확인법",
    "알려줘",
    "식재료",
    "레시피",
    "어떡하지",
    "어떡해",
}

#
# Planner (public tools + LLM)
#
ENABLE_LLM_RECIPE_PLANNER = True

TOOL_SEARCH_RECIPES = "search_recipes"
TOOL_RECOMMEND_BY_INGREDIENT = "recommend_by_ingredient"
TOOL_RECOMMEND_FROM_FRIDGE = "recommend_from_fridge"
TOOL_SEARCH_EXTERNAL = "search_external"
TOOL_SUGGEST_PAIRING = "suggest_pairing"

WHEN_ALWAYS = "always"
WHEN_PREV_EMPTY = "prev_empty"

PUBLIC_TOOL_NAMES = frozenset({
    TOOL_SEARCH_RECIPES,
    TOOL_RECOMMEND_BY_INGREDIENT,
    TOOL_RECOMMEND_FROM_FRIDGE,
    TOOL_SEARCH_EXTERNAL,
    TOOL_SUGGEST_PAIRING,
})

TOOL_ARGS_WHITELIST: dict[str, frozenset[str]] = {
    TOOL_SEARCH_RECIPES: frozenset({"keyword"}),
    TOOL_RECOMMEND_BY_INGREDIENT: frozenset({"ingredient"}),
    TOOL_RECOMMEND_FROM_FRIDGE: frozenset(),
    TOOL_SEARCH_EXTERNAL: frozenset({"keyword", "query_text"}),
    TOOL_SUGGEST_PAIRING: frozenset({"text"}),
}

RECIPE_PLANNER_PROMPT = """너는 밥벌이 레시피 에이전트의 실행 계획(planner)이다.
사용자 요청에 맞는 도구 실행 순서를 JSON으로만 반환한다.

허용 도구 (이 이름만 사용):
- search_recipes: args keyword — 레시피/요리법 검색
- recommend_by_ingredient: args ingredient — 특정 재료로 만들 메뉴 추천
- recommend_from_fridge: args 없음 — 냉장고 재료 기반 추천 (재료명 없이 "오늘 뭐 해먹지" 등)
- search_external: args keyword, query_text — 웹 검색 (조리시간/온도 질문 또는 DB 결과 없을 때 fallback)
- suggest_pairing: args text — 곁들임/같이 먹기 좋은 메뉴

when 값:
- always: 항상 실행
- prev_empty: 직전 단계 결과가 비었을 때만 실행 (fallback)

규칙:
- 에어프라이어/몇 분/온도/조리시간 → search_external만 (always)
- 곁들임/같이 먹기 → suggest_pairing만
- "OO 레시피" 검색 → search_recipes + search_external(prev_empty)
- "OO로 뭐 해먹지" (재료 있음) → recommend_by_ingredient + search_external(prev_empty)
- 냉장고/오늘 뭐 해먹지 (특정 재료 없음) → recommend_from_fridge
- steps는 1~3개, 순차 실행만. 병렬 없음.
- max_fallback은 0 또는 1 (기본 1)

반환 형식 (JSON만, 설명 없음):
{"steps":[{"tool":"search_recipes","args":{"keyword":"김치볶음밥"},"when":"always"}],"max_fallback":1}
"""

# (utterance, intent, expected_tool_sequence, expected_when_for_last_or_none)
PLANNER_GOLDEN_CASES = (
    ("김치볶음밥 레시피", "recipe.search", (TOOL_SEARCH_RECIPES, TOOL_SEARCH_EXTERNAL), WHEN_PREV_EMPTY),
    ("에어프라이어 치킨 몇 분?", "recipe.search", (TOOL_SEARCH_EXTERNAL,), None),
    ("두부로 뭐 해먹지?", "recipe.recommend", (TOOL_RECOMMEND_BY_INGREDIENT, TOOL_SEARCH_EXTERNAL), WHEN_PREV_EMPTY),
    ("오늘 뭐 해먹지?", "recipe.recommend", (TOOL_RECOMMEND_FROM_FRIDGE,), None),
    ("냉장고 재료로 뭐 해먹지?", "recipe.recommend", (TOOL_RECOMMEND_FROM_FRIDGE,), None),
    ("김치볶음밥이랑 먹기 좋은 음식", "recipe.pairing", (TOOL_SUGGEST_PAIRING,), None),
    ("파스타와 어울리는 반찬", "recipe.pairing", (TOOL_SUGGEST_PAIRING,), None),
)

