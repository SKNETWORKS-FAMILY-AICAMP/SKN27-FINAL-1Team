import sys
from pathlib import Path

# 직접 실행해도 프로젝트 루트 기준 import가 가능하도록 경로를 맞춥니다.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.backend.services.chat_service import chat_service


def test_route_intent_examples() -> None:
    """챗봇 대표 문장이 기대 intent로 분류되는지 확인합니다."""
    cases = {
        "오늘 먼저 먹어야 할 거 뭐야?": "inventory.expiring",
        "재료 기한 다되어 가는거 있어?": "inventory.expiring",
        "김치 유통기한 언제까지야": "inventory.expiring",
        "내 냉장고 재료 뭐 있어?": "inventory.list",
        "영수증 등록 어디서 해?": "receipt.guide",
        "파 어떻게 보관해?": "ingredient.guide",
        "파 보관법": "ingredient.guide",
        "아보카도 보관법": "ingredient.guide",
        "남은 피자 보관법": "ingredient.guide",
        "계란 보관 어떻게 해": "ingredient.guide",
        "먹다 남은 햄버거 어떡하지?": "ingredient.guide",
        "두부로 뭐 만들수있어?": "recipe.recommend",
        "두부로 뭘 만들지?": "recipe.recommend",
        "이걸로 만들수 있는 메뉴 뭐야": "recipe.recommend",
        "파 빨리 써야 하는데 뭐하지": "recipe.recommend",
        "감자로 간단하게 만들수 있는거 알려줘": "recipe.recommend",
        "먹다남은 감자튀김 어디에 쓸수있을까": "recipe.recommend",
        "바베큐 레시피 알려줘": "recipe.search",
        "김치볶음밥 레시피": "recipe.search",
        "감자튀김 에어프라이기 시간": "recipe.search",
    }

    for message, expected in cases.items():
        assert chat_service._route_intent(message) == expected


def test_extract_recipe_ingredient() -> None:
    """특정 재료 레시피 질문에서 재료명만 추출되는지 확인합니다."""
    assert chat_service._extract_recipe_ingredient("두부로 뭐 만들수있어?") == "두부"
    assert chat_service._extract_recipe_ingredient("두부로 뭘 만들지?") == "두부"
    assert chat_service._extract_recipe_ingredient("이걸로 만들수 있는 메뉴 뭐야") == ""
    assert chat_service._extract_recipe_ingredient("냉장고에 있는 걸로 저녁 추천") == ""
    assert chat_service._extract_recipe_ingredient("파 빨리 써야 하는데 뭐하지") == "대파"
    assert chat_service._extract_recipe_ingredient("먹다남은 감자튀김 어디에 쓸수있을까") == "감자튀김"
    assert chat_service._extract_keyword("먹다 남은 햄버거 어떡하지?") == "햄버거"
    assert chat_service._extract_keyword("아보카도 보관법") == "아보카도"
    assert chat_service._extract_keyword("남은 피자 보관법") == "피자"


def test_login_status_question() -> None:
    """로그인 상태를 묻는 문장을 별도로 인식합니다."""
    assert chat_service._is_login_status_question("지금 로그인 되어 있어?")
    assert chat_service._is_login_status_question("나 로그인 상태야?")
    assert not chat_service._is_login_status_question("로그인하려면 어디로 가?")

def test_guest_chat_login_boundary() -> None:
    """비회원은 개인 냉장고 기능만 막고 일반 레시피/보관법은 허용합니다."""
    assert chat_service._requires_login("inventory.list", "내 냉장고 재료 뭐 있어?")
    assert chat_service._requires_login("inventory.expiring", "소비기한 임박 재료 알려줘")
    assert chat_service._requires_login("recipe.recommend", "냉장고 재료로 뭐 먹을까?")
    assert chat_service._requires_login("recipe.recommend", "내 식재료로 레시피 추천해줘")
    assert chat_service._extract_recipe_ingredient("내 식재료로 레시피 추천해줘") == ""
    assert not chat_service._requires_login("recipe.recommend", "두부로 뭐 만들 수 있어?")
    assert not chat_service._requires_login("recipe.search", "깐풍기 레시피")
    assert not chat_service._requires_login("ingredient.guide", "양파 보관법")

def test_guide_result_match() -> None:
    """가이드 검색이 비슷한 이름의 다른 재료를 답하지 않는지 확인합니다."""
    assert not chat_service._is_guide_result_match("피자", "피자소스")
    assert not chat_service._is_guide_result_match("김", "김치")
    assert chat_service._is_guide_result_match("파", "대파")
    assert chat_service._is_guide_result_match("마늘", "깐마늘")


def test_search_result_relevance() -> None:
    """웹 검색 fallback이 질문 핵심어와 무관한 결과를 거르는지 확인합니다."""
    good = {"title": "남은 치킨 보관법", "content": "치킨은 밀폐 후 냉장 보관", "url": "https://example.com"}
    bad = {"title": "마늘 양파 보관법", "content": "마늘과 양파는 상온 보관", "url": "https://example.com"}
    pizza_sauce = {"title": "피자소스 보관법", "content": "피자소스는 개봉 후 냉장 보관", "url": "https://example.com"}

    assert chat_service._is_relevant_search_result("먹다남은 치킨", good)
    assert not chat_service._is_relevant_search_result("먹다남은 치킨", bad)
    assert not chat_service._is_relevant_search_result("피자", pizza_sauce)
    assert not chat_service._is_relevant_search_result("보관법", good)


if __name__ == "__main__":
    test_route_intent_examples()
    test_extract_recipe_ingredient()
    test_guide_result_match()
    test_search_result_relevance()
    print("chat service tests ok")