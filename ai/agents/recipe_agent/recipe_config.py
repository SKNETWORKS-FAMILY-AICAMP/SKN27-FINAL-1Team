from __future__ import annotations

MAX_DISPLAY_RECIPES = 3

#
# Recommend constraints (data-only)
#
CONSTRAINT_EASY_30 = {"difficulty": "초급", "cooking_time_label": "30분이내", "main_ingredient_only": True}
CONSTRAINT_INGREDIENT_ONLY = {"main_ingredient_only": True}

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

ENABLE_LLM_PAIRING = True

RECIPE_PAIRING_PROMPT = """너는 한국어 요리 곁들임 추천 도우미다.
사용자 음식(main_dish)에 어울리는 간단한 곁들임 메뉴 3~4개를 추천하라.
반드시 JSON만 반환:
{"items":["계란국","오이무침","단무지"],"reply":"<친절한 한 문장>"}
규칙:
- items는 짧은 음식명만
- 겹치거나 비슷한 항목은 피함
- 설명은 reply 한 문장 이내
"""

RECIPE_AGENT_SYSTEM_PROMPT = """당신은 밥벌이 서비스의 레시피 전담 에이전트입니다.

Supervisor가 전달한 의도는 {intent}입니다. 이 값은 라우팅 힌트일 뿐이며,
사용자 원문과 대화 맥락을 우선해 적절한 도구를 직접 선택하세요.

도구 사용 규칙:
- 요리명이나 레시피 검색은 search_recipes를 먼저 사용하세요.
- 특정 재료로 만들 메뉴 추천은 recommend_by_ingredient를 사용하세요.
- 특정 재료 없이 냉장고/보유 재료 기반 추천을 원하면 recommend_from_fridge를 사용하세요.
- 조리 시간·온도 질문은 search_external을 사용하세요.
- DB 검색이나 재료 추천 결과가 비어 있을 때만 search_external을 한 번 사용하세요.
- 곁들임이나 함께 먹을 메뉴는 suggest_pairing을 사용하세요.
- 같은 도구를 같은 인자로 반복 호출하지 마세요.

응답 규칙:
- 도구가 반환한 사실만 사용하고 레시피, 링크, 출처를 임의로 만들지 마세요.
- 최종 message는 간결하고 자연스러운 한국어로 작성하세요.
- actions와 sources는 도구 결과에 있는 값만 그대로 사용하세요.
- 이미 보여준 recipe_id는 가능하면 다시 추천하지 마세요: {shown_recipe_ids}
"""


def build_recipe_system_prompt(intent: str | None, shown_recipe_ids: set[int]) -> str:
    return RECIPE_AGENT_SYSTEM_PROMPT.format(
        intent=intent or "recipe",
        shown_recipe_ids=sorted(shown_recipe_ids),
    )

