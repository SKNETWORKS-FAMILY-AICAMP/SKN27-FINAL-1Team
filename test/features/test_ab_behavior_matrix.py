from datetime import date

import pytest

from ai.agents.alarm_agent.alarm_agent import analyze_intent
from app.backend.api.calendar.calendar_api import _event_key_belongs_to_user
from app.backend.services.calendar_mcp_client import _serverless_output
from app.backend.services.receipt_ocr_service.receipt_ocr_service import ReceiptOcrService
from app.backend.services.recommendation_service.fridge_ingredient_match import (
    FridgeItemSnapshot,
    classify_fridge_match,
)
from app.backend.services.recommendation_service.recommend_config import RecipeRecommendConfig


@pytest.mark.parametrize(
    "prefix",
    ["ingredient-expiry", "today-menu", "recipe-delete", "receipt-cost", "calendar-agent"],
)
def test_calendar_feature_ab_same_prefix_current_user_vs_other_user(prefix):
    assert _event_key_belongs_to_user(f"{prefix}-7-2026-07-07", 7)
    assert not _event_key_belongs_to_user(f"{prefix}-8-2026-07-07", 7)


@pytest.mark.parametrize(
    ("ready_payload", "not_ready_payload"),
    [
        ({"status": "COMPLETED", "output": {"event_id": "ok"}}, {"status": "IN_QUEUE", "output": {"event_id": "ok"}}),
        ({"status": "COMPLETED", "output": {"deleted": True}}, {"status": "FAILED", "output": {"deleted": True}}),
        ({"status": "COMPLETED", "output": {"missing": True}}, {"status": "CANCELLED", "output": {"missing": True}}),
    ],
)
def test_calendar_mcp_feature_ab_completed_status_returns_output_only_when_ready(ready_payload, not_ready_payload):
    assert _serverless_output(ready_payload) is not None
    assert _serverless_output(not_ready_payload) is None


@pytest.mark.parametrize(
    ("specific_text", "ambiguous_text", "reminder_type"),
    [
        ("내일 두부 먹으라고 알림 등록해줘", "내일 두부 알림 등록해줘", "consume_reminder"),
        ("내일 두부 사야한다고 알림 등록해줘", "내일 두부 알림 등록해줘", "shopping_reminder"),
        ("내일 병원 일정 등록해줘", "내일 병원 알림 등록해줘", "calendar_event"),
    ],
)
def test_alarm_agent_feature_ab_specific_reminder_vs_ambiguous_alarm(specific_text, ambiguous_text, reminder_type):
    specific = analyze_intent(specific_text)
    ambiguous = analyze_intent(ambiguous_text)

    assert specific["intent"] == "calendar.create"
    assert specific["payload"]["reminder_type"] == reminder_type
    assert ambiguous["intent"] == "alarm.clarify"


@pytest.mark.parametrize(
    ("receipt_like", "not_receipt_like"),
    [
        ({"items": [{"raw_name": "tofu"}]}, {"confidence_note": "not a receipt"}),
        ({"store_name": "market"}, {}),
        ({"total_amount": 1000}, {"total_amount": 0}),
        ({"confidence_note": "영수증 결제 승인"}, {"confidence_note": "not a purchase receipt"}),
    ],
)
def test_receipt_ocr_feature_ab_receipt_evidence_present_vs_absent(receipt_like, not_receipt_like):
    service = ReceiptOcrService()

    assert service._has_receipt_evidence(receipt_like) is True
    assert service._has_receipt_evidence(not_receipt_like) is False


@pytest.mark.parametrize(
    ("good", "bad"),
    [
        ({"document_type": "receipt", "is_receipt_like": True, "items": [{"raw_name": "tofu"}]}, {"document_type": "non_receipt", "is_receipt_like": False}),
        ({"document_type": "receipt", "is_receipt_like": True, "store_name": "market"}, {"document_type": "receipt", "is_receipt_like": True}),
    ],
)
def test_receipt_ocr_feature_ab_valid_receipt_vs_rejected_document(good, bad):
    service = ReceiptOcrService()

    assert service._validate_receipt_document(good) == []
    assert service._validate_receipt_document(bad)


@pytest.mark.parametrize(
    ("fridge_items", "expected_owned", "expected_maybe", "expected_missing"),
    [
        ([FridgeItemSnapshot(1, "egg")], 1, 0, 1),
        ([FridgeItemSnapshot(None, "green onion chopped")], 0, 1, 1),
        ([FridgeItemSnapshot(None, "milk")], 0, 0, 2),
    ],
)
def test_recipe_matching_feature_ab_owned_partial_missing_paths(fridge_items, expected_owned, expected_maybe, expected_missing):
    result = classify_fridge_match(
        [{"name": "egg", "ingredient_id": 1}, {"name": "green onion", "ingredient_id": 2}],
        fridge_items,
    )

    assert len(result.owned) == expected_owned
    assert len(result.maybe_owned) == expected_maybe
    assert len(result.missing) == expected_missing


@pytest.mark.parametrize(
    ("small", "large"),
    [
        (RecipeRecommendConfig.menu_custom_preset(1, pool_multiplier=1), RecipeRecommendConfig.menu_custom_preset(50, pool_multiplier=10)),
        (RecipeRecommendConfig.for_mode("menu_custom", request_limit=5), RecipeRecommendConfig.for_mode("fridge_consume", request_limit=5)),
    ],
)
def test_recipe_recommend_feature_ab_small_custom_pool_vs_larger_pool(small, large):
    assert small.pool_size < large.pool_size
