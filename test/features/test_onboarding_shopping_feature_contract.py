from app.backend.schemas.onboarding import OnboardingRequest


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
