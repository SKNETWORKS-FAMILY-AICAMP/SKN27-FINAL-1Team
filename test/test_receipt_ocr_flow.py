import asyncio
import io
import os
import sys
from unittest.mock import patch

import pytest
from fastapi import UploadFile
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.backend.db.base import Base
from app.backend.db.models import (
    FridgeItem,
    Ingredient,
    IngredientAlias,
    IngredientStorageStandard,
    Receipt,
    ReceiptItem,
    User,
)
from app.backend.schemas.receipts import ReceiptConfirmRequest
from app.backend.core.config import settings
from app.backend.services.ingredient_match_service import ingredient_name_matcher
from app.backend.services.receipt_ocr_service.receipt_confirm_service import receipt_confirm_service
from app.backend.services.receipt_ocr_service.receipt_ocr_service import ReceiptOcrService


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(type_, compiler, **kw):
    return "INTEGER"


EA = "\uac1c"
BANANA = "\ubc14\ub098\ub098"
BANANA_IMPORTED = "\ubc14\ub098\ub098(\uc218\uc785\uc0b0)"
UNKNOWN_PRODUCT = "\ucc98\uc74c\ubcf4\ub294\uc0c1\ud488ABC"
COLD_STORAGE = "\ub0c9\uc7a5"
STORE_NAME = "\ud14c\uc2a4\ud2b8\ub9c8\ud2b8"


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    receipt_tables = [
        User.__table__,
        Ingredient.__table__,
        IngredientAlias.__table__,
        IngredientStorageStandard.__table__,
        Receipt.__table__,
        ReceiptItem.__table__,
        FridgeItem.__table__,
    ]
    Base.metadata.create_all(bind=engine, tables=receipt_tables)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine, tables=receipt_tables)


def seed_user_and_receipt(db_session):
    user = User(email="receipt-test@example.com", nickname="receipt tester")
    db_session.add(user)
    db_session.flush()

    receipt = Receipt(user_id=user.id, original_file_name="receipt.jpg")
    db_session.add(receipt)
    db_session.flush()
    return user, receipt


def seed_ingredient(db_session, name: str, *, normalized_name: str | None = None, default_unit: str = EA):
    ingredient = Ingredient(
        name=name,
        normalized_name=normalized_name or name.replace(" ", "").lower(),
        default_unit=default_unit,
    )
    db_session.add(ingredient)
    db_session.flush()
    return ingredient


def test_ingredient_matcher_strips_parentheses_and_returns_neo4j_standard_name(monkeypatch):
    monkeypatch.setattr(
        ingredient_name_matcher,
        "_load_neo4j_candidates",
        lambda: [(ingredient_name_matcher._match_key(BANANA), BANANA)],
    )

    matched = ingredient_name_matcher.find_best_name(BANANA_IMPORTED)

    assert matched == BANANA


def test_ingredient_matcher_returns_none_when_no_neo4j_standard_name_matches(monkeypatch):
    monkeypatch.setattr(
        ingredient_name_matcher,
        "_load_neo4j_candidates",
        lambda: [(ingredient_name_matcher._match_key(BANANA), BANANA)],
    )

    matched = ingredient_name_matcher.find_best_name(UNKNOWN_PRODUCT)

    assert matched is None


def test_ocr_normalize_result_uses_neo4j_standard_name_or_raw_name_fallback(db_session, monkeypatch):
    monkeypatch.setattr(
        ingredient_name_matcher,
        "_load_neo4j_candidates",
        lambda: [(ingredient_name_matcher._match_key(BANANA), BANANA)],
    )
    service = ReceiptOcrService()

    normalized = service._normalize_ocr_result(
        {
            "items": [
                {"raw_name": BANANA_IMPORTED, "quantity": 1, "unit": EA, "item_amount": 2000},
                {"raw_name": UNKNOWN_PRODUCT, "quantity": 2, "unit": EA, "item_amount": 3000},
            ]
        },
        image_id="receipt-test",
        db=db_session,
    )

    assert normalized["items"][0]["raw_name"] == BANANA_IMPORTED
    assert normalized["items"][0]["normalized_name"] == BANANA
    assert normalized["items"][1]["raw_name"] == UNKNOWN_PRODUCT
    assert normalized["items"][1]["normalized_name"] == UNKNOWN_PRODUCT


def test_analyze_upload_retries_low_quality_ocr_result(db_session, monkeypatch, tmp_path):
    user = User(email="receipt-graph@example.com", nickname="receipt graph tester")
    db_session.add(user)
    db_session.flush()

    monkeypatch.setattr(settings, "OCR_UPLOAD_DIR", str(tmp_path / "raw"))
    monkeypatch.setattr(
        ingredient_name_matcher,
        "_load_neo4j_candidates",
        lambda: [(ingredient_name_matcher._match_key(BANANA), BANANA)],
    )

    service = ReceiptOcrService()
    calls = []

    def fake_call_openai_vision(*, image_bytes, filename, image_id, retry_note=None):
        calls.append(retry_note)
        if len(calls) == 1:
            return {
                "image_id": image_id,
                "store_name": None,
                "purchase_datetime": None,
                "items": [{"raw_name": "???", "quantity": None, "unit": None, "item_amount": None}],
                "total_item_count": None,
                "total_amount": None,
                "currency": "KRW",
                "confidence_note": "Unreadable first pass",
            }
        return {
            "image_id": image_id,
            "store_name": STORE_NAME,
            "purchase_datetime": "2026-06-29 12:30:00",
            "items": [{"raw_name": BANANA_IMPORTED, "quantity": 1, "unit": EA, "item_amount": 2000}],
            "total_item_count": 1,
            "total_amount": 2000,
            "currency": "KRW",
            "confidence_note": None,
        }

    monkeypatch.setattr(service, "_call_openai_vision", fake_call_openai_vision)

    upload = UploadFile(filename="receipt.png", file=io.BytesIO(b"fake-image-bytes"))
    result = asyncio.run(service.analyze_upload(db=db_session, file=upload, user_id=user.id))

    assert len(calls) == 2
    assert calls[0] is None
    assert "item_names_unclear" in calls[1]
    assert "many_item_amounts_missing" in calls[1]
    assert result["items"][0]["raw_name"] == BANANA_IMPORTED
    assert result["items"][0]["normalized_name"] == BANANA
    assert result["receipt_id"] is not None


def test_analyze_upload_does_not_retry_when_only_total_amount_is_visible(db_session, monkeypatch, tmp_path):
    user = User(email="receipt-total-only@example.com", nickname="receipt total tester")
    db_session.add(user)
    db_session.flush()

    monkeypatch.setattr(settings, "OCR_UPLOAD_DIR", str(tmp_path / "raw"))
    monkeypatch.setattr(
        ingredient_name_matcher,
        "_load_neo4j_candidates",
        lambda: [(ingredient_name_matcher._match_key(BANANA), BANANA)],
    )

    service = ReceiptOcrService()
    calls = []

    def fake_call_openai_vision(*, image_bytes, filename, image_id, retry_note=None):
        calls.append(retry_note)
        if len(calls) == 1:
            return {
                "image_id": image_id,
                "store_name": STORE_NAME,
                "purchase_datetime": "2026-06-29 12:30:00",
                "items": [],
                "total_item_count": None,
                "total_amount": 2000,
                "currency": "KRW",
                "confidence_note": "Only total amount was visible",
            }
        return {
            "image_id": image_id,
            "store_name": STORE_NAME,
            "purchase_datetime": "2026-06-29 12:30:00",
            "items": [{"raw_name": BANANA_IMPORTED, "quantity": 1, "unit": EA, "item_amount": 2000}],
            "total_item_count": 1,
            "total_amount": 2000,
            "currency": "KRW",
            "confidence_note": None,
        }

    monkeypatch.setattr(service, "_call_openai_vision", fake_call_openai_vision)

    upload = UploadFile(filename="receipt.png", file=io.BytesIO(b"fake-image-bytes"))
    result = asyncio.run(service.analyze_upload(db=db_session, file=upload, user_id=user.id))

    assert len(calls) == 1
    assert result["items"] == []
    assert result["total_amount"] == 2000


def test_analyze_upload_requests_reupload_when_retry_stays_low_quality(db_session, monkeypatch, tmp_path):
    user = User(email="receipt-reupload@example.com", nickname="receipt reupload tester")
    db_session.add(user)
    db_session.flush()

    monkeypatch.setattr(settings, "OCR_UPLOAD_DIR", str(tmp_path / "raw"))

    service = ReceiptOcrService()
    calls = []

    def fake_call_openai_vision(*, image_bytes, filename, image_id, retry_note=None):
        calls.append(retry_note)
        return {
            "image_id": image_id,
            "store_name": None,
            "purchase_datetime": None,
            "items": [{"raw_name": "???", "quantity": None, "unit": None, "item_amount": None}],
            "total_item_count": None,
            "total_amount": None,
            "currency": "KRW",
            "confidence_note": "Unreadable receipt image",
        }

    monkeypatch.setattr(service, "_call_openai_vision", fake_call_openai_vision)

    upload = UploadFile(filename="receipt.png", file=io.BytesIO(b"fake-image-bytes"))
    result = asyncio.run(service.analyze_upload(db=db_session, file=upload, user_id=user.id))

    assert len(calls) == 2
    assert result["needs_reupload"] is True
    assert result["receipt_id"] is None
    assert "\uc601\uc218\uc99d" in result["reupload_message"]
    assert db_session.query(Receipt).count() == 0


def test_analyze_upload_requests_reupload_for_non_receipt_document(db_session, monkeypatch, tmp_path):
    user = User(email="receipt-non-receipt@example.com", nickname="receipt document tester")
    db_session.add(user)
    db_session.flush()

    monkeypatch.setattr(settings, "OCR_UPLOAD_DIR", str(tmp_path / "raw"))

    service = ReceiptOcrService()
    calls = []

    def fake_call_openai_vision(*, image_bytes, filename, image_id, retry_note=None):
        calls.append(retry_note)
        return {
            "image_id": image_id,
            "document_type": "non_receipt",
            "is_receipt_like": False,
            "store_name": None,
            "purchase_datetime": None,
            "items": [],
            "total_item_count": None,
            "total_amount": None,
            "currency": "KRW",
            "confidence_note": "The image is a project table, not a purchase receipt.",
        }

    monkeypatch.setattr(service, "_call_openai_vision", fake_call_openai_vision)

    upload = UploadFile(filename="table.png", file=io.BytesIO(b"fake-image-bytes"))
    result = asyncio.run(service.analyze_upload(db=db_session, file=upload, user_id=user.id))

    assert len(calls) == 1
    assert result["needs_reupload"] is True
    assert result["receipt_id"] is None
    assert result["document_type"] == "non_receipt"
    assert "non_receipt_document" in result["receipt_validation_issues"]
    assert "\uc601\uc218\uc99d \uc774\ubbf8\uc9c0\uac00 \uc544\ub2cc \uac83" in result["reupload_message"]
    assert db_session.query(Receipt).count() == 0


def test_confirm_receipt_saves_neo4j_standard_name_to_receipt_and_fridge_items(db_session, monkeypatch):
    user, receipt = seed_user_and_receipt(db_session)
    banana = seed_ingredient(db_session, BANANA)
    monkeypatch.setattr(
        ingredient_name_matcher,
        "_load_neo4j_candidates",
        lambda: [(ingredient_name_matcher._match_key(BANANA), BANANA)],
    )
    request_data = ReceiptConfirmRequest(
        receipt_id=receipt.id,
        store_name=STORE_NAME,
        purchase_datetime=None,
        total_amount=2000,
        calendar_cost_enabled=False,
        items=[
            {
                "raw_name": BANANA_IMPORTED,
                "normalized_name": BANANA_IMPORTED,
                "quantity": 1,
                "unit": EA,
                "item_amount": 2000,
                "storage_method": COLD_STORAGE,
                "item_memo": None,
            }
        ],
    )

    with patch(
        "app.backend.services.receipt_ocr_service.receipt_confirm_service.inventory_service._get_or_create_storage_rule",
        return_value=(COLD_STORAGE, 7),
    ):
        saved_count = receipt_confirm_service.save_confirmed_items(
            db=db_session,
            user_id=user.id,
            request_data=request_data,
        )

    receipt_item = db_session.query(ReceiptItem).one()
    fridge_item = db_session.query(FridgeItem).one()

    assert saved_count == 1
    assert receipt_item.raw_name == BANANA_IMPORTED
    assert receipt_item.normalized_name == BANANA
    assert receipt_item.ingredient_id == banana.id
    assert fridge_item.receipt_item_id == receipt_item.id
    assert fridge_item.display_name == BANANA
    assert fridge_item.ingredient_id == banana.id


def test_confirm_receipt_keeps_raw_name_when_no_neo4j_standard_name_matches(db_session, monkeypatch):
    user, receipt = seed_user_and_receipt(db_session)
    monkeypatch.setattr(
        ingredient_name_matcher,
        "_load_neo4j_candidates",
        lambda: [(ingredient_name_matcher._match_key(BANANA), BANANA)],
    )
    request_data = ReceiptConfirmRequest(
        receipt_id=receipt.id,
        store_name=STORE_NAME,
        purchase_datetime=None,
        total_amount=3000,
        calendar_cost_enabled=False,
        items=[
            {
                "raw_name": UNKNOWN_PRODUCT,
                "normalized_name": UNKNOWN_PRODUCT,
                "quantity": 1,
                "unit": EA,
                "item_amount": 3000,
                "storage_method": COLD_STORAGE,
                "item_memo": None,
            }
        ],
    )

    with patch(
        "app.backend.services.receipt_ocr_service.receipt_confirm_service.inventory_service._get_or_create_storage_rule",
        return_value=(COLD_STORAGE, 7),
    ):
        receipt_confirm_service.save_confirmed_items(
            db=db_session,
            user_id=user.id,
            request_data=request_data,
        )

    receipt_item = db_session.query(ReceiptItem).one()
    fridge_item = db_session.query(FridgeItem).one()
    created_ingredient = db_session.query(Ingredient).one()

    assert receipt_item.raw_name == UNKNOWN_PRODUCT
    assert receipt_item.normalized_name == UNKNOWN_PRODUCT
    assert fridge_item.display_name == UNKNOWN_PRODUCT
    assert created_ingredient.name == UNKNOWN_PRODUCT
