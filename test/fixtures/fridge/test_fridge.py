import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

# 직접 실행해도 프로젝트 루트 기준 import가 가능하도록 경로를 맞춥니다.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.backend.services.inventory_service.inventory_service import _object_particle, inventory_service

def test_map_to_response_defaults_empty_category_to_etc() -> None:
    """마스터 카테고리가 비어 있으면 프론트 응답에서는 기타로 표시합니다."""
    item = SimpleNamespace(
        id=1,
        display_name="호박",
        quantity=1,
        unit="개",
        storage_location="냉장",
        purchased_date=date.today(),
        expiry_date=date.today(),
        created_at=None,
        receipt_item_id=None,
        is_ai_recommended=False,
    )
    ingredient = SimpleNamespace(name="호박", category=None, default_unit="개")

    response = inventory_service._map_to_response(item, ingredient)

    assert response["category"] == "기타"

def test_object_particle_matches_final_consonant() -> None:
    """식재료명 받침에 맞춰 을/를 조사를 고릅니다."""
    assert _object_particle("버터") == "를"
    assert _object_particle("김치") == "를"
    assert _object_particle("귤") == "을"
    assert _object_particle("egg") == "를"

if __name__ == "__main__":
    test_map_to_response_defaults_empty_category_to_etc()
    test_object_particle_matches_final_consonant()
    print("inventory service tests ok")


# ===== 통합: 냉장고 서비스 / 재료명 매칭 / MCP 래퍼 테스트 =====

import sys
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

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


# ===== 통합: 냉장고 서비스 / 재료명 매칭 / MCP 래퍼 테스트 =====

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from ai.tools import fridge_mcp_tools


class FakeDb:
    """롤백 호출 여부만 확인하는 테스트 DB입니다."""

    def __init__(self):
        self.rolled_back = False

    def rollback(self):
        self.rolled_back = True


def test_get_fridge_items_tool_response_shape() -> None:
    """냉장고 MCP 조회 Tool은 ok/message/data/error 형식을 반환합니다."""
    original = fridge_mcp_tools.inventory_service
    fridge_mcp_tools.inventory_service = SimpleNamespace(
        get_ingredients=lambda db, user_id: [
            {"id": 1, "name": "두부", "quantity": 1, "unit": "개", "storage_method": "냉장", "expiration_date": None, "d_day": 2, "status": "expiring"}
        ]
    )
    try:
        result = fridge_mcp_tools.get_fridge_items_tool(FakeDb(), 7)
        assert result["ok"] is True
        assert result["message"] == '냉장고 재료를 조회했어요.'
        assert result["data"]["items"][0]["name"] == "두부"
        assert result["error"] is None
    finally:
        fridge_mcp_tools.inventory_service = original


def test_write_tool_rolls_back_on_error() -> None:
    """쓰기 MCP Tool은 실패 시 공통 실패 JSON과 롤백을 수행합니다."""
    original = fridge_mcp_tools.inventory_service
    db = FakeDb()

    def fail(*args, **kwargs):
        raise RuntimeError("boom")

    fridge_mcp_tools.inventory_service = SimpleNamespace(add_ingredient=fail)
    try:
        result = fridge_mcp_tools.add_fridge_item_tool(db, 7, "두부")
        assert result["ok"] is False
        assert result["error"]["code"] == "FRIDGE_TOOL_ERROR"
        assert db.rolled_back is True
    finally:
        fridge_mcp_tools.inventory_service = original


if __name__ == "__main__":
    test_get_fridge_items_tool_response_shape()
    test_write_tool_rolls_back_on_error()
    print("fridge mcp tools tests ok")


class EmptyIngredientQuery:
    """식재료 마스터와 별칭이 모두 비어 있는 상황을 흉내냅니다."""

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return None

    def all(self):
        return []


class EmptyIngredientDb:
    """query 호출만 제공하는 냉장고 서비스 테스트용 DB 대역입니다."""

    def query(self, *args, **kwargs):
        return EmptyIngredientQuery()


def test_chat_add_rejects_unknown_ingredient_name(monkeypatch) -> None:
    """챗봇 등록은 마스터/별칭에 없는 이름을 냉장고에 추가하지 않습니다."""
    result = inventory_service.add_ingredient_by_name(EmptyIngredientDb(), 1, "일이삼사오", 3, "냉장")

    assert "올바른 식재료명을 입력해주세요" in result
