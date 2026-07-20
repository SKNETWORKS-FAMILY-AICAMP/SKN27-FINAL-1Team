from fastapi import HTTPException

from app.backend.services.receipt_ocr_service.receipt_ocr_service import ReceiptOcrService


PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00"
)


def test_receipt_ocr_feature_detects_image_signatures_before_trusting_extension():
    service = ReceiptOcrService()

    assert service._detect_image_type(PNG_1X1) == "png"
    assert service._detect_image_type(b"\xff\xd8\xff\xe0fake") == "jpeg"
    assert service._detect_image_type(b"not image") is None


def test_receipt_ocr_feature_rejects_extension_signature_mismatch():
    service = ReceiptOcrService()

    class Upload:
        filename = "receipt.jpg"
        content_type = "image/jpeg"

    try:
        service._validate_upload(Upload(), PNG_1X1)
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "does not match" in exc.detail
    else:
        raise AssertionError("expected signature mismatch rejection")


def test_receipt_ocr_feature_parses_json_object_from_model_fence():
    service = ReceiptOcrService()

    parsed = service._parse_json_object('```json\n{"document_type":"receipt","items":[]}\n```')

    assert parsed == {"document_type": "receipt", "items": []}


def test_receipt_ocr_feature_normalizes_unknown_document_types():
    service = ReceiptOcrService()

    assert service._normalize_document_type("card-slip") == "card_slip"
    assert service._normalize_document_type("presentation") == "unknown"


def test_receipt_ocr_feature_quality_flags_missing_and_mismatched_receipt_data():
    service = ReceiptOcrService()

    score, issues = service._score_ocr_quality(
        {
            "items": [{"raw_name": "tofu", "item_amount": 1000}],
            "total_amount": 5000,
            "total_item_count": 1,
        }
    )

    assert score < 1.0
    assert {"store_name_missing", "purchase_datetime_missing", "total_amount_mismatch"} <= set(issues)


def test_receipt_ocr_feature_status_requires_reupload_for_low_quality():
    service = ReceiptOcrService()

    assert service._build_ocr_status(quality_score=0.2, quality_issues=["text_uncertain"]) == "reupload_required"
    assert service._build_ocr_status(quality_score=0.8, quality_issues=[]) == "needs_review"
    assert service._build_ocr_status(quality_score=0.9, quality_issues=["text_uncertain"]) == "needs_review"
    assert service._build_ocr_status(quality_score=1.0, quality_issues=[]) == "completed"
