from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, selectinload

from app.backend.core.config import settings
from app.backend.db.models import Receipt, ReceiptItem
from app.backend.services.receipt_ocr_service.privacy_masking import mask_sensitive_text


KST = timezone(timedelta(hours=9))
PROJECT_ROOT = Path(__file__).resolve().parents[4]


class ReceiptHistoryService:
    """최근에 등록(확정)된 영수증 내역을 조회/삭제하는 서비스입니다."""

    def update_store_name(self, *, db: Session, user_id: int, receipt_id: int, store_name: str) -> Dict[str, Any]:
        receipt = (
            db.query(Receipt)
            .filter(Receipt.id == receipt_id, Receipt.user_id == user_id)
            .options(selectinload(Receipt.items))
            .first()
        )
        if not receipt:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="영수증을 찾을 수 없습니다.")

        cleaned = (mask_sensitive_text(store_name) or "").strip()
        if not cleaned:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="영수증 제목을 입력해주세요.")

        receipt.store_name = cleaned
        db.commit()
        db.refresh(receipt)

        return self._serialize(receipt)

    def delete_receipt(self, *, db: Session, user_id: int, receipt_id: int) -> None:
        receipt = (
            db.query(Receipt)
            .filter(Receipt.id == receipt_id, Receipt.user_id == user_id)
            .first()
        )
        if not receipt:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="영수증을 찾을 수 없습니다.")

        original_file_path = receipt.original_file_path

        # 영수증과 영수증 품목만 삭제됩니다. 이미 냉장고에 입고된 식재료는
        # fridge_items.receipt_item_id ON DELETE SET NULL 로 보존됩니다.
        db.delete(receipt)
        db.commit()

        self._delete_file(original_file_path)

    def _delete_file(self, relative_or_absolute_path: Optional[str]) -> None:
        if not relative_or_absolute_path:
            return

        target = self._resolve_deletable_upload_path(relative_or_absolute_path)
        if not target:
            return

        try:
            if target.is_file():
                target.unlink()
        except OSError:
            pass

    def _resolve_deletable_upload_path(self, relative_or_absolute_path: str) -> Optional[Path]:
        path = Path(relative_or_absolute_path)
        target = path if path.is_absolute() else PROJECT_ROOT / path
        upload_root = self._resolve_storage_root(settings.OCR_UPLOAD_DIR)

        try:
            resolved_target = target.resolve(strict=False)
            resolved_upload_root = upload_root.resolve(strict=False)
            resolved_target.relative_to(resolved_upload_root)
        except (OSError, ValueError):
            return None

        return resolved_target

    def _resolve_storage_root(self, path_value: str) -> Path:
        path = Path(path_value)
        return path if path.is_absolute() else PROJECT_ROOT / path

    def get_recent_receipts(self, *, db: Session, user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        receipts = (
            db.query(Receipt)
            .filter(Receipt.user_id == user_id)
            .filter(Receipt.items.any())
            .options(selectinload(Receipt.items))
            .order_by(Receipt.created_at.desc())
            .limit(limit)
            .all()
        )
        return [self._serialize(receipt) for receipt in receipts]

    def _serialize(self, receipt: Receipt) -> Dict[str, Any]:
        return {
            "receipt_id": receipt.id,
            "store_name": mask_sensitive_text(receipt.store_name),
            "purchase_datetime": self._format_datetime(receipt.purchased_at),
            "total_amount": receipt.total_price,
            "item_count": len(receipt.items),
            "original_file_name": receipt.original_file_name,
            "original_file_path": receipt.original_file_path,
            "items": [self._serialize_item(item) for item in receipt.items],
        }

    def _serialize_item(self, item: ReceiptItem) -> Dict[str, Any]:
        return {
            "raw_name": mask_sensitive_text(item.raw_name),
            "normalized_name": mask_sensitive_text(item.normalized_name),
            "quantity": float(item.quantity) if item.quantity is not None else None,
            "unit": item.unit,
            "item_amount": item.item_amount,
            "storage_method": item.storage_method,
        }

    def _format_datetime(self, value: Optional[datetime]) -> Optional[str]:
        if not value:
            return None

        aware = value if value.tzinfo else value.replace(tzinfo=KST)
        return aware.astimezone(KST).strftime("%Y-%m-%d %H:%M")


receipt_history_service = ReceiptHistoryService()
