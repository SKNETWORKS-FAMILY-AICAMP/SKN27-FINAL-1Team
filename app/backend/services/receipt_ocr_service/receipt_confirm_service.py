from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.backend.db.models import FridgeItem, Ingredient, IngredientAlias, Receipt, ReceiptItem
from app.backend.schemas.receipts import ReceiptConfirmRequest
from app.backend.services.ingredient_match_service import ingredient_name_matcher
from app.backend.services.inventory_service.inventory_service import inventory_service
from app.backend.services.receipt_ocr_service.privacy_masking import mask_sensitive_text


KST = timezone(timedelta(hours=9))
DEFAULT_UNIT = "\uac1c"
ALLOWED_UNITS = {DEFAULT_UNIT, "kg"}


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
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Receipt not found.")

        receipt.store_name = mask_sensitive_text(request_data.store_name)
        receipt.purchased_at = self._parse_purchase_datetime(request_data.purchase_datetime)
        receipt.total_price = request_data.total_amount

        existing_item_ids = [
            row[0]
            for row in db.query(ReceiptItem.id)
            .filter(ReceiptItem.receipt_id == receipt.id)
            .all()
        ]
        if existing_item_ids:
            db.query(FridgeItem).filter(
                FridgeItem.user_id == user_id,
                FridgeItem.receipt_item_id.in_(existing_item_ids),
            ).delete(synchronize_session=False)
            db.query(ReceiptItem).filter(ReceiptItem.id.in_(existing_item_ids)).delete(synchronize_session=False)

        saved_count = 0
        confirmed_items: List[Dict[str, Any]] = []
        for item in request_data.items:
            raw_name = (mask_sensitive_text(item.raw_name) or "").strip()
            normalized_name = (mask_sensitive_text(item.normalized_name) or raw_name).strip()
            if not raw_name and not normalized_name:
                continue

            final_name = (
                ingredient_name_matcher.find_best_name(raw_name)
                or ingredient_name_matcher.find_best_name(normalized_name)
                or normalized_name
                or raw_name
            )
            ingredient = self._get_or_create_ingredient(db, final_name, item.unit)
            final_name = ingredient.name
            receipt_item = ReceiptItem(
                receipt_id=receipt.id,
                ingredient_id=ingredient.id,
                raw_name=raw_name or normalized_name,
                normalized_name=final_name,
                quantity=self._to_decimal(item.quantity),
                unit=item.unit if item.unit in ALLOWED_UNITS else DEFAULT_UNIT,
                item_amount=item.item_amount,
                storage_method=item.storage_method,
                item_memo=mask_sensitive_text(item.item_memo),
            )
            db.add(receipt_item)
            db.flush()
            self._create_fridge_item(
                db=db,
                user_id=user_id,
                receipt=receipt,
                receipt_item=receipt_item,
                ingredient=ingredient,
            )
            confirmed_items.append(
                {
                    "receipt_item_id": receipt_item.id,
                    "ingredient_id": ingredient.id,
                    "raw_name": receipt_item.raw_name,
                    "normalized_name": receipt_item.normalized_name,
                    "quantity": float(receipt_item.quantity) if receipt_item.quantity is not None else None,
                    "unit": receipt_item.unit,
                    "item_amount": receipt_item.item_amount,
                    "storage_method": receipt_item.storage_method,
                    "item_memo": receipt_item.item_memo,
                }
            )
            saved_count += 1

        receipt.confirmed_result_json = {
            "receipt_id": receipt.id,
            "store_name": receipt.store_name,
            "purchase_datetime": request_data.purchase_datetime,
            "total_amount": receipt.total_price,
            "items": confirmed_items,
            "calendar_cost_enabled": request_data.calendar_cost_enabled,
            "source": "user_confirmed_receipt",
        }

        db.commit()
        return saved_count

    def _create_fridge_item(
        self,
        *,
        db: Session,
        user_id: int,
        receipt: Receipt,
        receipt_item: ReceiptItem,
        ingredient: Ingredient,
    ) -> None:
        purchase_date = self._purchase_date(receipt.purchased_at)
        storage_location, lifespan_days = inventory_service._get_or_create_storage_rule(
            db,
            ingredient,
            receipt_item.storage_method,
        )
        expiry_date = purchase_date + timedelta(days=lifespan_days)
        d_day = (expiry_date - date.today()).days

        db.add(
            FridgeItem(
                user_id=user_id,
                ingredient_id=ingredient.id,
                receipt_item_id=receipt_item.id,
                display_name=receipt_item.normalized_name or receipt_item.raw_name,
                quantity=receipt_item.quantity,
                unit=receipt_item.unit or ingredient.default_unit or DEFAULT_UNIT,
                storage_location=storage_location,
                purchased_date=purchase_date,
                expiry_date=expiry_date,
                status=inventory_service._get_status_from_d_day(d_day),
            )
        )

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

    def _get_or_create_ingredient(self, db: Session, name: str, unit: Optional[str]) -> Ingredient:
        ingredient = self._find_ingredient(db, name)
        if ingredient:
            return ingredient

        normalized = self._normalize_name(name)
        try:
            with db.begin_nested():
                ingredient = Ingredient(
                    name=name.strip(),
                    normalized_name=normalized,
                    default_unit=unit if unit in ALLOWED_UNITS else DEFAULT_UNIT,
                )
                db.add(ingredient)
                db.flush()
                return ingredient
        except IntegrityError:
            ingredient = db.query(Ingredient).filter(Ingredient.normalized_name == normalized).first()
            if ingredient:
                return ingredient
            raise

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

    def _purchase_date(self, value: Optional[datetime]) -> date:
        if not value:
            return date.today()
        aware = value if value.tzinfo else value.replace(tzinfo=KST)
        return aware.astimezone(KST).date()


receipt_confirm_service = ReceiptConfirmService()
