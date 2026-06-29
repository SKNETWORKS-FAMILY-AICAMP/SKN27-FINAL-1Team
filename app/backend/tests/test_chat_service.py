import sys
from pathlib import Path

# 직접 실행해도 프로젝트 루트 기준 import가 가능하도록 경로를 맞춥니다.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.services.chat_service import chat_service


def test_route_intent_examples() -> None:
    """챗봇 대표 문장이 기대 intent로 분류되는지 확인합니다."""
    cases = {
        "오늘 먼저 먹어야 할 거 뭐야?": "inventory.expiring",
        "재료 기한 다되어 가는거 있어?": "inventory.expiring",
        "김치 유통기한 언제까지야": "inventory.expiring",
        "파 어떻게 보관해?": "ingredient.guide",
        "파 보관법": "ingredient.guide",
        "두부로 뭐 만들수있어?": "recipe.recommend",
        "이걸로 만들수 있는 메뉴 뭐야": "recipe.recommend",
        "파 빨리 써야 하는데 뭐하지": "recipe.recommend",
    }

    for message, expected in cases.items():
        assert chat_service._route_intent(message) == expected


def test_extract_recipe_ingredient() -> None:
    """특정 재료 레시피 질문에서 재료명만 추출되는지 확인합니다."""
    assert chat_service._extract_recipe_ingredient("두부로 뭐 만들수있어?") == "두부"
    assert chat_service._extract_recipe_ingredient("이걸로 만들수 있는 메뉴 뭐야") == ""
    assert chat_service._extract_recipe_ingredient("냉장고에 있는 걸로 저녁 추천") == ""
    assert chat_service._extract_recipe_ingredient("파 빨리 써야 하는데 뭐하지") == "대파"


if __name__ == "__main__":
    test_route_intent_examples()
    test_extract_recipe_ingredient()
    print("chat service tests ok")