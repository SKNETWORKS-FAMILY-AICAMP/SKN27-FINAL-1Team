"""냉장고 조회 (추천·상세 공통)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app.backend.db.models import FridgeItem, Ingredient
from app.backend.services.recommendation_service.fridge_ingredient_match import FridgeItemSnapshot


@dataclass(frozen=True)
class FridgeExpiryRow:
    ingredient_id: int
    fridge_name: str
    expiry_date: date | None
    purchased_date: date | None
    status: str | None = None


def _fetch_fridge_rows(
    db: Session,
    user_id: int,
    statuses: tuple[str, ...] = ("normal",),
) -> list[FridgeExpiryRow]:
    rows = (
        db.query(FridgeItem, Ingredient)
        .join(Ingredient, FridgeItem.ingredient_id == Ingredient.id)
        .filter(
            FridgeItem.user_id == user_id,
            FridgeItem.status.in_(statuses),
        )
        .all()
    )

    return [
        FridgeExpiryRow(
            ingredient_id=int(fridge_item.ingredient_id),
            fridge_name=fridge_item.display_name or ingredient.name,
            expiry_date=fridge_item.expiry_date,
            purchased_date=fridge_item.purchased_date,
            status=fridge_item.status,
        )
        for fridge_item, ingredient in rows
    ]


def fetch_fridge_snapshots(
    db: Session,
    user_id: int,
    statuses: tuple[str, ...] = ("normal",),
) -> list[FridgeItemSnapshot]:
    return [
        FridgeItemSnapshot(
            ingredient_id=row.ingredient_id,
            fridge_name=row.fridge_name,
            expiry_date=row.expiry_date,
            status=row.status,
        )
        for row in _fetch_fridge_rows(db, user_id, statuses=statuses)
    ]


def fetch_fridge_expiry_rows(db: Session, user_id: int) -> list[FridgeExpiryRow]:
    return _fetch_fridge_rows(db, user_id)
