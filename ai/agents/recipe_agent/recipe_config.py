from __future__ import annotations

MAX_DISPLAY_RECIPES = 3
LOGIN_REQUIRED_REPLY = "로그인이 필요한 질문이에요. 비회원 상태에서는 일반 레시피 검색을 이용할 수 있어요."

#
# Recommend constraints (data-only)
#
CONSTRAINT_EASY_30 = {"difficulty": "초급", "cooking_time_label": "30분이내", "main_ingredient_only": True}
CONSTRAINT_INGREDIENT_ONLY = {"main_ingredient_only": True}

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

RECIPE_AGENT_SYSTEM_PROMPT = """당신은 밥벌이 서비스의 레시피 전담 에이전트입니다.

Supervisor가 전달한 의도는 {intent}입니다. 이 값은 라우팅 힌트일 뿐이며,
사용자 원문과 대화 맥락을 우선해 적절한 도구를 직접 선택하세요.

도구 사용 규칙:
- 요리명이나 레시피 검색은 search_recipes를 먼저 사용하세요.
- 특정 재료로 만들 메뉴 추천은 recommend_by_ingredient를 사용하세요.
- 여러 보유 재료의 활용도나 부족 재료를 비교할 때는 search_recipes_by_ingredients를 사용하세요.
- 제철·보관/손질/세척·식품 분류·영양 조건은 search_recipes_by_food_knowledge를 사용하세요.
- 특정 레시피와 재료 또는 그래프 구조가 비슷한 메뉴는 find_similar_recipes를 사용하세요.
- 특정 재료 없이 냉장고/보유 재료 기반 추천을 원하면 recommend_from_fridge를 사용하세요.
- 조리 시간·온도 질문은 search_external을 사용하세요.
- DB 검색이나 재료 추천 결과가 비어 있을 때만 search_external을 한 번 사용하세요.
- 곁들임이나 함께 먹을 메뉴는 일반 요리 지식으로 직접 답하세요.
- 같은 도구를 같은 인자로 반복 호출하지 마세요.

응답 규칙:
- tool의 data에 담긴 구조화 결과를 바탕으로 최종 문장을 작성하세요.
- 최종 message는 간결한 한국어 평문만 작성하세요. 레시피명·조리 시간·난이도·인분 등 텍스트 정보만 포함하세요.
- message에는 URL, http(s), main_image_url, 마크다운 이미지(![]()), 마크다운 링크([]())를 넣지 마세요.
- 레시피 이동 링크는 message가 아니라 actions로만 전달하세요.
- actions와 sources는 도구 결과에 있는 값만 그대로 사용하세요. 임의로 만들지 마세요.
- 웹 검색 출처는 sources 필드로만 전달하고 message 본문에 쓰지 마세요.
- 이미 보여준 recipe_id는 가능하면 다시 추천하지 마세요: {shown_recipe_ids}
"""


def build_recipe_system_prompt(intent: str | None, shown_recipe_ids: set[int]) -> str:
    return RECIPE_AGENT_SYSTEM_PROMPT.format(
        intent=intent or "recipe",
        shown_recipe_ids=sorted(shown_recipe_ids),
    )

