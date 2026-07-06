from app.backend.services.receipt_ocr_service.receipt_ocr_service import ReceiptOcrService


def test_receipt_feature_ab_accepts_receipt_and_rejects_non_receipt():
    service = ReceiptOcrService()

    accepted = service._validate_receipt_document(
        {"document_type": "receipt", "is_receipt_like": True, "store_name": "market"}
    )
    rejected = service._validate_receipt_document(
        {"document_type": "non_receipt", "is_receipt_like": False, "confidence_note": "not a receipt"}
    )

    assert accepted == []
    assert rejected == ["non_receipt_document", "receipt_evidence_missing"]
