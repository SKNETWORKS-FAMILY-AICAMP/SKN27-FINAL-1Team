import pytest

from app.backend.services.recommendation_service.fridge import (
    FridgeItemSnapshot,
    classify_fridge_match,
    compute_match_rates,
    find_maybe_match,
    recipe_contains_banned,
)
from app.backend.services.recommendation_service.recommend_config import RecipeRecommendConfig


def test_recipe_matching_feature_counts_maybe_owned_as_half_for_score_but_full_for_display():
    rates = compute_match_rates(owned_count=1, maybe_owned_count=1, required_count=2)

    assert rates.match_rate == 75
    assert rates.display_match_rate == 100


def test_recipe_matching_feature_prefers_longest_partial_match():
    match = find_maybe_match("green onion", [FridgeItemSnapshot(None, "onion"), FridgeItemSnapshot(None, "green onion chopped")])

    assert match.fridge_ingredient_name == "green onion chopped"
    assert match.match_type == "recipe_in_fridge"


def test_recipe_matching_feature_splits_owned_maybe_and_missing_ingredients():
    result = classify_fridge_match(
        [
            {"name": "egg", "ingredient_id": 1},
            {"name": "green onion", "ingredient_id": 2},
            {"name": "soy sauce", "ingredient_id": 3},
        ],
        [FridgeItemSnapshot(1, "egg"), FridgeItemSnapshot(None, "green onion chopped")],
    )

    assert [item["name"] for item in result.owned] == ["egg"]
    assert [item["name"] for item in result.maybe_owned] == ["green onion"]
    assert [item["name"] for item in result.missing] == ["soy sauce"]
    assert result.display_match_rate == 67


def test_recipe_matching_feature_detects_banned_ingredients_by_id_or_partial_name():
    recipe_ingredients = [{"name": "egg", "ingredient_id": 1}, {"name": "green onion", "ingredient_id": 2}]

    assert recipe_contains_banned(recipe_ingredients, [FridgeItemSnapshot(1, "egg")])
    assert recipe_contains_banned(recipe_ingredients, [FridgeItemSnapshot(None, "onion")])
    assert not recipe_contains_banned(recipe_ingredients, [FridgeItemSnapshot(None, "milk")])


def test_recipe_recommend_config_feature_clamps_limits_and_pool_size():
    config = RecipeRecommendConfig.menu_custom_preset(999, query="tofu")

    assert config.limit == 50
    assert config.pool_size == 100
    assert RecipeRecommendConfig.for_mode("unknown", request_limit=9) is None
