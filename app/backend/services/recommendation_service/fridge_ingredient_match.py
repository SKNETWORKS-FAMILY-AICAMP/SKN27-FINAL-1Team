from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.backend.services.recommendation_service.recommend_config import (
    BASIC_INGREDIENT_IDS,
    BASIC_INGREDIENT_NORMALIZED_NAMES,
    basic_ingredient_normalized,
)

MAYBE_OWNED_WEIGHT = 0.5
MAYBE_MATCH_SCORE = 1.0

MatchType = Literal["recipe_in_fridge", "fridge_in_recipe"]


@dataclass(frozen=True)
class FridgeItemSnapshot:
    ingredient_id: int | None
    fridge_name: str


@dataclass(frozen=True)
class MaybeMatch:
    fridge_ingredient_name: str
    match_type: MatchType
    score: float
    overlap_length: int


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


def _clamp_rate(value: float) -> int:
    return max(0, min(100, int(round(value))))


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
            )
        elif fridge in recipe:
            candidate = MaybeMatch(
                fridge_ingredient_name=fridge,
                match_type="fridge_in_recipe",
                score=MAYBE_MATCH_SCORE,
                overlap_length=len(fridge),
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
            owned.append(ingredient)
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
        # cleaned = text before normalize in _basic_ingredient_normalized
        # if any(
        #     len(parts := cleaned.split()) >= 2 and parts[-1] == basic_name
        #     for basic_name in BASIC_INGREDIENT_NORMALIZED_NAMES
        # ):
        #     owned.append(ingredient)
        #     continue
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
