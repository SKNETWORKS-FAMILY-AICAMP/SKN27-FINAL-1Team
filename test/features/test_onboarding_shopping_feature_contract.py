from app.backend.api.shopping import shopping_api
from app.backend.schemas.onboarding import OnboardingRequest
from app.backend.schemas.shopping import ShoppingCompareRequest


def test_onboarding_feature_preserves_food_preferences_and_alert_consent():
    request = OnboardingRequest(
        disliked_ingredients=["cilantro"],
        allergy=["peanut"],
        preferred_ingredients=["tofu"],
        is_alert_allowed=False,
    )

    assert request.disliked_ingredients == ["cilantro"]
    assert request.allergy == ["peanut"]
    assert request.preferred_ingredients == ["tofu"]
    assert request.is_alert_allowed is False


def test_shopping_feature_compare_totals_missing_ingredients():
    response = shopping_api.compare_shopping_prices(
        ShoppingCompareRequest(missing_ingredients=["tofu", "egg"]),
        current_user_id=7,
    )

    assert response["total_price"] == 6000
    assert response["recommended_market"]
    assert [item["name"] for item in response["market_prices"]] == ["tofu", "egg"]
