import pytest

from app.backend.services.recommendation_service.fridge import (
    FridgeItemSnapshot,
    classify_fridge_match,
    compute_match_rates,
    find_maybe_match,
    recipe_contains_banned,
)
from app.backend.services.recommendation_service.recommend_config import RecipeRecommendConfig


@pytest.mark.parametrize(
    ("owned", "maybe", "required", "match_rate", "display_rate"),
    [
        (0, 0, 0, 0, 0),
        (0, 0, 2, 0, 0),
        (1, 0, 2, 50, 50),
        (1, 1, 2, 75, 100),
        (2, 0, 2, 100, 100),
        (0, 1, 2, 25, 50),
    ],
)
def test_recipe_matching_feature_match_rate_matrix(owned, maybe, required, match_rate, display_rate):
    result = compute_match_rates(owned, maybe, required)

    assert result.match_rate == match_rate
    assert result.display_match_rate == display_rate


@pytest.mark.parametrize(
    ("recipe_name", "fridge_names", "expected_name", "expected_type"),
    [
        ("green onion", ["onion", "green onion chopped"], "green onion chopped", "recipe_in_fridge"),
        ("green onion chopped", ["green onion"], "green onion", "fridge_in_recipe"),
        ("egg", ["milk", "rice"], None, None),
        ("", ["egg"], None, None),
    ],
)
def test_recipe_matching_feature_find_maybe_match_matrix(recipe_name, fridge_names, expected_name, expected_type):
    result = find_maybe_match(recipe_name, [FridgeItemSnapshot(None, name) for name in fridge_names])

    if expected_name is None:
        assert result is None
    else:
        assert result.fridge_ingredient_name == expected_name
        assert result.match_type == expected_type


@pytest.mark.parametrize(
    ("recipe_ingredients", "fridge_items", "owned_count", "maybe_count", "missing_count"),
    [
        ([{"name": "egg", "ingredient_id": 1}], [FridgeItemSnapshot(1, "egg")], 1, 0, 0),
        ([{"name": "green onion", "ingredient_id": 2}], [FridgeItemSnapshot(None, "green onion chopped")], 0, 1, 0),
        ([{"name": "soy sauce", "ingredient_id": 3}], [FridgeItemSnapshot(None, "egg")], 0, 0, 1),
        (
            [{"name": "egg", "ingredient_id": 1}, {"name": "green onion", "ingredient_id": 2}, {"name": "soy sauce", "ingredient_id": 3}],
            [FridgeItemSnapshot(1, "egg"), FridgeItemSnapshot(None, "green onion chopped")],
            1,
            1,
            1,
        ),
    ],
)
def test_recipe_matching_feature_classify_fridge_match_matrix(recipe_ingredients, fridge_items, owned_count, maybe_count, missing_count):
    result = classify_fridge_match(recipe_ingredients, fridge_items)

    assert len(result.owned) == owned_count
    assert len(result.maybe_owned) == maybe_count
    assert len(result.missing) == missing_count


@pytest.mark.parametrize(
    ("banned_items", "expected"),
    [
        ([FridgeItemSnapshot(1, "egg")], True),
        ([FridgeItemSnapshot(None, "onion")], True),
        ([FridgeItemSnapshot(None, "milk")], False),
        ([], False),
    ],
)
def test_recipe_matching_feature_banned_ingredient_matrix(banned_items, expected):
    recipe_ingredients = [{"name": "egg", "ingredient_id": 1}, {"name": "green onion", "ingredient_id": 2}]

    assert recipe_contains_banned(recipe_ingredients, banned_items) is expected


@pytest.mark.parametrize(
    ("limit", "expected_limit"),
    [(-1, 1), (0, 1), (9, 9), (999, 50)],
)
def test_recipe_recommend_config_feature_clamp_matrix(limit, expected_limit):
    config = RecipeRecommendConfig.menu_custom_preset(limit)

    assert config.limit == expected_limit
    assert config.pool_size == 100


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("fridge_consume", "fridge_consume"),
        ("menu_custom", "menu_custom"),
        ("unknown", None),
    ],
)
def test_recipe_recommend_config_feature_for_mode_matrix(mode, expected):
    config = RecipeRecommendConfig.for_mode(mode, request_limit=5)

    assert (config.mode if config else None) == expected
