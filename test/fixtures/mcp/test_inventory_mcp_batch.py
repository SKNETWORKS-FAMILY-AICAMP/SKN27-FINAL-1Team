from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.backend.schemas.inventory import IngredientCreate, InventoryUpdateItem
from app.backend.services.inventory_service.inventory_service import InventoryService


def test_update_input_requires_a_change_and_positive_values():
    with pytest.raises(ValidationError):
        InventoryUpdateItem(inventory_id=1)
    with pytest.raises(ValidationError):
        InventoryUpdateItem(inventory_id=1, quantity=0)

    item = InventoryUpdateItem(inventory_id=1, name="감자")
    assert item.model_fields_set == {"inventory_id", "name"}


def test_add_batch_reuses_single_item_path_without_committing(monkeypatch):
    service = InventoryService()
    db = MagicMock()
    calls = []

    def fake_add(_db, user_id, data, **kwargs):
        calls.append((user_id, data.name, kwargs))
        if data.name == "실패":
            raise ValueError("invalid")
        return {"name": data.name}

    monkeypatch.setattr(service, "add_ingredient", fake_add)
    prepared = [
        (IngredientCreate(name="감자"), ("실온", 14)),
        (IngredientCreate(name="양파"), ("냉장", 7)),
    ]

    assert service.add_ingredients_batch(db, 42, prepared) == [
        {"name": "감자"},
        {"name": "양파"},
    ]
    assert all(call[2]["commit"] is False for call in calls)
    assert all(call[2]["validate_name"] is False for call in calls)
    db.commit.assert_not_called()


def test_add_batch_stops_on_failure_without_committing(monkeypatch):
    service = InventoryService()
    db = MagicMock()

    def fake_add(_db, _user_id, data, **_kwargs):
        if data.name == "실패":
            raise ValueError("invalid")
        return {"name": data.name}

    monkeypatch.setattr(service, "add_ingredient", fake_add)
    prepared = [
        (IngredientCreate(name="감자"), ("실온", 14)),
        (IngredientCreate(name="실패"), ("냉장", 7)),
        (IngredientCreate(name="양파"), ("냉장", 7)),
    ]

    with pytest.raises(ValueError, match="invalid"):
        service.add_ingredients_batch(db, 42, prepared)
    db.commit.assert_not_called()


def test_remove_batch_uses_sorted_locked_lookup_and_never_commits(monkeypatch):
    service = InventoryService()
    db = MagicMock()
    requested = []
    rows = [
        (SimpleNamespace(id=2, status="normal"), SimpleNamespace()),
        (SimpleNamespace(id=9, status="expired"), SimpleNamespace()),
    ]

    def fake_lookup(_db, user_id, inventory_ids, *, lock=False):
        requested.append((user_id, inventory_ids, lock))
        return rows

    monkeypatch.setattr(service, "get_active_ingredients_by_ids", fake_lookup)

    assert service.remove_ingredients_batch(db, 42, [9, 2]) == [2, 9]
    assert requested == [(42, [2, 9], True)]
    assert [row[0].status for row in rows] == ["used", "used"]
    db.flush.assert_called_once_with()
    db.commit.assert_not_called()
