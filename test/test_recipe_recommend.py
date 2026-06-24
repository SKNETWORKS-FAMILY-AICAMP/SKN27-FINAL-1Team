import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.backend.services.recommendation_service.recommendation_service import (
    FridgeExpiryRow,
    RecipeRecommendConfig,
    RecommendationService,
)


def _row(
    ingredient_id: int,
    fridge_name: str,
    *,
    expiry_date: date | None = None,
    purchased_date: date | None = None,
) -> FridgeExpiryRow:
    return FridgeExpiryRow(
        ingredient_id=ingredient_id,
        fridge_name=fridge_name,
        expiry_date=expiry_date,
        purchased_date=purchased_date,
    )


def test_fridge_consume_preset_flags():
    config = RecipeRecommendConfig.fridge_consume_preset()

    assert config.require_any_owned is True
    assert config.include_maybe_owned is True
    assert config.use_expiry_priority is True
    assert config.min_display_match_rate is None
    assert config.limit == RecipeRecommendConfig.FRIDGE_CONSUME_LIMIT


def test_for_mode_fridge_consume_ignores_request_limit():
    config = RecipeRecommendConfig.for_mode("fridge_consume", request_limit=20)

    assert config is not None
    assert config.limit == RecipeRecommendConfig.FRIDGE_CONSUME_LIMIT


def test_for_mode_menu_custom_uses_request_limit():
    config = RecipeRecommendConfig.for_mode("menu_custom", request_limit=5)

    assert config is not None
    assert config.limit == 5
    assert config.use_expiry_priority is False


def test_clamp_limit():
    assert RecipeRecommendConfig.clamp_limit(0) == RecipeRecommendConfig.LIMIT_MIN
    assert RecipeRecommendConfig.clamp_limit(100) == RecipeRecommendConfig.LIMIT_MAX
    assert RecipeRecommendConfig.clamp_limit(7) == 7


def test_d_day_uses_expiry_date():
    today = date(2026, 6, 24)
    row = _row(1, "대파", expiry_date=date(2026, 6, 23))

    assert RecommendationService._d_day(row, today, 7) == -1


def test_d_day_fallback_from_purchased_date():
    today = date(2026, 6, 24)
    row = _row(1, "대파", purchased_date=date(2026, 6, 20))

    assert RecommendationService._d_day(row, today, 7) == 3


def test_urgency_higher_when_closer_to_expiry():
    config = RecipeRecommendConfig.fridge_consume_preset()

    assert RecommendationService._urgency(0, config) == 4
    assert RecommendationService._urgency(1, config) == 3
    assert RecommendationService._urgency(3, config) == 1
    assert RecommendationService._urgency(4, config) == 0


def test_score_expiry_prioritizes_sooner_items():
    service = RecommendationService()
    config = RecipeRecommendConfig.fridge_consume_preset()
    today = date(2026, 6, 24)

    ownership_owned = type(
        "Ownership",
        (),
        {
            "owned": [{"ingredient_id": 1}],
            "maybe_owned": [],
        },
    )()
    ownership_later = type(
        "Ownership",
        (),
        {
            "owned": [{"ingredient_id": 2}],
            "maybe_owned": [],
        },
    )()

    fridge_by_id = {
        1: _row(1, "대파", expiry_date=today),
        2: _row(2, "양파", expiry_date=today + timedelta(days=10)),
    }

    score_soon, expiring_soon = service._score_expiry(
        ownership_owned,
        fridge_by_id,
        {},
        config,
        today,
    )
    score_later, expiring_later = service._score_expiry(
        ownership_later,
        fridge_by_id,
        {},
        config,
        today,
    )

    assert score_soon > score_later
    assert expiring_soon == 1
    assert expiring_later == 0


def test_rank_and_slice_returns_nine_and_has_more():
    candidates = [{"recipe_id": index} for index in range(1, 16)]

    items, has_more = RecommendationService._rank_and_slice(candidates, [1, 2], 9)

    assert len(items) == 9
    assert items[0]["recipe_id"] == 3
    assert has_more is True


def test_rank_and_slice_has_more_false_when_exhausted():
    candidates = [{"recipe_id": index} for index in range(1, 6)]

    items, has_more = RecommendationService._rank_and_slice(candidates, [], 9)

    assert len(items) == 5
    assert has_more is False
