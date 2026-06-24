from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.backend.db.models import Ingredient, IngredientAlias, Receipt, ReceiptItem
from app.backend.schemas.receipts import ReceiptConfirmRequest


KST = timezone(timedelta(hours=9))
ALLOWED_UNITS = {"개", "kg"}


class ReceiptConfirmService:
    def save_confirmed_items(self, *, db: Session, user_id: int, request_data: ReceiptConfirmRequest) -> int:
        receipt = (
            db.query(Receipt)
            .filter(
                Receipt.id == request_data.receipt_id,
                Receipt.user_id == user_id,
            )
            .first()
        )
        if not receipt:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="영수증을 찾을 수 없습니다.")

        receipt.store_name = request_data.store_name
        receipt.purchased_at = self._parse_purchase_datetime(request_data.purchase_datetime)
        receipt.total_price = request_data.total_amount

        db.query(ReceiptItem).filter(ReceiptItem.receipt_id == receipt.id).delete(synchronize_session=False)

        saved_count = 0
        for item in request_data.items:
            raw_name = (item.raw_name or "").strip()
            normalized_name = (item.normalized_name or raw_name).strip()
            if not raw_name and not normalized_name:
                continue

            ingredient = self._find_ingredient(db, normalized_name or raw_name)
            receipt_item = ReceiptItem(
                receipt_id=receipt.id,
                ingredient_id=ingredient.id if ingredient else None,
                raw_name=raw_name or normalized_name,
                normalized_name=normalized_name or raw_name,
                quantity=self._to_decimal(item.quantity),
                unit=item.unit if item.unit in ALLOWED_UNITS else "개",
                item_amount=item.item_amount,
                storage_method=item.storage_method,
                item_memo=item.item_memo,
            )
            db.add(receipt_item)
            saved_count += 1

        db.commit()
        return saved_count

    def _find_ingredient(self, db: Session, name: str) -> Optional[Ingredient]:
        normalized = self._normalize_name(name)
        if not normalized:
            return None

        ingredient = (
            db.query(Ingredient)
            .filter(
                (Ingredient.normalized_name == normalized)
                | (Ingredient.name == name)
            )
            .first()
        )
        if ingredient:
            return ingredient

        alias = db.query(IngredientAlias).filter(IngredientAlias.alias_name == name).first()
        return alias.ingredient if alias else None

    def _normalize_name(self, name: str) -> str:
        return name.strip().replace(" ", "").lower()

    def _to_decimal(self, value: Optional[float]) -> Optional[Decimal]:
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None

    def _parse_purchase_datetime(self, value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                return datetime.strptime(value, fmt).replace(tzinfo=KST)
            except ValueError:
                continue
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=KST)


receipt_confirm_service = ReceiptConfirmService()
