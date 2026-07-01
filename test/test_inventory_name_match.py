import sys
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.backend.services.inventory_service.inventory_service import inventory_service


def test_chat_inventory_name_match_uses_display_name() -> None:
    """챗봇 폐기/소비 매칭은 표시명과 공백 차이를 함께 보아야 합니다."""
    fridge_item = SimpleNamespace(display_name="토마토 소스", quantity=Decimal("1"), status="normal")
    ingredient = SimpleNamespace(name="토마토소스", normalized_name="토마토소스")
    items = [(fridge_item, ingredient)]

    assert inventory_service._find_item_by_name(items, "토마토 소스") is fridge_item
    assert inventory_service._find_item_by_name(items, "토마토소스") is fridge_item


if __name__ == "__main__":
    test_chat_inventory_name_match_uses_display_name()
    print("inventory name match tests ok")
