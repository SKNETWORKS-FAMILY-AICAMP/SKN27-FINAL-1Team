import os
import sys
from contextlib import contextmanager
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.backend.services.recommendation_service.fridge_ingredient_match import FridgeItemSnapshot
from app.backend.services.recommendation_service.fridge_loader import FridgeExpiryRow
from app.backend.services.recommendation_service.hard_filter import UserHardFilterContext
from app.backend.services.recommendation_service.recommend_config import RecipeRecommendConfig
from app.backend.services.recommendation_service.recommendation_service import RecommendationService


def _recipe(index: int) -> SimpleNamespace:
    return SimpleNamespace(
        id=index,
        title=f"recipe-{index}",
        category="국/탕",
        difficulty="초급",
        cooking_time=20,
        serving_size=2,
        image_url=None,
    )


def test_fridge_consume_preset_flags():
    config = RecipeRecommendConfig.fridge_consume_preset()

    assert config.mode == "fridge_consume"
    assert config.limit == RecipeRecommendConfig.FRIDGE_CONSUME_LIMIT
    assert config.pool_multiplier == 10
    assert config.pool_size == 90
    assert config.require_any_owned is True
    assert config.use_expiry_priority is True

def test_for_mode_fridge_consume_ignores_request_limit():
    config = RecipeRecommendConfig.for_mode("fridge_consume", request_limit=20)

    assert config is not None
    assert config.limit == RecipeRecommendConfig.FRIDGE_CONSUME_LIMIT


def test_for_mode_menu_custom_uses_request_limit():
    config = RecipeRecommendConfig.for_mode("menu_custom", request_limit=5)

    assert config is not None
    assert config.mode == "menu_custom"
    assert config.limit == 5


def test_menu_custom_pool_multiplier():
    config = RecipeRecommendConfig.menu_custom_preset(5, pool_multiplier=4)

    assert config.pool_multiplier == 4
    assert config.pool_size == 20


def test_menu_custom_preset_search_filters():
    config = RecipeRecommendConfig.menu_custom_preset(
        5,
        query="김치",
        category="찌개",
        difficulty="초급",
        cooking_time_label="30분이내",
    )

    assert config.query == "김치"
    assert config.category == "찌개"
    assert config.difficulty == "초급"
    assert config.cooking_time_label == "30분이내"


def test_menu_custom_preset_preference_filters():
    config = RecipeRecommendConfig.menu_custom_preset(
        5,
        min_display_match_rate=70,
        require_any_owned=True,
        use_expiry_priority=True,
    )

    assert config.min_display_match_rate == 70
    assert config.require_any_owned is True
    assert config.use_expiry_priority is True


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
    query_chain.order_by.return_value.all.return_value = recipes

    ingredient_rows = {
        recipe.id: [{"name": "대파", "amount": None, "ingredient_id": 1}]
        for recipe in recipes
    }

    with (
        patch(
            "app.backend.services.recommendation_service.recommendation_service.build_recipe_query",
            return_value=query_chain,
        ) as build_query,
        patch(
            "app.backend.services.recommendation_service.recommendation_service.load_recipe_ingredients_bulk",
            return_value=ingredient_rows,
        ),
        patch(
            "app.backend.services.recommendation_service.recommendation_service.fetch_review_rank_scores",
            return_value=_default_rank_scores(recipes),
        ),
    ):
        config = RecipeRecommendConfig.menu_custom_preset(5, pool_multiplier=2)
        result = service.recommend_recipes(db, user_id=1, config=config)

    build_query.assert_called_once()
    query_chain.order_by.assert_called_once()
    query_chain.order_by.return_value.all.assert_called_once()
    assert result["returned_count"] == 5
    assert len(result["items"]) == 5
    assert result["has_more"] is True
    assert result["items"][0]["recipe_id"] == 10


def test_clamp_limit():
    assert RecipeRecommendConfig.clamp_limit(0) == RecipeRecommendConfig.LIMIT_MIN
    assert RecipeRecommendConfig.clamp_limit(100) == RecipeRecommendConfig.LIMIT_MAX
    assert RecipeRecommendConfig.clamp_limit(7) == 7


def _default_rank_scores(recipes) -> dict[int, float]:
    return {recipe.id: 50.0 for recipe in recipes}


@contextmanager
def _menu_custom_mock_pipeline(service, db, recipes, ingredient_rows, *, fridge_items=None, expiry_rows=None, rank_scores=None):
    query_chain = MagicMock()
    query_chain.order_by.return_value.all.return_value = recipes
    fridge_items = fridge_items or []
    expiry_rows = expiry_rows or []
    rank_scores = rank_scores if rank_scores is not None else _default_rank_scores(recipes)

    with (
        patch(
            "app.backend.services.recommendation_service.recommendation_service.build_recipe_query",
            return_value=query_chain,
        ),
        patch(
            "app.backend.services.recommendation_service.recommendation_service.load_recipe_ingredients_bulk",
            return_value=ingredient_rows,
        ),
        patch(
            "app.backend.services.recommendation_service.recommendation_service.fetch_fridge_snapshots",
            return_value=fridge_items,
        ),
        patch(
            "app.backend.services.recommendation_service.recommendation_service.fetch_fridge_expiry_rows",
            return_value=expiry_rows,
        ),
        patch(
            "app.backend.services.recommendation_service.recommendation_service.fetch_review_rank_scores",
            return_value=rank_scores,
        ),
    ):
        yield query_chain

def test_pipeline_pool_cap_after_banned_filter():
    """banned 1건 제외 후 pool cap → limit slice."""
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
        for index in range(1, 8)
    ]
    ingredient_rows = {
        1: [{"name": "땅콩", "amount": None, "ingredient_id": 99}],
        **{
            index: [{"name": "대파", "amount": None, "ingredient_id": 1}]
            for index in range(2, 8)
        },
    }

    with (
        _menu_custom_mock_pipeline(service, db, recipes, ingredient_rows),
        patch(
            "app.backend.services.recommendation_service.recommendation_service.load_hard_filter_context",
            return_value=UserHardFilterContext(
                banned_items=(FridgeItemSnapshot(ingredient_id=None, fridge_name="땅콩"),),
            ),
        ),
    ):
        config = RecipeRecommendConfig.menu_custom_preset(3, pool_multiplier=2)
        result = service.recommend_recipes(db, user_id=1, config=config)

    assert result["returned_count"] == 3
    assert result["has_more"] is True
    assert all(item["recipe_id"] != 1 for item in result["items"])


def test_no_results_when_sql_empty():
    service = RecommendationService()
    db = MagicMock()
    query_chain = MagicMock()
    query_chain.order_by.return_value.all.return_value = []

    with (
        patch(
            "app.backend.services.recommendation_service.recommendation_service.build_recipe_query",
            return_value=query_chain,
        ),
        patch(
            "app.backend.services.recommendation_service.recommendation_service.load_recipe_ingredients_bulk",
            return_value={},
        ),
    ):
        config = RecipeRecommendConfig.menu_custom_preset(5)
        result = service.recommend_recipes(db, user_id=1, config=config)

    assert result["returned_count"] == 0
    assert result["empty_reason"] == "no_sql_match"


def test_hard_filter_excludes_before_eval():
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
    query_chain = MagicMock()
    query_chain.order_by.return_value.all.return_value = recipes
    ingredient_rows = {
        recipe.id: [{"name": "대파", "amount": None, "ingredient_id": 1}]
        for recipe in recipes
    }

    with (
        patch(
            "app.backend.services.recommendation_service.recommendation_service.build_recipe_query",
            return_value=query_chain,
        ),
        patch(
            "app.backend.services.recommendation_service.recommendation_service.load_recipe_ingredients_bulk",
            return_value=ingredient_rows,
        ) as load_bulk,
        patch(
            "app.backend.services.recommendation_service.recommendation_service.fetch_review_rank_scores",
            return_value=_default_rank_scores(recipes),
        ),
    ):
        config = RecipeRecommendConfig.menu_custom_preset(3)
        service.recommend_recipes(
            db,
            user_id=1,
            config=config,
            exclude_recipe_ids=[1, 2, 3],
        )

    load_bulk.assert_called_once()
    loaded_ids = load_bulk.call_args[0][1]
    assert loaded_ids == [4, 5]


def test_hard_filter_excludes_recipe_with_banned_ingredient():
    service = RecommendationService()
    db = MagicMock()
    recipes = [
        SimpleNamespace(
            id=1,
            title="recipe-1",
            category="국/탕",
            difficulty="초급",
            cooking_time=20,
            serving_size=2,
            image_url=None,
        )
    ]
    ingredient_rows = {1: [{"name": "땅콩", "amount": None, "ingredient_id": 99}]}

    with (
        _menu_custom_mock_pipeline(service, db, recipes, ingredient_rows),
        patch(
            "app.backend.services.recommendation_service.recommendation_service.load_hard_filter_context",
            return_value=UserHardFilterContext(
                banned_items=(FridgeItemSnapshot(ingredient_id=None, fridge_name="땅콩"),),
            ),
        ),
    ):
        config = RecipeRecommendConfig.menu_custom_preset(3)
        result = service.recommend_recipes(db, user_id=1, config=config)

    assert result["returned_count"] == 0
    assert result["empty_reason"] == "no_scorable_recipes"


def test_hard_filter_id_match_excludes():
    service = RecommendationService()
    db = MagicMock()
    recipes = [
        SimpleNamespace(
            id=1,
            title="recipe-1",
            category="국/탕",
            difficulty="초급",
            cooking_time=20,
            serving_size=2,
            image_url=None,
        )
    ]
    ingredient_rows = {1: [{"name": "대파", "amount": None, "ingredient_id": 5}]}

    with (
        _menu_custom_mock_pipeline(service, db, recipes, ingredient_rows),
        patch(
            "app.backend.services.recommendation_service.recommendation_service.load_hard_filter_context",
            return_value=UserHardFilterContext(
                banned_items=(FridgeItemSnapshot(ingredient_id=5, fridge_name="대파"),),
            ),
        ),
    ):
        config = RecipeRecommendConfig.menu_custom_preset(3)
        result = service.recommend_recipes(db, user_id=1, config=config)

    assert result["returned_count"] == 0
    assert result["empty_reason"] == "no_scorable_recipes"


def test_exclude_exhausted_returns_no_sql_match():
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

    with _menu_custom_mock_pipeline(service, db, recipes, ingredient_rows):
        config = RecipeRecommendConfig.menu_custom_preset(3)
        result = service.recommend_recipes(
            db,
            user_id=1,
            config=config,
            exclude_recipe_ids=[1, 2, 3],
        )

    assert result["returned_count"] == 0
    assert result["empty_reason"] == "no_sql_match"


def test_min_display_match_rate_excludes_low_match_recipes():
    service = RecommendationService()
    db = MagicMock()
    recipes = [_recipe(1), _recipe(2)]
    ingredient_rows = {
        1: [
            {"name": "대파", "amount": None, "ingredient_id": 1},
            {"name": "양파", "amount": None, "ingredient_id": 2},
        ],
        2: [{"name": "대파", "amount": None, "ingredient_id": 1}],
    }
    fridge_items = [
        FridgeItemSnapshot(ingredient_id=1, fridge_name="대파"),
    ]

    with _menu_custom_mock_pipeline(
        service, db, recipes, ingredient_rows, fridge_items=fridge_items
    ):
        config = RecipeRecommendConfig.menu_custom_preset(1, min_display_match_rate=70)
        result = service.recommend_recipes(db, user_id=1, config=config)

    assert result["returned_count"] == 1
    assert result["items"][0]["recipe_id"] == 2
    assert result["items"][0]["display_match_rate"] == 100
    assert result["applied_tier"] == "strict"
    assert result["fallback_used"] is False


def test_require_any_owned_excludes_zero_owned():
    service = RecommendationService()
    db = MagicMock()
    recipes = [_recipe(1)]
    ingredient_rows = {1: [{"name": "소고기", "amount": None, "ingredient_id": 99}]}

    with _menu_custom_mock_pipeline(service, db, recipes, ingredient_rows, fridge_items=[]):
        config = RecipeRecommendConfig.menu_custom_preset(3, require_any_owned=True)
        result = service.recommend_recipes(db, user_id=1, config=config)

    assert result["returned_count"] == 1
    assert result["fallback_used"] is True
    assert result["applied_tier"] == "open"


def test_tier_fallback_relaxes_min_display_match_rate():
    service = RecommendationService()
    db = MagicMock()
    recipes = [_recipe(1)]
    ingredient_rows = {
        1: [
            {"name": "대파", "amount": None, "ingredient_id": 1},
            {"name": "양파", "amount": None, "ingredient_id": 2},
        ],
    }
    fridge_items = [FridgeItemSnapshot(ingredient_id=1, fridge_name="대파")]

    with _menu_custom_mock_pipeline(
        service, db, recipes, ingredient_rows, fridge_items=fridge_items
    ):
        config = RecipeRecommendConfig.menu_custom_preset(3, min_display_match_rate=70)
        result = service.recommend_recipes(db, user_id=1, config=config)

    assert result["returned_count"] == 1
    assert result["fallback_used"] is True
    assert result["applied_tier"] == "relaxed"
    assert result["items"][0]["display_match_rate"] == 50


def test_expiry_priority_ranks_expiring_recipe_first():
    service = RecommendationService()
    db = MagicMock()
    today = date.today()
    recipes = [_recipe(1), _recipe(2)]
    ingredient_rows = {
        1: [{"name": "대파", "amount": None, "ingredient_id": 1}],
        2: [{"name": "양파", "amount": None, "ingredient_id": 2}],
    }
    fridge_items = [
        FridgeItemSnapshot(ingredient_id=1, fridge_name="대파"),
        FridgeItemSnapshot(ingredient_id=2, fridge_name="양파"),
    ]
    expiry_rows = [
        FridgeExpiryRow(1, "대파", today + timedelta(days=10), None),
        FridgeExpiryRow(2, "양파", today + timedelta(days=1), None),
    ]

    with (
        _menu_custom_mock_pipeline(
            service,
            db,
            recipes,
            ingredient_rows,
            fridge_items=fridge_items,
            expiry_rows=expiry_rows,
        ),
        patch(
            "app.backend.services.recommendation_service.recommendation_service.date"
        ) as mock_date,
    ):
        mock_date.today.return_value = today
        config = RecipeRecommendConfig.menu_custom_preset(2, use_expiry_priority=True)
        result = service.recommend_recipes(db, user_id=1, config=config)

    assert result["returned_count"] == 2
    assert result["items"][0]["recipe_id"] == 2
    assert result["items"][0]["expiry_score"] > result["items"][1]["expiry_score"]


def test_response_includes_scoring_fields():
    service = RecommendationService()
    db = MagicMock()
    recipes = [_recipe(1)]
    ingredient_rows = {1: [{"name": "대파", "amount": None, "ingredient_id": 1}]}
    fridge_items = [FridgeItemSnapshot(ingredient_id=1, fridge_name="대파")]

    with _menu_custom_mock_pipeline(
        service, db, recipes, ingredient_rows, fridge_items=fridge_items
    ):
        result = service.recommend_recipes(
            db, user_id=1, config=RecipeRecommendConfig.menu_custom_preset(1)
        )

    item = result["items"][0]
    assert "missing_ingredient_count" in item
    assert "display_match_rate" in item
    assert item["display_match_rate"] == 100


def test_zero_rank_score_allowed_when_min_is_zero():
    service = RecommendationService()
    db = MagicMock()
    recipes = [_recipe(1), _recipe(2)]
    ingredient_rows = {
        1: [{"name": "대파", "amount": None, "ingredient_id": 1}],
        2: [{"name": "대파", "amount": None, "ingredient_id": 1}],
    }

    with _menu_custom_mock_pipeline(
        service,
        db,
        recipes,
        ingredient_rows,
        rank_scores={1: 0.0, 2: 50.0},
    ):
        result = service.recommend_recipes(
            db, user_id=1, config=RecipeRecommendConfig.menu_custom_preset(3)
        )

    assert result["returned_count"] == 2
    assert result["items"][0]["recipe_id"] == 2


def test_negative_rank_score_filtered_out():
    service = RecommendationService()
    db = MagicMock()
    recipes = [_recipe(1)]
    ingredient_rows = {1: [{"name": "대파", "amount": None, "ingredient_id": 1}]}

    with _menu_custom_mock_pipeline(
        service,
        db,
        recipes,
        ingredient_rows,
        rank_scores={1: -1.0},
    ):
        result = service.recommend_recipes(
            db, user_id=1, config=RecipeRecommendConfig.menu_custom_preset(3)
        )

    assert result["returned_count"] == 0
    assert result["empty_reason"] == "no_scorable_recipes"


def test_review_rank_score_sorts_higher_first():
    service = RecommendationService()
    db = MagicMock()
    recipes = [_recipe(1), _recipe(2)]
    ingredient_rows = {
        1: [{"name": "대파", "amount": None, "ingredient_id": 1}],
        2: [{"name": "대파", "amount": None, "ingredient_id": 1}],
    }

    with _menu_custom_mock_pipeline(
        service,
        db,
        recipes,
        ingredient_rows,
        rank_scores={1: 90.0, 2: 20.0},
    ):
        result = service.recommend_recipes(
            db, user_id=1, config=RecipeRecommendConfig.menu_custom_preset(2)
        )

    assert result["returned_count"] == 2
    assert result["items"][0]["recipe_id"] == 1
    assert result["items"][1]["recipe_id"] == 2
