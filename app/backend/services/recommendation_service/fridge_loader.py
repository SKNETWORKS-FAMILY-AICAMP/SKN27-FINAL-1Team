"""냉장고 조회 (추천·상세 공통)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.backend.db.models import FridgeItem, Ingredient
from app.backend.services.recommendation_service.fridge_ingredient_match import FridgeItemSnapshot
from app.backend.services.recommendation_service.recommend_config import FridgeExpiryRow


def _fetch_fridge_rows(db: Session, user_id: int) -> list[FridgeExpiryRow]:
    rows = (
        db.query(FridgeItem, Ingredient)
        .join(Ingredient, FridgeItem.ingredient_id == Ingredient.id)
        .filter(
            FridgeItem.user_id == user_id,
            FridgeItem.status == "normal",
        )
        .all()
    )

    return [
        FridgeExpiryRow(
            ingredient_id=int(fridge_item.ingredient_id),
            fridge_name=fridge_item.display_name or ingredient.name,
            expiry_date=fridge_item.expiry_date,
            purchased_date=fridge_item.purchased_date,
        )
        for fridge_item, ingredient in rows
    ]


def fetch_fridge_items_with_expiry(db: Session, user_id: int) -> list[FridgeExpiryRow]:
    return _fetch_fridge_rows(db, user_id)


def fetch_fridge_snapshots(db: Session, user_id: int) -> list[FridgeItemSnapshot]:
    return [
        FridgeItemSnapshot(ingredient_id=row.ingredient_id, fridge_name=row.fridge_name)
        for row in _fetch_fridge_rows(db, user_id)
    ]
