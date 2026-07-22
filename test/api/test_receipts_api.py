from datetime import datetime
from types import SimpleNamespace

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
    async def fake_analyze_upload(*, db, files, file, user_id, crop_mode):
        assert user_id == 7
        assert files is None
        assert file.filename == "receipt.png"
        assert crop_mode == "auto"
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
                    "normalization_match_type": "exact",
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
    assert body["items"][0]["normalization_match_type"] == "exact"
    assert body["items"][0]["unit"] == EA
    assert body["quality_score"] == 1.0
    assert body["ocr_status"] == "completed"


def test_upload_receipt_api_accepts_ordered_image_array(monkeypatch):
    async def fake_analyze_upload(*, db, files, file, user_id, crop_mode):
        assert user_id == 7
        assert file is None
        assert [upload.filename for upload in files] == ["top.png", "bottom.png"]
        assert crop_mode == "manual"
        return {
            "receipt_id": 11,
            "original_file_name": "top.png 외 1장",
            "original_file_path": "storage/raw/receipts/7/combined.jpg",
            "items": [],
            "currency": "KRW",
            "needs_reupload": False,
        }

    monkeypatch.setattr(receipts_api.receipt_ocr_service, "analyze_upload", fake_analyze_upload)

    client = create_test_client()
    response = client.post(
        "/api/v1/receipts/upload",
        files=[
            ("files", ("top.png", b"top-image", "image/png")),
            ("files", ("bottom.png", b"bottom-image", "image/png")),
        ],
        data={"crop_mode": "manual"},
    )

    assert response.status_code == 200
    assert response.json()["receipt_id"] == 11


def test_upload_receipt_stream_api_returns_stage_and_result_events(monkeypatch):
    async def fake_create_upload_event_stream(*, db, files, file, user_id, crop_mode):
        assert user_id == 7
        assert files is None
        assert file.filename == "receipt.png"
        assert crop_mode == "auto"

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


# 사용자 영수증 이미지가 브라우저나 중간 캐시에 저장되지 않도록 보안 헤더를 고정한다.
def test_receipt_image_response_disables_caching_and_mime_sniffing(monkeypatch, tmp_path):
    image_path = tmp_path / "receipt.png"
    image_path.write_bytes(b"fake-image-bytes")
    receipt = SimpleNamespace(original_file_path=str(image_path))

    class FakeQuery:
        def filter(self, *args):
            return self

        def first(self):
            return receipt

    fake_db = SimpleNamespace(query=lambda model: FakeQuery())
    monkeypatch.setattr(receipts_api.receipt_storage.config, "OCR_UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(receipts_api.receipt_storage.config, "RECEIPT_STORAGE_BACKEND", "local")

    response = receipts_api.get_receipt_image(receipt_id=10, current_user_id=7, db=fake_db)

    assert response.headers["cache-control"] == "private, no-store, max-age=0"
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_s3_receipt_image_is_streamed_without_redirect(monkeypatch):
    receipt = SimpleNamespace(original_file_path="s3://private-receipts/receipts/7/receipt.png")

    class FakeQuery:
        def filter(self, *args):
            return self

        def first(self):
            return receipt

    fake_db = SimpleNamespace(query=lambda model: FakeQuery())
    monkeypatch.setattr(receipts_api.receipt_storage.config, "S3_RECEIPT_BUCKET", "private-receipts")
    monkeypatch.setattr(receipts_api.receipt_storage.config, "S3_RECEIPT_PREFIX", "receipts")
    monkeypatch.setattr(
        receipts_api.receipt_storage,
        "open_s3_object",
        lambda stored_path: (b"fake-image-bytes", "image/png"),
    )

    response = receipts_api.get_receipt_image(receipt_id=10, current_user_id=7, db=fake_db)

    assert response.status_code == 200
    assert "location" not in response.headers
    assert response.media_type == "image/png"


def test_confirm_receipt_api_saves_confirmed_items(monkeypatch):
    saved = {}

    def fake_save_confirmed_items(*, db, user_id, request_data):
        saved["user_id"] = user_id
        saved["receipt_id"] = request_data.receipt_id
        saved["item_name"] = request_data.items[0].normalized_name
        return len(request_data.items)

    monkeypatch.setattr(receipts_api.receipt_confirm_service, "save_confirmed_items", fake_save_confirmed_items)
    monkeypatch.setattr(receipts_api, "_get_receipt_age_in_days", lambda value: 31)

    client = create_test_client()
    response = client.post(
        "/api/v1/receipts/confirm",
        json={
            "receipt_id": 10,
            "store_name": STORE_NAME,
            "purchase_datetime": "2026-06-29 12:30:00",
            "total_amount": 2000,
            "calendar_cost_enabled": False,
            "old_receipt_confirmed": True,
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


def test_confirm_receipt_calendar_event_uses_receipt_registration_copy(monkeypatch):
    saved_event = {}

    def fake_save_confirmed_items(*, db, user_id, request_data):
        return len(request_data.items)

    async def fake_get_access_token(integration, db):
        return "google-access-token"

    async def fake_create_event_once(client, calendar_id, access_token, event_key, event, db, user_id, source):
        saved_event.update(
            {
                "calendar_id": calendar_id,
                "access_token": access_token,
                "event_key": event_key,
                "event": event,
                "user_id": user_id,
                "source": source,
            }
        )

    monkeypatch.setattr(receipts_api.receipt_confirm_service, "save_confirmed_items", fake_save_confirmed_items)
    monkeypatch.setattr(receipts_api, "_get_receipt_age_in_days", lambda value: 0)
    monkeypatch.setattr(receipts_api, "_get_google_integration", lambda db, user_id: SimpleNamespace(calendar_id="primary"))
    monkeypatch.setattr(receipts_api, "_get_access_token", fake_get_access_token)
    monkeypatch.setattr(receipts_api, "_create_event_once", fake_create_event_once)

    client = create_test_client()
    response = client.post(
        "/api/v1/receipts/confirm",
        json={
            "receipt_id": 10,
            "store_name": STORE_NAME,
            "purchase_datetime": "2026-06-29 12:30:00",
            "total_amount": 2000,
            "calendar_cost_enabled": True,
            "old_receipt_confirmed": False,
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
    assert saved_event["event"]["summary"] == "영수증 등록 완료"
    assert "OCR" not in saved_event["event"]["description"]
    assert "사용비용" not in saved_event["event"]["description"]
    assert "총 금액: 2,000원" in saved_event["event"]["description"]


def test_receipt_age_policy_warns_only_after_thirty_calendar_days():
    now = datetime(2026, 7, 20, 12, 0, tzinfo=receipts_api.KST)

    assert receipts_api._get_receipt_age_in_days("2026-06-20 09:00:00", now=now) == 30
    assert receipts_api._get_receipt_age_in_days("2026-06-19 23:59:59", now=now) == 31


# 30일 초과 영수증은 사용자가 소비기한 경고를 확인하기 전까지 입고하지 않는다.
def test_confirm_receipt_api_rejects_old_receipt_without_acknowledgement(monkeypatch):
    save_called = False

    def fail_if_saved(**kwargs):
        nonlocal save_called
        save_called = True

    monkeypatch.setattr(receipts_api.receipt_confirm_service, "save_confirmed_items", fail_if_saved)
    monkeypatch.setattr(receipts_api, "_get_receipt_age_in_days", lambda value: 31)

    client = create_test_client()
    response = client.post(
        "/api/v1/receipts/confirm",
        json={
            "receipt_id": 10,
            "purchase_datetime": "2026-06-19 12:30:00",
            "calendar_cost_enabled": False,
            "old_receipt_confirmed": False,
            "items": [],
        },
    )

    assert response.status_code == 409
    assert "30일" in response.json()["detail"]
    assert save_called is False


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
