import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.backend.services import chat_service as chat_module


def test_empty_inventory_replies_are_helpful() -> None:
    """냉장고가 비어 있으면 개인화 질문에 등록 안내를 반환합니다."""
    original_inventory_service = chat_module.inventory_service
    chat_module.inventory_service = SimpleNamespace(get_ingredients=lambda db, user_id: [])
    try:
        service = chat_module.chat_service
        expected = service.EMPTY_INVENTORY_REPLY
        assert service._reply_inventory_list(None, 1) == expected
        assert service._reply_expiring_items(None, 1, "소비 임박재료 뭐 있어?") == expected
        assert service._reply_recipe_recommend(None, 1, "오늘 뭐 해먹지?") == (expected, [])
    finally:
        chat_module.inventory_service = original_inventory_service


if __name__ == "__main__":
    test_empty_inventory_replies_are_helpful()
    print("empty inventory chat tests ok")
