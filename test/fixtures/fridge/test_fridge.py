import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

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


def test_chat_consume_uses_multiple_matching_inventory_rows() -> None:
    """같은 재료가 여러 건이면 소비기한이 가까운 항목부터 요청 수량만큼 차감합니다."""
    first = SimpleNamespace(display_name="두부", quantity=Decimal("2"), status="normal", expiry_date=date(2026, 7, 16))
    second = SimpleNamespace(display_name="두부", quantity=Decimal("2"), status="normal", expiry_date=date(2026, 7, 20))
    ingredient = SimpleNamespace(name="두부", normalized_name="두부")
    db = MagicMock()
    db.query.return_value.join.return_value.filter.return_value.all.return_value = [
        (first, ingredient),
        (second, ingredient),
    ]

    reply = inventory_service.consume_ingredient_by_name(db, 1, "두부", 3)

    assert first.status == "used"
    assert second.quantity == Decimal("1")
    assert "3개 소비 처리했어요" in reply
    assert "남은 총수량: 1" in reply
    db.commit.assert_called_once()

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

def test_destructive_name_match_rejects_partial_name() -> None:
    """소비·폐기 작업은 짧은 부분 일치로 다른 식재료를 선택하지 않습니다."""
    fridge_item = SimpleNamespace(display_name="계란", quantity=Decimal("1"), status="normal")
    ingredient = SimpleNamespace(name="계란", normalized_name="계란")

    assert inventory_service._find_items_by_name([(fridge_item, ingredient)], "계") == []


def test_multi_add_uses_single_transaction(monkeypatch) -> None:
    """여러 재료 추가는 모두 준비된 뒤 한 번만 커밋합니다."""
    from ai.agents.inventory_agent.inventory_agent import execute_inventory_action

    calls = []
    db = MagicMock()

    def fake_add(db, user_id, name, quantity, storage, *, commit):
        """각 재료가 자동 커밋 없이 호출되는지 기록합니다."""
        calls.append((name, commit))
        return f"{name} 추가"

    monkeypatch.setattr(inventory_service, "add_ingredient_by_name", fake_add)

    result = execute_inventory_action(
        "add_ingredients",
        ["확인", "add_ingredients", "양파,1,냉장|감자,2,실온"],
        db,
        1,
    )

    assert calls == [("양파", False), ("감자", False)]
    db.commit.assert_called_once()
    db.rollback.assert_not_called()
    assert "양파 추가" in result["response_text"]


def test_multi_add_rolls_back_when_one_item_fails(monkeypatch) -> None:
    """여러 재료 중 하나라도 실패하면 전체 작업을 롤백합니다."""
    from ai.agents.inventory_agent.inventory_agent import execute_inventory_action

    db = MagicMock()

    def fake_add(db, user_id, name, quantity, storage, *, commit):
        """두 번째 재료에서 저장 실패를 재현합니다."""
        if name == "감자":
            raise RuntimeError("저장 실패")
        return f"{name} 추가"

    monkeypatch.setattr(inventory_service, "add_ingredient_by_name", fake_add)

    result = execute_inventory_action(
        "add_ingredients",
        ["확인", "add_ingredients", "양파,1,냉장|감자,2,실온"],
        db,
        1,
    )

    db.commit.assert_not_called()
    db.rollback.assert_called_once()
    assert "문제가 생겼어요" in result["response_text"]


def test_inventory_action_rejects_unsafe_quantity(monkeypatch) -> None:
    """직접 조작된 확인 명령의 무한대·음수 수량을 저장 전에 차단합니다."""
    from ai.agents.inventory_agent.inventory_agent import execute_inventory_action

    add_mock = MagicMock()
    monkeypatch.setattr(inventory_service, "add_ingredient_by_name", add_mock)

    for quantity in ("-1", "nan", "inf"):
        result = execute_inventory_action(
            "add_ingredient",
            ["확인", "add_ingredient", "양파", quantity, "냉장"],
            MagicMock(),
            1,
        )
        assert "올바른" in result["response_text"]

    add_mock.assert_not_called()
