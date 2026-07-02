import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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
            {"id": 1, "name": "??", "quantity": 1, "unit": "?", "storage_method": "??", "expiration_date": None, "d_day": 2, "status": "expiring"}
        ]
    )
    try:
        result = fridge_mcp_tools.get_fridge_items_tool(FakeDb(), 7)
        assert result["ok"] is True
        assert result["message"] == '냉장고 재료를 조회했어요.'
        assert result["data"]["items"][0]["name"] == "??"
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
        result = fridge_mcp_tools.add_fridge_item_tool(db, 7, "??")
        assert result["ok"] is False
        assert result["error"]["code"] == "FRIDGE_TOOL_ERROR"
        assert db.rolled_back is True
    finally:
        fridge_mcp_tools.inventory_service = original


if __name__ == "__main__":
    test_get_fridge_items_tool_response_shape()
    test_write_tool_rolls_back_on_error()
    print("fridge mcp tools tests ok")
