from datetime import date, timedelta
from types import SimpleNamespace

import pytest

pytest.importorskip("langchain_openai")

from ai.tools.fridge_mcp_tools import FRIDGE_MCP_TOOLS
from ai.agents.supervisor_agent import supervisor_agent
from app.backend.services.calendar_mcp_client import _serverless_output
from app.backend.services.inventory_service.inventory_service import inventory_service
from app.backend.services.receipt_ocr_service.receipt_ocr_service import ReceiptOcrService


def test_overall_feature_smoke_contracts():
    # 챗봇 슈퍼바이저 라우팅
    assert supervisor_agent.route_intent({"intent": "recipe.recommend"}) == "recipe_agent_node"
    assert supervisor_agent.route_intent({"intent": "alarm.calendar"}) == "alarm_agent_node"

    # 냉장고 MCP 도구 표면
    assert {"get_fridge_items", "add_fridge_item", "consume_fridge_item", "delete_fridge_item"}.issubset(
        FRIDGE_MCP_TOOLS
    )

    # Calendar serverless result contract
    assert _serverless_output({"status": "COMPLETED", "output": {"event_id": "calendar-event"}}) == {
        "event_id": "calendar-event"
    }

    # Inventory response mapping
    assert inventory_service._map_to_response(
        SimpleNamespace(
            id=1,
            receipt_item_id=None,
            display_name="tofu",
            quantity=1,
            unit="ea",
            storage_location="fridge",
            purchased_date=date.today(),
            expiry_date=date.today() + timedelta(days=1),
            created_at=None,
        ),
        SimpleNamespace(name="tofu", category=None, default_unit="ea"),
    )["is_expiring_soon"] is True

    # Receipt OCR validation surface
    assert ReceiptOcrService()._validate_receipt_document(
        {"document_type": "receipt", "is_receipt_like": True, "store_name": "market"}
    ) == []
