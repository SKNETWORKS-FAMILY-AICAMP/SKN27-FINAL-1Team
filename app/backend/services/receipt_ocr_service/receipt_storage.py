from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from app.backend.core.config import settings


PROJECT_ROOT = Path(__file__).resolve().parents[4]
LOGGER = logging.getLogger(__name__)
KST = timezone(timedelta(hours=9))


class ReceiptStorage:
    """Store private receipt images locally in development or in S3 in production."""

    def __init__(self, config: Any = settings, s3_client: Any = None) -> None:
        self.config = config
        self._client = s3_client

    @property
    def backend(self) -> str:
        return str(self.config.RECEIPT_STORAGE_BACKEND).strip().lower()

    def save(self, *, user_id: int, image_bytes: bytes, extension: str) -> str:
        stored_name = f"{datetime.now(KST):%Y%m%d}_{uuid4().hex}{extension}"
        if self.backend == "s3":
            key = self._key_for(user_id, stored_name)
            self._s3_client().put_object(
                Bucket=self.config.S3_RECEIPT_BUCKET,
                Key=key,
                Body=image_bytes,
                ContentType=self.media_type(stored_name),
                ServerSideEncryption="AES256",
            )
            return f"s3://{self.config.S3_RECEIPT_BUCKET}/{key}"

        upload_root = self._local_root()
        user_dir = upload_root / str(user_id)
        user_dir.mkdir(parents=True, exist_ok=True)
        stored_path = user_dir / stored_name
        stored_path.write_bytes(image_bytes)
        return self._display_path(stored_path)

    def delete(self, stored_path: str | None) -> None:
        if not stored_path:
            return
        try:
            if self.is_s3_uri(stored_path):
                bucket, key = self._parse_s3_uri(stored_path)
                self._s3_client().delete_object(Bucket=bucket, Key=key)
                return
            local_path = self.local_path(stored_path)
            if local_path and local_path.is_file():
                local_path.unlink()
        except Exception:
            LOGGER.warning("Failed to delete receipt image %s", stored_path, exc_info=True)

    def presigned_get_url(self, stored_path: str, *, expires_seconds: int = 60) -> str:
        bucket, key = self._parse_s3_uri(stored_path)
        return self._s3_client().generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expires_seconds,
        )

    def open_s3_object(self, stored_path: str):
        bucket, key = self._parse_s3_uri(stored_path)
        response = self._s3_client().get_object(Bucket=bucket, Key=key)
        return response["Body"], response.get("ContentType") or self.media_type(key)

    def local_path(self, stored_path: str) -> Path | None:
        if self.is_s3_uri(stored_path):
            return None
        path = Path(stored_path)
        target = path if path.is_absolute() else PROJECT_ROOT / path
        try:
            resolved_target = target.resolve(strict=False)
            resolved_target.relative_to(self._local_root().resolve(strict=False))
        except (OSError, ValueError):
            return None
        return resolved_target

    @staticmethod
    def is_s3_uri(stored_path: str) -> bool:
        return stored_path.startswith("s3://")

    @staticmethod
    def object_stem(stored_path: str) -> str:
        return PurePosixPath(stored_path.replace("\\", "/")).stem

    @staticmethod
    def media_type(stored_path: str) -> str:
        return {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
        }.get(PurePosixPath(stored_path).suffix.lower(), "application/octet-stream")

    def _parse_s3_uri(self, stored_path: str) -> tuple[str, str]:
        parsed = urlparse(stored_path)
        bucket = parsed.netloc
        key = parsed.path.lstrip("/")
        prefix = str(self.config.S3_RECEIPT_PREFIX).strip("/")
        if (
            parsed.scheme != "s3"
            or bucket != self.config.S3_RECEIPT_BUCKET
            or not key
            or (prefix and not key.startswith(f"{prefix}/"))
        ):
            raise ValueError("Invalid receipt S3 object path.")
        return bucket, key

    def _key_for(self, user_id: int, stored_name: str) -> str:
        prefix = str(self.config.S3_RECEIPT_PREFIX).strip("/")
        return "/".join(part for part in (prefix, str(user_id), stored_name) if part)

    def _local_root(self) -> Path:
        path = Path(self.config.OCR_UPLOAD_DIR)
        return path if path.is_absolute() else PROJECT_ROOT / path

    @staticmethod
    def _display_path(path: Path) -> str:
        try:
            return path.relative_to(PROJECT_ROOT).as_posix()
        except ValueError:
            return path.as_posix()

    def _s3_client(self):
        if self._client is None:
            import boto3

            kwargs = {"region_name": self.config.AWS_REGION}
            if self.config.S3_ENDPOINT_URL:
                kwargs["endpoint_url"] = self.config.S3_ENDPOINT_URL
            self._client = boto3.client("s3", **kwargs)
        return self._client


receipt_storage = ReceiptStorage()
