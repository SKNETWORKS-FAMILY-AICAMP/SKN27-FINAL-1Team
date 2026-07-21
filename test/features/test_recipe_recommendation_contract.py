from app.backend.schemas.recipes import RecipeDetailResponse, RecipeRecommendRequest
from app.backend.services.recommendation_service.recommend_config import RecipeRecommendConfig
from app.backend.services.recommendation_service.recommendation_service import (
    _filter_by_owned_preference,
)


def test_recipe_detail_contract_splits_owned_maybe_owned_and_missing_ingredients():
    detail = RecipeDetailResponse.model_validate(
        {
            "recipe_id": 1,
            "title": "egg rice",
            "category": None,
            "difficulty": None,
            "cooking_time_min": None,
            "serving_count": None,
            "main_image_url": None,
            "owned_ingredients": [{"name": "egg", "amount": "2", "ingredient_id": 1}],
            "maybe_owned_ingredients": [
                {
                    "recipe_ingredient_name": "green onion",
                    "fridge_ingredient_name": "spring onion",
                    "match_type": "fridge_in_recipe",
                    "score": 0.8,
                    "name": "green onion",
                    "amount": "1",
                    "ingredient_id": 2,
                }
            ],
            "missing_ingredients": [{"name": "soy sauce", "amount": "1 spoon", "ingredient_id": 3}],
            "match_rate": 67,
            "display_match_rate": 100,
            "steps": [{"title": "step 1", "text": "cook", "image_url": None}],
            "source_url": None,
        }
    )

    assert detail.owned_ingredients[0].name == "egg"
    assert detail.maybe_owned_ingredients[0].score == 0.8
    assert detail.missing_ingredients[0].name == "soy sauce"


def test_recipe_recommend_request_defaults_and_menu_custom_options():
    default_request = RecipeRecommendRequest()
    custom_request = RecipeRecommendRequest(mode="menu_custom", query="tofu", require_any_owned=True)

    assert default_request.mode == "fridge_consume"
    assert default_request.limit == 9
    assert custom_request.mode == "menu_custom"
    assert custom_request.query == "tofu"
    assert custom_request.require_any_owned is True


def test_require_any_owned_filters_zero_owned_before_rank():
    rows = [
        {"recipe_id": 1, "owned_ingredient_count": 0},
        {"recipe_id": 2, "owned_ingredient_count": 1},
        {"recipe_id": 3, "owned_ingredient_count": 0},
    ]

    kept = _filter_by_owned_preference(rows, RecipeRecommendConfig.fridge_consume_preset())
    assert [row["recipe_id"] for row in kept] == [2]
    assert _filter_by_owned_preference(rows, RecipeRecommendConfig()) == rows
