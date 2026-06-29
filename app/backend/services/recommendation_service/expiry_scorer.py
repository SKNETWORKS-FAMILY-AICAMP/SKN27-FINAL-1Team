"""유통기한 우선 점수."""

from __future__ import annotations

from datetime import date, timedelta

from app.backend.services.recommendation_service.fridge_ingredient_match import FridgeMatchResult
from app.backend.services.recommendation_service.recommend_config import FridgeExpiryRow, RecipeRecommendConfig

DEFAULT_EXPIRY_FALLBACK_DAYS = 7


def d_day(row: FridgeExpiryRow, today: date, fallback_days: int = DEFAULT_EXPIRY_FALLBACK_DAYS) -> int:
    target = row.expiry_date
    if target is None and row.purchased_date is not None:
        target = row.purchased_date + timedelta(days=fallback_days)
    if target is None:
        return 999
    return (target - today).days


def urgency(d_day_value: int, config: RecipeRecommendConfig) -> int:
    if d_day_value > config.expiring_soon_days:
        return 0
    return max(0, config.urgency_base - d_day_value)


def score_expiry(
    fridge_match: FridgeMatchResult,
    fridge_by_id: dict[int, FridgeExpiryRow],
    fridge_by_name: dict[str, FridgeExpiryRow],
    config: RecipeRecommendConfig,
    today: date,
) -> tuple[int, int]:
    if not config.use_expiry_priority:
        return 0, 0

    matched_rows: list[FridgeExpiryRow] = []
    seen_ids: set[int] = set()

    for ingredient in fridge_match.owned:
        ingredient_id = ingredient.get("ingredient_id")
        if ingredient_id and ingredient_id in fridge_by_id and ingredient_id not in seen_ids:
            matched_rows.append(fridge_by_id[ingredient_id])
            seen_ids.add(ingredient_id)

    if config.include_maybe_owned:
        for ingredient in fridge_match.maybe_owned:
            fridge_name = (ingredient.get("fridge_ingredient_name") or "").strip()
            row = fridge_by_name.get(fridge_name)
            if row and row.ingredient_id not in seen_ids:
                matched_rows.append(row)
                seen_ids.add(row.ingredient_id)

    total_urgency = 0
    expiring_count = 0
    for row in matched_rows:
        d_day_value = d_day(row, today)
        total_urgency += urgency(d_day_value, config)
        if d_day_value <= config.expiring_soon_days:
            expiring_count += 1

    score = total_urgency + config.expiring_ingredient_bonus * expiring_count
    return score, expiring_count


def build_reason(expiring_count: int, display_match_rate: int) -> str | None:
    if expiring_count > 0:
        return f"임박 재료 {expiring_count}개 활용"
    if display_match_rate >= 80:
        return f"보유 재료 {display_match_rate}%로 활용하기 좋아요"
    return None
