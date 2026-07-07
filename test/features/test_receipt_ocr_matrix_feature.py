import pytest

from app.backend.services.receipt_ocr_service.receipt_ocr_service import ReceiptOcrService


@pytest.fixture
def service():
    return ReceiptOcrService()


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("", None),
        (" null ", None),
        (" tofu ", "tofu"),
        (123, "123"),
    ],
)
def test_receipt_ocr_feature_nullable_str_matrix(service, value, expected):
    assert service._nullable_str(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (True, True),
        (False, False),
        ("true", True),
        ("1", True),
        ("yes", True),
        ("false", False),
        ("0", False),
        ("no", False),
        (None, None),
        ("maybe", None),
    ],
)
def test_receipt_ocr_feature_nullable_bool_matrix(service, value, expected):
    assert service._nullable_bool(value) is expected


@pytest.mark.parametrize(
    ("value", "number", "integer"),
    [
        (None, None, None),
        ("", None, None),
        ("1000", 1000.0, 1000),
        ("1000.4", 1000.4, 1000),
        ("1000.6", 1000.6, 1001),
        ("bad", None, None),
    ],
)
def test_receipt_ocr_feature_nullable_number_and_int_matrix(service, value, number, integer):
    assert service._nullable_number(value) == number
    assert service._nullable_int(value) == integer


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("receipt", "receipt"),
        ("card-slip", "card_slip"),
        ("e receipt", "e_receipt"),
        ("non-receipt", "non_receipt"),
        ("menu", "unknown"),
        (None, "unknown"),
    ],
)
def test_receipt_ocr_feature_document_type_matrix(service, value, expected):
    assert service._normalize_document_type(value) == expected


@pytest.mark.parametrize(
    ("normalized", "expected"),
    [
        ({"items": [{"raw_name": "tofu"}]}, True),
        ({"store_name": "market"}, True),
        ({"purchase_datetime": "2026-07-07 09:00:00"}, True),
        ({"total_amount": 1000}, True),
        ({"confidence_note": "card approval slip"}, True),
        ({"confidence_note": "영수증 결제 승인"}, True),
        ({"confidence_note": "not a receipt"}, False),
        ({}, False),
    ],
)
def test_receipt_ocr_feature_receipt_evidence_matrix(service, normalized, expected):
    assert service._has_receipt_evidence(normalized) is expected


@pytest.mark.parametrize(
    ("normalized", "expected"),
    [
        ({"document_type": "receipt", "is_receipt_like": True, "items": [{"raw_name": "tofu"}]}, []),
        ({"document_type": "non_receipt", "is_receipt_like": False}, ["non_receipt_document", "receipt_evidence_missing"]),
        ({"document_type": "receipt", "is_receipt_like": False}, ["non_receipt_document", "receipt_evidence_missing"]),
        ({"document_type": "receipt", "is_receipt_like": True}, ["receipt_evidence_missing"]),
    ],
)
def test_receipt_ocr_feature_document_validation_matrix(service, normalized, expected):
    assert service._validate_receipt_document(normalized) == expected


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("receipt.jpg", "image/jpeg"),
        ("receipt.jpeg", "image/jpeg"),
        ("receipt.png", "image/png"),
        ("receipt.webp", "image/webp"),
        ("receipt.pdf", "application/octet-stream"),
    ],
)
def test_receipt_ocr_feature_guess_mime_type_matrix(service, filename, expected):
    assert service._guess_mime_type(filename) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, True),
        ("", True),
        ("?", True),
        ("a", True),
        ("tofu", False),
        ("두부", False),
    ],
)
def test_receipt_ocr_feature_unclear_item_name_matrix(service, value, expected):
    assert service._is_unclear_item_name(value) is expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-07-07 09:30:00", True),
        ("2026-07-07 09:30", True),
        ("2026-07-07T09:30:00+09:00", True),
        ("not a date", False),
        (None, False),
    ],
)
def test_receipt_ocr_feature_purchase_datetime_matrix(service, value, expected):
    assert (service._parse_purchase_datetime(value) is not None) is expected


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ('{"a": 1}', {"a": 1}),
        ('prefix {"a": 1} suffix', {"a": 1}),
        ('```json\n{"a": 1}\n```', {"a": 1}),
        ('```\n{"a": 1}\n```', {"a": 1}),
    ],
)
def test_receipt_ocr_feature_parse_json_object_matrix(service, content, expected):
    assert service._parse_json_object(content) == expected


@pytest.mark.parametrize("content", ["", "[]", "no json here", "{bad json}"])
def test_receipt_ocr_feature_parse_json_object_rejects_invalid_content(service, content):
    with pytest.raises(ValueError):
        service._parse_json_object(content)
