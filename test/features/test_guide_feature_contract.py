import pytest
from pydantic import ValidationError

from app.backend.schemas.guide import FoodGuideSuggestionCreate, GuideDetailResponse


def test_guide_detail_contract_includes_core_guide_sections():
    guide = GuideDetailResponse.model_validate(
        {
            "code": "tofu",
            "name": "tofu",
            "storage_tips": "Keep refrigerated.",
            "prep_tips": "Drain before cooking.",
            "washing_tips": "Rinse container liquid if needed.",
            "freshness_tips": "Check smell and texture.",
        }
    )

    assert guide.storage_tips
    assert guide.prep_tips
    assert guide.washing_tips
    assert guide.freshness_tips


def test_guide_suggestion_strips_text_and_restricts_guide_type():
    suggestion = FoodGuideSuggestionCreate(
        ingredient_code=" tofu ",
        guide_type="storage",
        content="  Keep refrigerated after opening.  ",
        source_name="  user test  ",
    )

    assert suggestion.ingredient_code == "tofu"
    assert suggestion.content == "Keep refrigerated after opening."
    assert suggestion.source_name == "user test"

    with pytest.raises(ValidationError):
        FoodGuideSuggestionCreate(
            ingredient_code="tofu",
            guide_type="nutrition",
            content="Keep refrigerated after opening.",
        )
