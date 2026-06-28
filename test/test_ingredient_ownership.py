import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.backend.services.recommendation_service.fridge_ingredient_match import (
    FridgeItemSnapshot,
    classify_fridge_match,
    compute_match_rates,
    find_maybe_match,
    ingredient_matches_refs,
    recipe_contains_banned,
)


def _recipe(name: str, ingredient_id: int | None = None, amount: str | None = None) -> dict:
    return {"name": name, "ingredient_id": ingredient_id, "amount": amount}


def _fridge(ingredient_id: int, fridge_name: str) -> FridgeItemSnapshot:
    return FridgeItemSnapshot(ingredient_id=ingredient_id, fridge_name=fridge_name)


def test_id_match_classified_as_owned():
    recipes = [_recipe("계란", ingredient_id=10)]
    fridge = [_fridge(10, "계란")]

    result = classify_fridge_match(recipes, fridge)

    assert len(result.owned) == 1
    assert len(result.maybe_owned) == 0
    assert len(result.missing) == 0


def test_recipe_name_in_fridge_name_is_maybe_owned():
    recipes = [_recipe("대파", ingredient_id=20)]
    fridge = [_fridge(99, "흰대파")]

    result = classify_fridge_match(recipes, fridge)

    assert len(result.owned) == 0
    assert len(result.maybe_owned) == 1
    assert result.maybe_owned[0]["match_type"] == "recipe_in_fridge"
    assert result.maybe_owned[0]["recipe_ingredient_name"] == "대파"
    assert result.maybe_owned[0]["fridge_ingredient_name"] == "흰대파"
    assert result.maybe_owned[0]["score"] == 1.0


def test_fridge_name_in_recipe_name_is_maybe_owned():
    recipes = [_recipe("다진마늘", ingredient_id=30)]
    fridge = [_fridge(88, "마늘")]

    result = classify_fridge_match(recipes, fridge)

    assert len(result.maybe_owned) == 1
    assert result.maybe_owned[0]["match_type"] == "fridge_in_recipe"


def test_unrelated_names_are_missing():
    recipes = [_recipe("참기름", ingredient_id=40)]
    fridge = [_fridge(77, "시금치")]

    result = classify_fridge_match(recipes, fridge)

    assert len(result.missing) == 1
    assert len(result.maybe_owned) == 0


def test_match_rates_with_owned_and_maybe():
    rates = compute_match_rates(owned_count=2, maybe_owned_count=1, required_count=4)

    assert rates.match_rate == 62
    assert rates.display_match_rate == 75


def test_empty_recipe_name_is_missing():
    recipes = [_recipe("", ingredient_id=50)]
    fridge = [_fridge(66, "대파")]

    result = classify_fridge_match(recipes, fridge)

    assert len(result.missing) == 1
    assert len(result.maybe_owned) == 0


def test_empty_fridge_list_all_missing():
    recipes = [_recipe("대파", ingredient_id=20)]

    result = classify_fridge_match(recipes, [])

    assert len(result.missing) == 1
    assert result.match_rate == 0
    assert result.display_match_rate == 0


def test_find_maybe_match_prefers_longer_overlap():
    fridge = [
        _fridge(1, "파"),
        _fridge(2, "흰대파"),
    ]

    match = find_maybe_match("대파", fridge)

    assert match is not None
    assert match.fridge_ingredient_name == "흰대파"
    assert match.match_type == "recipe_in_fridge"


def test_classify_empty_recipe_list_rates_zero():
    result = classify_fridge_match([], [_fridge(1, "대파")])

    assert result.match_rate == 0
    assert result.display_match_rate == 0


def test_ingredient_matches_refs_by_id():
    ingredient = _recipe("대파", ingredient_id=10)
    refs = [_fridge(10, "대파")]

    assert ingredient_matches_refs(ingredient, refs) is True


def test_ingredient_matches_refs_by_substring_name():
    ingredient = _recipe("흰대파", ingredient_id=20)
    refs = [FridgeItemSnapshot(ingredient_id=None, fridge_name="대파")]

    assert ingredient_matches_refs(ingredient, refs) is True


def test_ingredient_matches_refs_unrelated():
    ingredient = _recipe("참기름", ingredient_id=40)
    refs = [FridgeItemSnapshot(ingredient_id=None, fridge_name="대파")]

    assert ingredient_matches_refs(ingredient, refs) is False


def test_recipe_contains_banned():
    ingredients = [_recipe("땅콩", ingredient_id=99)]
    banned = [FridgeItemSnapshot(ingredient_id=None, fridge_name="땅콩")]

    assert recipe_contains_banned(ingredients, banned) is True
    assert recipe_contains_banned(ingredients, []) is False
