from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session, selectinload

from app.backend.db.models import Receipt, ReceiptItem


KST = timezone(timedelta(hours=9))


class ReceiptHistoryService:
    """최근에 등록(확정)된 영수증 내역을 조회하는 서비스입니다."""

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
            "store_name": receipt.store_name,
            "purchase_datetime": self._format_datetime(receipt.purchased_at),
            "total_amount": receipt.total_price,
            "item_count": len(receipt.items),
            "original_file_name": receipt.original_file_name,
            "original_file_path": receipt.original_file_path,
            "items": [self._serialize_item(item) for item in receipt.items],
        }

    def _serialize_item(self, item: ReceiptItem) -> Dict[str, Any]:
        return {
            "raw_name": item.raw_name,
            "normalized_name": item.normalized_name,
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
