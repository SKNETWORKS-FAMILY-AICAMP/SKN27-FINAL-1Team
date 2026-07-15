"""냉장고 조회 + 재료 매칭 (추천·상세 공통)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.backend.db.models import FridgeItem, Ingredient
from app.backend.services.recommendation_service.recommend_config import (
    BASIC_INGREDIENT_IDS,
    BASIC_INGREDIENT_NORMALIZED_NAMES,
    basic_ingredient_normalized,
)

MAYBE_OWNED_WEIGHT = 0.5
MAYBE_MATCH_SCORE = 1.0

MatchType = Literal["recipe_in_fridge", "fridge_in_recipe"]


# ── 데이터 클래스 ──


@dataclass(frozen=True)
class FridgeItemSnapshot:
    ingredient_id: int | None
    fridge_name: str
    expiry_date: date | None = None
    status: str | None = None


@dataclass(frozen=True)
class FridgeExpiryRow:
    ingredient_id: int
    fridge_name: str
    expiry_date: date | None
    purchased_date: date | None
    status: str | None = None


@dataclass(frozen=True)
class MaybeMatch:
    fridge_ingredient_name: str
    match_type: MatchType
    score: float
    overlap_length: int
    expiry_date: date | None = None
    status: str | None = None


@dataclass(frozen=True)
class MatchRates:
    match_rate: int
    display_match_rate: int


@dataclass(frozen=True)
class FridgeMatchResult:
    owned: list[dict[str, Any]]
    maybe_owned: list[dict[str, Any]]
    missing: list[dict[str, Any]]
    match_rate: int
    display_match_rate: int


# ── DB 조회 ──


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


# ── 매칭 ──


def _clamp_rate(value: float) -> int:
    return max(0, min(100, int(round(value))))


def _is_expired_snapshot(item: FridgeItemSnapshot | MaybeMatch | None) -> bool:
    if item is None:
        return False
    if item.status == "expired":
        return True
    return bool(item.expiry_date and item.expiry_date < date.today())


def _fridge_status_payload(item: FridgeItemSnapshot | MaybeMatch | None) -> dict[str, Any]:
    if item is None:
        return {}
    return {
        "expiry_date": item.expiry_date,
        "status": item.status,
        "is_expired": _is_expired_snapshot(item),
    }


def _pick_fridge_item(candidates: list[FridgeItemSnapshot]) -> FridgeItemSnapshot | None:
    if not candidates:
        return None

    expired = [item for item in candidates if _is_expired_snapshot(item)]
    if expired:
        return sorted(expired, key=lambda item: item.expiry_date or date.min)[0]

    with_expiry = [item for item in candidates if item.expiry_date is not None]
    if with_expiry:
        return sorted(with_expiry, key=lambda item: item.expiry_date or date.max)[0]

    return candidates[0]


def compute_match_rates(
    owned_count: int,
    maybe_owned_count: int,
    required_count: int,
) -> MatchRates:
    if required_count <= 0:
        return MatchRates(match_rate=0, display_match_rate=0)

    weighted = (owned_count + maybe_owned_count * MAYBE_OWNED_WEIGHT) / required_count * 100
    display = (owned_count + maybe_owned_count) / required_count * 100
    return MatchRates(
        match_rate=_clamp_rate(weighted),
        display_match_rate=_clamp_rate(display),
    )


def find_maybe_match(
    recipe_name: str,
    fridge_items: list[FridgeItemSnapshot],
) -> MaybeMatch | None:
    recipe = recipe_name.strip()
    if not recipe:
        return None

    best: MaybeMatch | None = None

    for item in fridge_items:
        fridge = item.fridge_name.strip()
        if not fridge:
            continue

        if recipe in fridge:
            candidate = MaybeMatch(
                fridge_ingredient_name=fridge,
                match_type="recipe_in_fridge",
                score=MAYBE_MATCH_SCORE,
                overlap_length=len(recipe),
                expiry_date=item.expiry_date,
                status=item.status,
            )
        elif fridge in recipe:
            candidate = MaybeMatch(
                fridge_ingredient_name=fridge,
                match_type="fridge_in_recipe",
                score=MAYBE_MATCH_SCORE,
                overlap_length=len(fridge),
                expiry_date=item.expiry_date,
                status=item.status,
            )
        else:
            continue

        if best is None:
            best = candidate
            continue

        if candidate.overlap_length > best.overlap_length:
            best = candidate
        elif candidate.overlap_length == best.overlap_length and candidate.match_type == "recipe_in_fridge":
            best = candidate

    return best


def ingredient_matches_refs(
    ingredient: dict[str, Any],
    refs: list[FridgeItemSnapshot],
) -> bool:
    ingredient_id = ingredient.get("ingredient_id")
    ref_ids = {ref.ingredient_id for ref in refs if ref.ingredient_id is not None}
    if ingredient_id and ingredient_id in ref_ids:
        return True
    recipe_name = ingredient.get("name") or ""
    return find_maybe_match(recipe_name, refs) is not None


def recipe_contains_banned(
    recipe_ingredients: list[dict[str, Any]],
    banned_items: list[FridgeItemSnapshot],
) -> bool:
    if not banned_items:
        return False
    return any(ingredient_matches_refs(ingredient, banned_items) for ingredient in recipe_ingredients)


def classify_fridge_match(
    recipe_ingredients: list[dict[str, Any]],
    fridge_items: list[FridgeItemSnapshot],
) -> FridgeMatchResult:
    owned_ids = {item.ingredient_id for item in fridge_items if item.ingredient_id is not None}

    owned: list[dict[str, Any]] = []
    maybe_owned: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []

    for ingredient in recipe_ingredients:
        ingredient_id = ingredient.get("ingredient_id")
        if ingredient_id and ingredient_id in owned_ids:
            matched = _pick_fridge_item([item for item in fridge_items if item.ingredient_id == ingredient_id])
            owned.append({**ingredient, **_fridge_status_payload(matched)})
            continue

        recipe_name = ingredient.get("name") or ""
        if ingredient_id and ingredient_id in BASIC_INGREDIENT_IDS:
            owned.append(ingredient)
            continue

        normalized = basic_ingredient_normalized(recipe_name)
        if normalized and normalized in BASIC_INGREDIENT_NORMALIZED_NAMES:
            owned.append(ingredient)
            continue
        # ponytail: 수식어+기본재료(뜨거운 물 등) — 오탐·범위 검토 후 재활성화
        if not ingredient_matches_refs(ingredient, fridge_items):
            missing.append(ingredient)
            continue

        maybe = find_maybe_match(recipe_name, fridge_items)
        if maybe:
            maybe_owned.append(
                {
                    **ingredient,
                    "recipe_ingredient_name": recipe_name,
                    "fridge_ingredient_name": maybe.fridge_ingredient_name,
                    "match_type": maybe.match_type,
                    "score": maybe.score,
                    **_fridge_status_payload(maybe),
                }
            )
        else:
            missing.append(ingredient)

    rates = compute_match_rates(
        owned_count=len(owned),
        maybe_owned_count=len(maybe_owned),
        required_count=len(recipe_ingredients),
    )

    return FridgeMatchResult(
        owned=owned,
        maybe_owned=maybe_owned,
        missing=missing,
        match_rate=rates.match_rate,
        display_match_rate=rates.display_match_rate,
    )


def _self_check() -> None:
    empty = classify_fridge_match([{"name": "물"}], [])
    assert len(empty.owned) == 1
    assert empty.missing == []

    assert len(classify_fridge_match([{"name": "물 1200ml"}], []).owned) == 1
    assert len(classify_fridge_match([{"name": "? 물"}], []).owned) == 1

    hot_water = classify_fridge_match([{"name": "뜨거운 물"}], [])
    assert hot_water.owned == []
    assert len(hot_water.missing) == 1

    missing_onion = classify_fridge_match([{"name": "양파"}], [])
    assert missing_onion.owned == []
    assert len(missing_onion.missing) == 1

    egg_water = classify_fridge_match([{"name": "계란물"}], [])
    assert egg_water.owned == []
    assert len(egg_water.missing) == 1

    fridge = [FridgeItemSnapshot(ingredient_id=99, fridge_name="양파")]
    mixed = classify_fridge_match(
        [{"name": "물"}, {"name": "양파", "ingredient_id": 99}],
        fridge,
    )
    assert len(mixed.owned) == 2
    assert mixed.missing == []
    assert mixed.display_match_rate == 100


if __name__ == "__main__":
    _self_check()
    print("ok")
