from datetime import date, timedelta
from types import SimpleNamespace

from app.backend.services.inventory_service.inventory_service import DEFAULT_CATEGORY, inventory_service


def test_inventory_feature_ab_expiring_vs_safe_item_status():
    ingredient = SimpleNamespace(name="tofu", category=None, default_unit="ea")

    expiring = inventory_service._map_to_response(
        SimpleNamespace(
            id=1,
            receipt_item_id=None,
            display_name="tofu",
            quantity=1,
            unit="ea",
            storage_location="fridge",
            purchased_date=date.today(),
            expiry_date=date.today() + timedelta(days=1),
            created_at=None,
        ),
        ingredient,
    )
    safe = inventory_service._map_to_response(
        SimpleNamespace(
            id=2,
            receipt_item_id=None,
            display_name="rice",
            quantity=1,
            unit="ea",
            storage_location="room",
            purchased_date=date.today(),
            expiry_date=date.today() + timedelta(days=10),
            created_at=None,
        ),
        ingredient,
    )

    assert expiring["name"] == "tofu"
    assert expiring["category"] == DEFAULT_CATEGORY
    assert expiring["d_day"] == 1
    assert expiring["is_expiring_soon"] is True
    assert expiring["status"] == "expiring"
    assert safe["is_expiring_soon"] is False
