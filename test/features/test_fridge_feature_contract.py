from types import SimpleNamespace

from ai.tools import fridge_mcp_tools


def test_fridge_feature_tool_returns_common_success_shape(monkeypatch):
    monkeypatch.setattr(
        fridge_mcp_tools,
        "inventory_service",
        SimpleNamespace(
            get_ingredients=lambda db, user_id: [
                {
                    "id": 1,
                    "name": "두부",
                    "quantity": 1,
                    "unit": "개",
                    "storage_method": "냉장",
                    "expiration_date": None,
                    "d_day": 3,
                    "status": "normal",
                }
            ]
        ),
    )

    result = fridge_mcp_tools.get_fridge_items_tool(None, 7)

    assert result["ok"] is True
    assert result["error"] is None
    assert result["data"]["items"][0]["name"] == "두부"


def test_fridge_feature_ab_filters_expiring_items(monkeypatch):
    monkeypatch.setattr(
        fridge_mcp_tools,
        "inventory_service",
        SimpleNamespace(
            get_ingredients=lambda db, user_id: [
                {"id": 1, "name": "milk", "d_day": 2},
                {"id": 2, "name": "rice", "d_day": 10},
            ]
        ),
    )

    result = fridge_mcp_tools.get_expiring_items_tool(None, 7, days=3)

    assert [item["name"] for item in result["data"]["items"]] == ["milk"]
