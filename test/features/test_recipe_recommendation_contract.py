from app.backend.schemas.recipes import RecipeDetailResponse, RecipeRecommendRequest, RecipeRecommendResponse


def test_recipe_recommendation_contract_exposes_score_reason_and_missing_count():
    response = RecipeRecommendResponse.model_validate(
        {
            "mode": "fridge_consume",
            "items": [
                {
                    "recipe_id": 1,
                    "title": "tofu stew",
                    "category": "soup",
                    "difficulty": "easy",
                    "cooking_time_min": 20,
                    "serving_count": 2,
                    "main_image_url": None,
                    "match_rate": 80,
                    "display_match_rate": 75,
                    "owned_ingredient_count": 3,
                    "missing_ingredient_count": 1,
                    "expiry_score": 10,
                    "reason": "Uses expiring tofu.",
                }
            ],
            "returned_count": 1,
            "has_more": False,
            "applied_tier": "strict",
            "fallback_used": False,
            "empty_reason": "none",
        }
    )

    item = response.items[0]
    assert item.reason == "Uses expiring tofu."
    assert item.owned_ingredient_count == 3
    assert item.missing_ingredient_count == 1


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
