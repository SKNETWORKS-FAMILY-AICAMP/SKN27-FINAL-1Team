from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.backend.api.receipts import receipts_api


EA = "\uac1c"
BANANA = "\ubc14\ub098\ub098"
COLD_STORAGE = "\ub0c9\uc7a5"
STORE_NAME = "\ud14c\uc2a4\ud2b8\ub9c8\ud2b8"


def create_test_client():
    app = FastAPI()
    app.include_router(receipts_api.router, prefix="/api/v1")
    app.dependency_overrides[receipts_api.get_current_user_required] = lambda: 7
    app.dependency_overrides[receipts_api.get_db] = lambda: object()
    return TestClient(app)


def test_upload_receipt_api_returns_ocr_candidates(monkeypatch):
    async def fake_analyze_upload(*, db, file, user_id, **kwargs):
        assert user_id == 7
        assert file.filename == "receipt.png"
        return {
            "receipt_id": 10,
            "original_file_name": "receipt.png",
            "original_file_path": "storage/raw/receipts/7/receipt.png",
            "store_name": STORE_NAME,
            "purchase_datetime": "2026-06-29 12:30:00",
            "items": [
                {
                    "raw_name": "\ubc14\ub098\ub098(\uc218\uc785\uc0b0)",
                    "normalized_name": BANANA,
                    "quantity": 1,
                    "unit": EA,
                    "item_amount": 2000,
                }
            ],
            "total_item_count": 1,
            "total_amount": 2000,
            "currency": "KRW",
            "confidence_note": None,
            "quality_score": 1.0,
            "quality_issues": [],
            "ocr_status": "completed",
            "ocr_error_message": None,
        }

    monkeypatch.setattr(receipts_api.receipt_ocr_service, "analyze_upload", fake_analyze_upload)

    client = create_test_client()
    response = client.post(
        "/api/v1/receipts/upload",
        files={"file": ("receipt.png", b"fake-image-bytes", "image/png")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["receipt_id"] == 10
    assert body["items"][0]["raw_name"] == "\ubc14\ub098\ub098(\uc218\uc785\uc0b0)"
    assert body["items"][0]["normalized_name"] == BANANA
    assert body["items"][0]["unit"] == EA
    assert body["quality_score"] == 1.0
    assert body["ocr_status"] == "completed"


def test_upload_receipt_stream_api_returns_stage_and_result_events(monkeypatch):
    async def fake_create_upload_event_stream(*, db, file, user_id, **kwargs):
        assert user_id == 7
        assert file.filename == "receipt.png"

        async def events():
            yield {"type": "stage", "stage": "image_uploaded"}
            yield {
                "type": "result",
                "data": {
                    "receipt_id": 10,
                    "original_file_name": "receipt.png",
                    "original_file_path": "storage/raw/receipts/7/receipt.png",
                    "store_name": STORE_NAME,
                    "purchase_datetime": "2026-06-29 12:30:00",
                    "items": [],
                    "total_item_count": 0,
                    "total_amount": 2000,
                    "currency": "KRW",
                    "confidence_note": None,
                    "quality_score": 1.0,
                    "quality_issues": [],
                    "ocr_status": "completed",
                    "ocr_error_message": None,
                    "needs_reupload": False,
                },
            }

        return events()

    monkeypatch.setattr(receipts_api.receipt_ocr_service, "create_upload_event_stream", fake_create_upload_event_stream)

    client = create_test_client()
    response = client.post(
        "/api/v1/receipts/upload/stream",
        files={"file": ("receipt.png", b"fake-image-bytes", "image/png")},
    )

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    assert "event: stage" in response.text
    assert '"stage": "image_uploaded"' in response.text
    assert "event: result" in response.text
    assert '"receipt_id": 10' in response.text
    assert '"ocr_status": "completed"' in response.text


def test_confirm_receipt_api_saves_confirmed_items(monkeypatch):
    saved = {}

    def fake_save_confirmed_items(*, db, user_id, request_data):
        saved["user_id"] = user_id
        saved["receipt_id"] = request_data.receipt_id
        saved["item_name"] = request_data.items[0].normalized_name
        return len(request_data.items)

    monkeypatch.setattr(receipts_api.receipt_confirm_service, "save_confirmed_items", fake_save_confirmed_items)

    client = create_test_client()
    response = client.post(
        "/api/v1/receipts/confirm",
        json={
            "receipt_id": 10,
            "store_name": STORE_NAME,
            "purchase_datetime": "2026-06-29 12:30:00",
            "total_amount": 2000,
            "calendar_cost_enabled": False,
            "items": [
                {
                    "raw_name": "\ubc14\ub098\ub098(\uc218\uc785\uc0b0)",
                    "normalized_name": BANANA,
                    "quantity": 1,
                    "unit": EA,
                    "item_amount": 2000,
                    "storage_method": COLD_STORAGE,
                    "item_memo": None,
                }
            ],
        },
    )

    assert response.status_code == 200
    assert response.json()["message"] == "\uc131\uacf5\uc801\uc73c\ub85c 1\uac1c \ud488\ubaa9\uc744 \uc800\uc7a5\ud588\uc2b5\ub2c8\ub2e4."
    assert saved == {"user_id": 7, "receipt_id": 10, "item_name": BANANA}


def test_receipt_history_api_returns_recent_receipts(monkeypatch):
    def fake_get_recent_receipts(*, db, user_id, limit):
        assert user_id == 7
        assert limit == 5
        return [
            {
                "receipt_id": 10,
                "store_name": STORE_NAME,
                "purchase_datetime": "2026-06-29 12:30",
                "total_amount": 2000,
                "item_count": 1,
                "original_file_name": "receipt.png",
                "original_file_path": "storage/raw/receipts/7/receipt.png",
                "items": [
                    {
                        "raw_name": "\ubc14\ub098\ub098(\uc218\uc785\uc0b0)",
                        "normalized_name": BANANA,
                        "quantity": 1,
                        "unit": EA,
                        "item_amount": 2000,
                        "storage_method": COLD_STORAGE,
                    }
                ],
            }
        ]

    monkeypatch.setattr(receipts_api.receipt_history_service, "get_recent_receipts", fake_get_recent_receipts)

    client = create_test_client()
    response = client.get("/api/v1/receipts/history?limit=5")

    assert response.status_code == 200
    body = response.json()
    assert body["receipts"][0]["receipt_id"] == 10
    assert body["receipts"][0]["items"][0]["normalized_name"] == BANANA


def test_delete_receipt_api_deletes_user_receipt(monkeypatch):
    deleted = {}

    def fake_delete_receipt(*, db, user_id, receipt_id):
        deleted["user_id"] = user_id
        deleted["receipt_id"] = receipt_id

    monkeypatch.setattr(receipts_api.receipt_history_service, "delete_receipt", fake_delete_receipt)

    client = create_test_client()
    response = client.delete("/api/v1/receipts/10")

    assert response.status_code == 200
    assert response.json()["message"] == "\uc601\uc218\uc99d \ub0b4\uc5ed\uc744 \uc0ad\uc81c\ud588\uc5b4\uc694."
    assert deleted == {"user_id": 7, "receipt_id": 10}
