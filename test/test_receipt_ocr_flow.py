import os
import sys
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.backend.db.base import Base
from app.backend.db.models import FridgeItem, Ingredient, Receipt, ReceiptItem, User
from app.backend.schemas.receipts import ReceiptConfirmRequest
from app.backend.services.ingredient_match_service import ingredient_name_matcher
from app.backend.services.receipt_ocr_service.receipt_confirm_service import receipt_confirm_service
from app.backend.services.receipt_ocr_service.receipt_ocr_service import ReceiptOcrService


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


def seed_user_and_receipt(db_session):
    user = User(email="receipt-test@example.com", nickname="receipt tester")
    db_session.add(user)
    db_session.flush()

    receipt = Receipt(user_id=user.id, original_file_name="receipt.jpg")
    db_session.add(receipt)
    db_session.flush()
    return user, receipt


def seed_ingredient(db_session, name: str, *, normalized_name: str | None = None, default_unit: str = "개"):
    ingredient = Ingredient(
        name=name,
        normalized_name=normalized_name or name.replace(" ", "").lower(),
        default_unit=default_unit,
    )
    db_session.add(ingredient)
    db_session.flush()
    return ingredient


def test_ingredient_matcher_strips_parentheses_and_returns_standard_name(db_session):
    banana = seed_ingredient(db_session, "바나나")

    matched = ingredient_name_matcher.find_best_ingredient(db_session, "바나나(수입산)")

    assert matched is not None
    assert matched.id == banana.id
    assert matched.name == "바나나"


def test_ingredient_matcher_returns_none_when_no_standard_name_matches(db_session):
    seed_ingredient(db_session, "바나나")

    matched = ingredient_name_matcher.find_best_ingredient(db_session, "처음보는상품ABC")

    assert matched is None


def test_ocr_normalize_result_uses_standard_name_or_raw_name_fallback(db_session):
    seed_ingredient(db_session, "바나나")
    service = ReceiptOcrService()

    normalized = service._normalize_ocr_result(
        {
            "items": [
                {"raw_name": "바나나(수입산)", "quantity": 1, "unit": "개", "item_amount": 2000},
                {"raw_name": "처음보는상품ABC", "quantity": 2, "unit": "개", "item_amount": 3000},
            ]
        },
        image_id="receipt-test",
        db=db_session,
    )

    assert normalized["items"][0]["raw_name"] == "바나나(수입산)"
    assert normalized["items"][0]["normalized_name"] == "바나나"
    assert normalized["items"][1]["raw_name"] == "처음보는상품ABC"
    assert normalized["items"][1]["normalized_name"] == "처음보는상품ABC"


def test_confirm_receipt_saves_standard_name_to_receipt_and_fridge_items(db_session):
    user, receipt = seed_user_and_receipt(db_session)
    banana = seed_ingredient(db_session, "바나나")
    request_data = ReceiptConfirmRequest(
        receipt_id=receipt.id,
        store_name="테스트마트",
        purchase_datetime=None,
        total_amount=2000,
        calendar_cost_enabled=False,
        items=[
            {
                "raw_name": "바나나(수입산)",
                "normalized_name": "바나나(수입산)",
                "quantity": 1,
                "unit": "개",
                "item_amount": 2000,
                "storage_method": "냉장",
                "item_memo": None,
            }
        ],
    )

    with patch(
        "app.backend.services.receipt_ocr_service.receipt_confirm_service.inventory_service._get_or_create_storage_rule",
        return_value=("냉장", 7),
    ):
        saved_count = receipt_confirm_service.save_confirmed_items(
            db=db_session,
            user_id=user.id,
            request_data=request_data,
        )

    receipt_item = db_session.query(ReceiptItem).one()
    fridge_item = db_session.query(FridgeItem).one()

    assert saved_count == 1
    assert receipt_item.raw_name == "바나나(수입산)"
    assert receipt_item.normalized_name == "바나나"
    assert receipt_item.ingredient_id == banana.id
    assert fridge_item.receipt_item_id == receipt_item.id
    assert fridge_item.display_name == "바나나"
    assert fridge_item.ingredient_id == banana.id


def test_confirm_receipt_keeps_raw_name_when_no_standard_name_matches(db_session):
    user, receipt = seed_user_and_receipt(db_session)
    request_data = ReceiptConfirmRequest(
        receipt_id=receipt.id,
        store_name="테스트마트",
        purchase_datetime=None,
        total_amount=3000,
        calendar_cost_enabled=False,
        items=[
            {
                "raw_name": "처음보는상품ABC",
                "normalized_name": "처음보는상품ABC",
                "quantity": 1,
                "unit": "개",
                "item_amount": 3000,
                "storage_method": "냉장",
                "item_memo": None,
            }
        ],
    )

    with patch(
        "app.backend.services.receipt_ocr_service.receipt_confirm_service.inventory_service._get_or_create_storage_rule",
        return_value=("냉장", 7),
    ):
        receipt_confirm_service.save_confirmed_items(
            db=db_session,
            user_id=user.id,
            request_data=request_data,
        )

    receipt_item = db_session.query(ReceiptItem).one()
    fridge_item = db_session.query(FridgeItem).one()
    created_ingredient = db_session.query(Ingredient).one()

    assert receipt_item.raw_name == "처음보는상품ABC"
    assert receipt_item.normalized_name == "처음보는상품ABC"
    assert fridge_item.display_name == "처음보는상품ABC"
    assert created_ingredient.name == "처음보는상품ABC"
