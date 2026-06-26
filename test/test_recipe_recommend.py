import os
import sys
from contextlib import contextmanager
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.backend.services.recommendation_service.expiry_scorer import d_day, score_expiry, urgency
from app.backend.services.recommendation_service.ownership_tier_service import ownership_tiers
from app.backend.services.recommendation_service.recommend_config import FridgeExpiryRow, RecipeRecommendConfig
from app.backend.services.recommendation_service.recommendation_service import RecommendationService


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
    assert config.mode == "menu_custom"
    assert config.limit == 5
    assert config.use_expiry_priority is False


def test_menu_custom_pool_multiplier():
    config = RecipeRecommendConfig.menu_custom_preset(5, pool_multiplier=4)

    assert config.pool_multiplier == 4
    assert config.pool_size == 20


def test_menu_custom_preset_api_filters_no_duplicate_kwargs():
    config = RecipeRecommendConfig.menu_custom_preset(
        5,
        require_any_owned=True,
        use_expiry_priority=True,
        min_display_match_rate=70,
    )

    assert config.require_any_owned is True
    assert config.use_expiry_priority is True
    assert config.min_display_match_rate == 70


def test_menu_custom_pool_multiplier_clamped():
    config = RecipeRecommendConfig.menu_custom_preset(5, pool_multiplier=99)

    assert config.pool_multiplier == RecipeRecommendConfig.POOL_MULTIPLIER_MAX
    assert config.pool_size == 5 * RecipeRecommendConfig.POOL_MULTIPLIER_MAX


def test_menu_custom_pipeline_slices_to_limit():
    service = RecommendationService()
    db = MagicMock()
    recipes = [
        SimpleNamespace(id=index, title=f"recipe-{index}", category="국/탕", difficulty="초급", cooking_time=20, serving_size=2, image_url=None)
        for index in range(1, 11)
    ]
    query_chain = MagicMock()
    query_chain.order_by.return_value.limit.return_value.all.return_value = recipes

    ingredient_rows = {
        recipe.id: [{"name": "대파", "amount": None, "ingredient_id": 1}]
        for recipe in recipes
    }

    with (
        patch(
            "app.backend.services.recommendation_service.recipe_recommend_engine.build_recipe_query",
            return_value=query_chain,
        ) as build_query,
        patch(
            "app.backend.services.recommendation_service.recipe_recommend_engine.fetch_fridge_items_with_expiry",
            return_value=[],
        ),
        patch(
            "app.backend.services.recommendation_service.recipe_recommend_engine.load_recipe_ingredients_bulk",
            return_value=ingredient_rows,
        ),
    ):
        config = RecipeRecommendConfig.menu_custom_preset(5, pool_multiplier=2)
        result = service.recommend_recipes(db, user_id=1, config=config)

    build_query.assert_called_once()
    query_chain.order_by.assert_called_once()
    query_chain.order_by.return_value.limit.assert_called_once_with(config.pool_size)
    assert result["returned_count"] == 5
    assert len(result["items"]) == 5
    assert result["has_more"] is True


def test_clamp_limit():
    assert RecipeRecommendConfig.clamp_limit(0) == RecipeRecommendConfig.LIMIT_MIN
    assert RecipeRecommendConfig.clamp_limit(100) == RecipeRecommendConfig.LIMIT_MAX
    assert RecipeRecommendConfig.clamp_limit(7) == 7


def test_d_day_uses_expiry_date():
    today = date(2026, 6, 24)
    row = _row(1, "대파", expiry_date=date(2026, 6, 23))

    assert d_day(row, today, 7) == -1


def test_d_day_fallback_from_purchased_date():
    today = date(2026, 6, 24)
    row = _row(1, "대파", purchased_date=date(2026, 6, 20))

    assert d_day(row, today, 7) == 3


def test_urgency_higher_when_closer_to_expiry():
    config = RecipeRecommendConfig.fridge_consume_preset()

    assert urgency(0, config) == 4
    assert urgency(1, config) == 3
    assert urgency(3, config) == 1
    assert urgency(4, config) == 0


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

    score_soon, expiring_soon = score_expiry(
        ownership_owned,
        fridge_by_id,
        {},
        config,
        today,
    )
    score_later, expiring_later = score_expiry(
        ownership_later,
        fridge_by_id,
        {},
        config,
        today,
    )

    assert score_soon > score_later
    assert expiring_soon == 1
    assert expiring_later == 0


def test_ownership_tiers_dedupes():
    high = RecipeRecommendConfig.menu_custom_preset(5, min_display_match_rate=70, require_any_owned=True)
    high_relaxed_only = RecipeRecommendConfig.menu_custom_preset(5, min_display_match_rate=70)
    fridge = RecipeRecommendConfig.fridge_consume_preset()
    open_only = RecipeRecommendConfig.menu_custom_preset(5)

    assert [name for name, _ in ownership_tiers(high)] == [
        "strict",
        "relaxed",
        "open",
    ]
    assert [name for name, _ in ownership_tiers(high_relaxed_only)] == [
        "strict",
        "relaxed",
    ]
    assert [name for name, _ in ownership_tiers(fridge)] == [
        "strict",
        "open",
    ]
    assert [name for name, _ in ownership_tiers(open_only)] == ["strict"]


@contextmanager
def _menu_custom_mock_pipeline(service, db, recipes, ingredient_rows, *, fridge_rows=None):
    query_chain = MagicMock()
    query_chain.order_by.return_value.limit.return_value.all.return_value = recipes

    with (
        patch(
            "app.backend.services.recommendation_service.recipe_recommend_engine.build_recipe_query",
            return_value=query_chain,
        ),
        patch(
            "app.backend.services.recommendation_service.recipe_recommend_engine.fetch_fridge_items_with_expiry",
            return_value=fridge_rows or [],
        ),
        patch(
            "app.backend.services.recommendation_service.recipe_recommend_engine.load_recipe_ingredients_bulk",
            return_value=ingredient_rows,
        ),
    ):
        yield query_chain


def test_fallback_fills_to_limit_from_relaxed_or_open():
    service = RecommendationService()
    db = MagicMock()
    recipes = [
        SimpleNamespace(
            id=index,
            title=f"recipe-{index}",
            category="국/탕",
            difficulty="초급",
            cooking_time=20,
            serving_size=2,
            image_url=None,
        )
        for index in range(1, 11)
    ]
    ingredient_rows = {
        1: [{"name": "대파", "amount": None, "ingredient_id": 1}],
        2: [{"name": "대파", "amount": None, "ingredient_id": 1}],
    }
    for index in range(3, 11):
        ingredient_rows[index] = [
            {"name": "대파", "amount": None, "ingredient_id": 1},
            {"name": "양파", "amount": None, "ingredient_id": 2},
            {"name": "당근", "amount": None, "ingredient_id": 3},
        ]

    with _menu_custom_mock_pipeline(
        service,
        db,
        recipes,
        ingredient_rows,
        fridge_rows=[_row(1, "대파")],
    ):
        config = RecipeRecommendConfig.menu_custom_preset(5, min_display_match_rate=70)
        result = service.recommend_recipes(db, user_id=1, config=config)

    assert result["returned_count"] == 5
    assert result["fallback_used"] is True
    assert result["applied_tier"] == "relaxed"
    assert result["empty_reason"] == "none"


def test_open_fallback_when_owned_requirement_blocks_all():
    service = RecommendationService()
    db = MagicMock()
    recipes = [
        SimpleNamespace(
            id=index,
            title=f"recipe-{index}",
            category="국/탕",
            difficulty="초급",
            cooking_time=20,
            serving_size=2,
            image_url=None,
        )
        for index in range(1, 6)
    ]
    ingredient_rows = {
        recipe.id: [{"name": "대파", "amount": None, "ingredient_id": 1}]
        for recipe in recipes
    }

    with _menu_custom_mock_pipeline(service, db, recipes, ingredient_rows, fridge_rows=[]):
        config = RecipeRecommendConfig.menu_custom_preset(3, require_any_owned=True)
        result = service.recommend_recipes(db, user_id=1, config=config)

    assert result["returned_count"] == 3
    assert result["applied_tier"] == "open"
    assert result["fallback_used"] is True
    assert result["empty_reason"] == "none"


def test_no_fallback_when_sql_empty():
    service = RecommendationService()
    db = MagicMock()
    query_chain = MagicMock()
    query_chain.order_by.return_value.limit.return_value.all.return_value = []

    with (
        patch(
            "app.backend.services.recommendation_service.recipe_recommend_engine.build_recipe_query",
            return_value=query_chain,
        ),
        patch(
            "app.backend.services.recommendation_service.recipe_recommend_engine.fetch_fridge_items_with_expiry",
            return_value=[],
        ),
        patch(
            "app.backend.services.recommendation_service.recipe_recommend_engine.load_recipe_ingredients_bulk",
            return_value={},
        ),
    ):
        config = RecipeRecommendConfig.menu_custom_preset(5, min_display_match_rate=70)
        result = service.recommend_recipes(db, user_id=1, config=config)

    assert result["returned_count"] == 0
    assert result["empty_reason"] == "no_sql_match"
    assert result["fallback_used"] is False


def test_no_fallback_when_exclude_exhausted():
    service = RecommendationService()
    db = MagicMock()
    recipes = [
        SimpleNamespace(
            id=index,
            title=f"recipe-{index}",
            category="국/탕",
            difficulty="초급",
            cooking_time=20,
            serving_size=2,
            image_url=None,
        )
        for index in range(1, 4)
    ]
    ingredient_rows = {
        recipe.id: [{"name": "대파", "amount": None, "ingredient_id": 1}]
        for recipe in recipes
    }

    with _menu_custom_mock_pipeline(
        service,
        db,
        recipes,
        ingredient_rows,
        fridge_rows=[_row(1, "대파")],
    ):
        config = RecipeRecommendConfig.menu_custom_preset(3, require_any_owned=True)
        result = service.recommend_recipes(
            db,
            user_id=1,
            config=config,
            exclude_recipe_ids=[1, 2, 3],
        )

    assert result["returned_count"] == 0
    assert result["empty_reason"] == "exhausted"
    assert result["fallback_used"] is False
