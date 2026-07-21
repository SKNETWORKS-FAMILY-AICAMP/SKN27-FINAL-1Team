"""_format_amount must keep integer trailing zeros (200g, not 2g)."""

from decimal import Decimal

from app.backend.services.recommendation_service.recipe_detail_service import recipe_detail_service


def test_format_amount_keeps_integer_trailing_zeros():
    fmt = recipe_detail_service._format_amount
    assert fmt(Decimal("200"), "g") == "200g"
    assert fmt(Decimal("60"), "g") == "60g"
    assert fmt(Decimal("40"), "g") == "40g"
    assert fmt(Decimal("30"), "g") == "30g"
    assert fmt(Decimal("25"), "g") == "25g"
    assert fmt(Decimal("15"), "ml") == "15ml"


def test_format_amount_trims_fractional_trailing_zeros_only():
    fmt = recipe_detail_service._format_amount
    assert fmt(Decimal("200.00"), "g") == "200g"
    assert fmt(Decimal("0.80"), "g") == "0.8g"
    assert fmt(Decimal("0.1"), "g") == "0.1g"
    assert fmt(15.0, "ml") == "15ml"
