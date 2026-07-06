# 영수증 OCR 흐름의 핵심 동작(Neo4j 표준명 매칭, LangGraph 재분석, 확정 저장)을 검증하는 테스트 파일이다.
# 실제 PostgreSQL/Neo4j/OpenAI 호출 없이 격리된 DB와 mock으로 서비스 계약만 확인한다.
import asyncio
import importlib
import io
import os
import shutil
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import UploadFile
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from starlette.datastructures import Headers

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
TEST_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00"
)


def make_upload(filename: str = "receipt.png", content: bytes = TEST_PNG_BYTES) -> UploadFile:
    return UploadFile(
        filename=filename,
        file=io.BytesIO(content),
        headers=Headers({"content-type": "image/png"}),
    )


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
    user = seed_user(db_session, email="receipt-test@example.com", nickname="receipt tester")

    receipt = Receipt(user_id=user.id, original_file_name="receipt.jpg")
    db_session.add(receipt)
    db_session.flush()
    return user, receipt


def seed_user(db_session, *, email: str, nickname: str):
    user = User(email=email, nickname=nickname)
    db_session.add(user)
    db_session.flush()
    return user


def seed_ingredient(db_session, name: str, *, normalized_name: str | None = None, default_unit: str = EA):
    ingredient = Ingredient(
        name=name,
        normalized_name=normalized_name or name.replace(" ", "").lower(),
        default_unit=default_unit,
    )
    db_session.add(ingredient)
    db_session.flush()
    return ingredient


@pytest.fixture()
def workspace_tmp_dir():
    path = Path(__file__).resolve().parent / ".tmp" / f"receipt-ocr-flow-{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture()
def neo4j_banana_candidates(monkeypatch):
    monkeypatch.setattr(
        ingredient_name_matcher,
        "_load_neo4j_candidates",
        lambda: [(ingredient_name_matcher._match_key(BANANA), BANANA)],
    )


@pytest.fixture()
def mock_cold_storage_rule(monkeypatch):
    confirm_module = importlib.import_module("app.backend.services.receipt_ocr_service.receipt_confirm_service")
    monkeypatch.setattr(
        confirm_module.inventory_service,
        "_get_or_create_storage_rule",
        lambda db, ingredient, storage_method: (COLD_STORAGE, 7),
    )


# Neo4j 기준 표준명 매칭에서 괄호/원산지 제거 규칙이 깨지면 이 테스트가 알려준다.
def test_ingredient_matcher_strips_parentheses_and_returns_neo4j_standard_name(neo4j_banana_candidates):
    matched = ingredient_name_matcher.find_best_name(BANANA_IMPORTED)

    assert matched == BANANA


# Neo4j 후보에 없는 품목을 억지로 표준명 매칭하지 않도록 유지되는지 이 테스트가 알려준다.
def test_ingredient_matcher_returns_none_when_no_neo4j_standard_name_matches(neo4j_banana_candidates):
    matched = ingredient_name_matcher.find_best_name(UNKNOWN_PRODUCT)

    assert matched is None


# OCR 초안 정규화가 Neo4j 표준명을 우선 쓰고, 매칭 실패 시 원문으로 fallback 되는지 이 테스트가 알려준다.
def test_ocr_normalize_result_uses_neo4j_standard_name_or_raw_name_fallback(db_session, neo4j_banana_candidates):
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


# LangGraph OCR 품질 기준 미달 시 재분석을 1회 수행하고 개선된 결과를 저장하는지 이 테스트가 알려준다.
def test_analyze_upload_retries_low_quality_ocr_result(
    db_session,
    monkeypatch,
    workspace_tmp_dir,
    neo4j_banana_candidates,
):
    user = seed_user(db_session, email="receipt-graph@example.com", nickname="receipt graph tester")
    monkeypatch.setattr(settings, "OCR_UPLOAD_DIR", str(workspace_tmp_dir / "raw"))

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

    upload = make_upload()
    result = asyncio.run(service.analyze_upload(db=db_session, file=upload, user_id=user.id))

    assert len(calls) == 2
    assert calls[0] is None
    assert "item_names_unclear" in calls[1]
    assert "many_item_amounts_missing" in calls[1]
    assert result["items"][0]["raw_name"] == BANANA_IMPORTED
    assert result["items"][0]["normalized_name"] == BANANA
    assert result["receipt_id"] is not None
    assert "receipt" not in Path(result["original_file_path"]).name
    assert Path(result["original_file_path"]).suffix == ".png"
    assert result["quality_score"] == 1.0
    assert result["ocr_status"] == "completed"

    saved_receipt = db_session.query(Receipt).filter(Receipt.id == result["receipt_id"]).one()
    assert float(saved_receipt.ocr_quality_score) == 1.0
    assert saved_receipt.ocr_status == "completed"
    assert saved_receipt.ocr_error_message is None


def test_validate_upload_rejects_pdf_extension():
    service = ReceiptOcrService()
    upload = make_upload(filename="receipt.pdf")

    with pytest.raises(Exception) as exc_info:
        service._validate_upload(upload, TEST_PNG_BYTES)

    assert exc_info.value.status_code == 400
    assert "Unsupported image format" in exc_info.value.detail


def test_validate_upload_rejects_mismatched_mime_type():
    service = ReceiptOcrService()
    upload = UploadFile(
        filename="receipt.png",
        file=io.BytesIO(TEST_PNG_BYTES),
        headers=Headers({"content-type": "image/jpeg"}),
    )

    with pytest.raises(Exception) as exc_info:
        service._validate_upload(upload, TEST_PNG_BYTES)

    assert exc_info.value.status_code == 400
    assert "content type" in exc_info.value.detail


def test_validate_upload_rejects_mismatched_file_signature():
    service = ReceiptOcrService()
    upload = make_upload(content=b"not-a-real-image")

    with pytest.raises(Exception) as exc_info:
        service._validate_upload(upload, b"not-a-real-image")

    assert exc_info.value.status_code == 400
    assert "content does not match" in exc_info.value.detail


def test_upload_rate_limit_rejects_more_than_five_requests_per_minute(monkeypatch):
    service = ReceiptOcrService()
    monkeypatch.setattr(settings, "RECEIPT_UPLOAD_RATE_LIMIT_PER_MINUTE", 5)
    monkeypatch.setattr(settings, "RECEIPT_UPLOAD_RATE_LIMIT_PER_DAY", 50)

    for _ in range(5):
        service._enforce_upload_rate_limit(user_id=7)

    with pytest.raises(Exception) as exc_info:
        service._enforce_upload_rate_limit(user_id=7)

    assert exc_info.value.status_code == 429
    assert "per minute" in exc_info.value.detail


# 품목이 없어도 총액만 보이는 영수증/전표는 무조건 저품질 재시도 대상이 되지 않도록 이 테스트가 알려준다.
def test_analyze_upload_does_not_retry_when_only_total_amount_is_visible(
    db_session,
    monkeypatch,
    workspace_tmp_dir,
    neo4j_banana_candidates,
):
    user = seed_user(db_session, email="receipt-total-only@example.com", nickname="receipt total tester")
    monkeypatch.setattr(settings, "OCR_UPLOAD_DIR", str(workspace_tmp_dir / "raw"))

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

    upload = make_upload()
    result = asyncio.run(service.analyze_upload(db=db_session, file=upload, user_id=user.id))

    assert len(calls) == 1
    assert result["items"] == []
    assert result["total_amount"] == 2000
    assert result["ocr_status"] == "completed"


# 재분석 후에도 OCR 품질이 낮으면 DB 저장 대신 재업로드 응답으로 끝나는지 이 테스트가 알려준다.
def test_analyze_upload_requests_reupload_when_retry_stays_low_quality(db_session, monkeypatch, workspace_tmp_dir):
    user = seed_user(db_session, email="receipt-reupload@example.com", nickname="receipt reupload tester")
    monkeypatch.setattr(settings, "OCR_UPLOAD_DIR", str(workspace_tmp_dir / "raw"))

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

    upload = make_upload()
    result = asyncio.run(service.analyze_upload(db=db_session, file=upload, user_id=user.id))

    assert len(calls) == 2
    assert result["needs_reupload"] is True
    assert result["receipt_id"] is None
    assert result["ocr_status"] == "reupload_required"
    assert "item_names_unclear" in result["ocr_error_message"]
    assert "\uc601\uc218\uc99d" in result["reupload_message"]
    assert db_session.query(Receipt).count() == 0


# 영수증이 아닌 문서 이미지가 들어오면 OCR 저장 없이 재업로드 안내를 반환하는지 이 테스트가 알려준다.
def test_analyze_upload_requests_reupload_for_non_receipt_document(db_session, monkeypatch, workspace_tmp_dir):
    user = seed_user(db_session, email="receipt-non-receipt@example.com", nickname="receipt document tester")
    monkeypatch.setattr(settings, "OCR_UPLOAD_DIR", str(workspace_tmp_dir / "raw"))

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

    upload = make_upload(filename="table.png")
    result = asyncio.run(service.analyze_upload(db=db_session, file=upload, user_id=user.id))

    assert len(calls) == 1
    assert result["needs_reupload"] is True
    assert result["receipt_id"] is None
    assert result["document_type"] == "non_receipt"
    assert result["ocr_status"] == "reupload_required"
    assert "non_receipt_document" in result["receipt_validation_issues"]
    assert "\uc601\uc218\uc99d \uc774\ubbf8\uc9c0\uac00 \uc544\ub2cc \uac83" in result["reupload_message"]
    assert db_session.query(Receipt).count() == 0


# 사용자가 확정한 품목이 Neo4j 표준명 기준으로 receipt_items, fridge_items, 확정 JSON에 저장되는지 이 테스트가 알려준다.
def test_confirm_receipt_saves_neo4j_standard_name_to_receipt_and_fridge_items(
    db_session,
    neo4j_banana_candidates,
    mock_cold_storage_rule,
):
    user, receipt = seed_user_and_receipt(db_session)
    banana = seed_ingredient(db_session, BANANA)
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
    db_session.refresh(receipt)
    assert receipt.confirmed_result_json["receipt_id"] == receipt.id
    assert receipt.confirmed_result_json["items"][0]["normalized_name"] == BANANA
    assert receipt.confirmed_result_json["items"][0]["storage_method"] == COLD_STORAGE


# Neo4j 표준명 매칭이 실패한 확정 품목은 사용자가 확인한 원문명으로 저장되는지 이 테스트가 알려준다.
def test_confirm_receipt_keeps_raw_name_when_no_neo4j_standard_name_matches(
    db_session,
    neo4j_banana_candidates,
    mock_cold_storage_rule,
):
    user, receipt = seed_user_and_receipt(db_session)
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
