from types import SimpleNamespace

import pytest

from app.backend.services.receipt_ocr_service.receipt_storage import ReceiptStorage


class FakeS3Client:
    def __init__(self):
        self.put_calls = []
        self.delete_calls = []
        self.get_calls = []
        self.presign_calls = []

    def put_object(self, **kwargs):
        self.put_calls.append(kwargs)

    def delete_object(self, **kwargs):
        self.delete_calls.append(kwargs)

    def get_object(self, **kwargs):
        self.get_calls.append(kwargs)
        return {"Body": b"image", "ContentType": "image/png"}

    def generate_presigned_url(self, operation, **kwargs):
        self.presign_calls.append((operation, kwargs))
        return "https://signed.example/receipt"


def test_s3_receipt_storage_saves_reads_and_deletes_private_object():
    config = SimpleNamespace(
        RECEIPT_STORAGE_BACKEND="s3",
        S3_RECEIPT_BUCKET="private-receipts",
        S3_RECEIPT_PREFIX="receipts",
        OCR_UPLOAD_DIR="unused",
        AWS_REGION="ap-northeast-2",
        S3_ENDPOINT_URL="",
    )
    client = FakeS3Client()
    storage = ReceiptStorage(config=config, s3_client=client)

    stored_path = storage.save(user_id=7, image_bytes=b"image", extension=".png")

    assert stored_path.startswith("s3://private-receipts/receipts/7/")
    assert stored_path.endswith(".png")
    assert client.put_calls == [
        {
            "Bucket": "private-receipts",
            "Key": stored_path.removeprefix("s3://private-receipts/"),
            "Body": b"image",
            "ContentType": "image/png",
            "ServerSideEncryption": "AES256",
        }
    ]
    assert storage.presigned_get_url(stored_path) == "https://signed.example/receipt"
    body, media_type = storage.open_s3_object(stored_path)
    assert body == b"image"
    assert media_type == "image/png"
    assert client.get_calls == [
        {
            "Bucket": "private-receipts",
            "Key": stored_path.removeprefix("s3://private-receipts/"),
        }
    ]
    storage.delete(stored_path)
    assert client.delete_calls == [
        {
            "Bucket": "private-receipts",
            "Key": stored_path.removeprefix("s3://private-receipts/"),
        }
    ]


def test_s3_receipt_storage_rejects_another_bucket_or_prefix():
    config = SimpleNamespace(
        RECEIPT_STORAGE_BACKEND="s3",
        S3_RECEIPT_BUCKET="private-receipts",
        S3_RECEIPT_PREFIX="receipts",
        OCR_UPLOAD_DIR="unused",
        AWS_REGION="ap-northeast-2",
        S3_ENDPOINT_URL="",
    )
    storage = ReceiptStorage(config=config, s3_client=FakeS3Client())

    with pytest.raises(ValueError, match="Invalid receipt S3 object path"):
        storage.presigned_get_url("s3://another-bucket/receipts/7/file.png")
    with pytest.raises(ValueError, match="Invalid receipt S3 object path"):
        storage.presigned_get_url("s3://private-receipts/outside/file.png")
