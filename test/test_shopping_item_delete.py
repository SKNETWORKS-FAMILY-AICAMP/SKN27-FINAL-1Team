import importlib
from types import SimpleNamespace

from app.backend.services.shopping_service.shopping_service import ShoppingService


class FakeProvider:
    provider_name = "naver"


class FakeDb:
    def __init__(self):
        self.deleted = []
        self.commit_count = 0

    def delete(self, item):
        self.deleted.append(item)

    def commit(self):
        self.commit_count += 1


def test_delete_recipe_item_keeps_hidden_tombstone(monkeypatch):
    service = ShoppingService(provider=FakeProvider())
    db = FakeDb()
    item = SimpleNamespace(
        id=3,
        shopping_list_id=11,
        source_type="recipe",
        source_refs=[{"type": "recipe", "recipe_id": 7}],
        is_checked=True,
        is_deleted=False,
    )
    monkeypatch.setattr(service, "_get_user_item", lambda *_args, **_kwargs: item)
    monkeypatch.setattr(
        service,
        "get_list",
        lambda *_args, **_kwargs: {"id": 11, "items": []},
    )

    result = service.delete_item(db=db, user_id=5, item_id=3)

    assert result == {"id": 11, "items": []}
    assert item.is_deleted is True
    assert item.is_checked is False
    assert db.deleted == []
    assert db.commit_count == 1


def test_delete_manual_item_removes_row(monkeypatch):
    service = ShoppingService(provider=FakeProvider())
    db = FakeDb()
    item = SimpleNamespace(
        id=4,
        shopping_list_id=11,
        source_type="manual",
        source_refs=[{"type": "manual"}],
        is_checked=True,
        is_deleted=False,
    )
    monkeypatch.setattr(service, "_get_user_item", lambda *_args, **_kwargs: item)
    monkeypatch.setattr(
        service,
        "get_list",
        lambda *_args, **_kwargs: {"id": 11, "items": []},
    )

    service.delete_item(db=db, user_id=5, item_id=4)

    assert db.deleted == [item]
    assert db.commit_count == 1


def test_recipe_sync_does_not_recreate_deleted_item(monkeypatch):
    service = ShoppingService(provider=FakeProvider())
    db = FakeDb()
    deleted_item = SimpleNamespace(
        ingredient_id=23,
        name="양파",
        source_type="recipe",
        source_refs=[{"type": "recipe", "recipe_id": 7}],
        is_deleted=True,
        is_purchased=False,
    )
    legacy_deleted_item = SimpleNamespace(
        ingredient_id=24,
        name="당근",
        source_type="recipe",
        source_refs=[],
        is_deleted=True,
        is_purchased=False,
    )
    shopping_list = SimpleNamespace(
        id=11,
        status="active",
        recipe_id=7,
        source="recipe",
        items=[deleted_item, legacy_deleted_item],
    )
    captured_inputs = []

    shopping_service_module = importlib.import_module(
        "app.backend.services.shopping_service.shopping_service"
    )
    monkeypatch.setattr(
        shopping_service_module.recipe_detail_service,
        "get_recipe_detail",
        lambda *_args, **_kwargs: {
            "owned_ingredients": [],
            "maybe_owned_ingredients": [],
            "missing_ingredients": [
                {"ingredient_id": 23, "name": "양파", "amount": "1개"},
                {"ingredient_id": 24, "name": "당근", "amount": "1개"},
            ],
        },
    )
    monkeypatch.setattr(
        service,
        "_build_source_ref",
        lambda *_args, **_kwargs: {"type": "recipe", "recipe_id": 7},
    )

    def capture_merge(_db, _shopping_list, raw_items, **_kwargs):
        captured_inputs.extend(raw_items)
        return False

    monkeypatch.setattr(service, "_merge_items_into_list", capture_merge)

    result = service._sync_recipe_list(db=db, user_id=5, shopping_list=shopping_list)

    assert captured_inputs == []
    assert result == {"changed": False, "owned_ingredients": []}
    assert db.commit_count == 0
