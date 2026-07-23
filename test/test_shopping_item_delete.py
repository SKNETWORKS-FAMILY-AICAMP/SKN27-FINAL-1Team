import importlib
from types import SimpleNamespace

from app.backend.schemas.shopping import ShoppingOwnedIngredientStockInput
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


def test_legacy_recipe_item_refs_use_the_named_list_recipe():
    service = ShoppingService(provider=FakeProvider())
    shopping_list = SimpleNamespace(
        recipe_id=7,
        recipe=SimpleNamespace(title="참치마요 주먹밥"),
    )
    item = SimpleNamespace(source_type="recipe", source_refs=[])

    assert service._item_source_refs(shopping_list, item) == [
        {
            "type": "recipe",
            "recipe_id": 7,
            "recipe_title": "참치마요 주먹밥",
        }
    ]


def test_source_recipe_list_keeps_the_available_recipe_title():
    service = ShoppingService(provider=FakeProvider())
    shopping_list = SimpleNamespace(
        recipe_id=7,
        recipe=SimpleNamespace(title="참치마요 주먹밥"),
        items=[
            SimpleNamespace(
                source_type="recipe",
                source_refs=[{"type": "recipe", "recipe_id": 7}],
            )
        ],
    )

    assert service._list_source_recipes(shopping_list) == [
        {
            "type": "recipe",
            "recipe_id": 7,
            "recipe_title": "참치마요 주먹밥",
        }
    ]


def test_complete_purchase_can_stock_an_owned_ingredient(monkeypatch):
    service = ShoppingService(provider=FakeProvider())
    db = FakeDb()
    shopping_list = SimpleNamespace(
        id=11,
        status="active",
        items=[SimpleNamespace(id=3, is_checked=False, is_purchased=False, is_deleted=False)],
    )
    stocked = []

    monkeypatch.setattr(service, "_get_user_list", lambda *_args, **_kwargs: shopping_list)
    monkeypatch.setattr(
        service,
        "_resolve_ingredient",
        lambda *_args, **_kwargs: SimpleNamespace(name="설탕", default_unit="g"),
    )
    monkeypatch.setattr(service, "get_list", lambda *_args, **_kwargs: {"id": 11})

    shopping_service_module = importlib.import_module(
        "app.backend.services.shopping_service.shopping_service"
    )
    monkeypatch.setattr(
        shopping_service_module.inventory_service,
        "add_ingredient",
        lambda _db, user_id, data: stocked.append((user_id, data)),
    )

    result = service.complete_purchase(
        db=db,
        user_id=5,
        shopping_list_id=11,
        item_ids=[],
        owned_ingredients=[
            ShoppingOwnedIngredientStockInput(
                name="백설탕",
                fridge_ingredient_name="설탕",
                ingredient_id=23,
                amount="120g",
            )
        ],
    )

    assert result["stocked_count"] == 1
    assert result["shopping_list"] == {"id": 11}
    assert len(stocked) == 1
    user_id, ingredient = stocked[0]
    assert user_id == 5
    assert ingredient.name == "설탕"
    assert ingredient.quantity == 120
    assert ingredient.unit == "g"


def test_remove_recipe_source_keeps_items_shared_with_another_source(monkeypatch):
    service = ShoppingService(provider=FakeProvider())
    db = FakeDb()
    recipe_only_item = SimpleNamespace(
        id=1,
        source_type="recipe",
        source_refs=[{"type": "recipe", "recipe_id": 7, "recipe_title": "리스샐러드"}],
        is_purchased=False,
        is_deleted=False,
    )
    shared_item = SimpleNamespace(
        id=2,
        source_type="recipe",
        source_refs=[
            {"type": "recipe", "recipe_id": 7, "recipe_title": "리스샐러드"},
            {"type": "recipe", "recipe_id": 8, "recipe_title": "체리초코케이크"},
        ],
        is_purchased=False,
        is_deleted=False,
    )
    manual_item = SimpleNamespace(
        id=3,
        source_type="manual",
        source_refs=[{"type": "manual"}],
        is_purchased=False,
        is_deleted=False,
    )
    shopping_list = SimpleNamespace(
        id=11,
        recipe_id=7,
        recipe=SimpleNamespace(title="리스샐러드"),
        status="active",
        items=[recipe_only_item, shared_item, manual_item],
    )
    monkeypatch.setattr(service, "_get_user_list", lambda *_args, **_kwargs: shopping_list)
    monkeypatch.setattr(service, "get_list", lambda *_args, **_kwargs: {"id": 11})

    result = service.remove_recipe_source(
        db=db,
        user_id=5,
        shopping_list_id=11,
        recipe_id=7,
    )

    assert result == {"id": 11}
    assert db.deleted == [recipe_only_item]
    assert shopping_list.recipe_id is None
    assert shopping_list.recipe is None
    assert shopping_list.items == [shared_item, manual_item]
    assert shared_item.source_refs == [
        {"type": "recipe", "recipe_id": 8, "recipe_title": "체리초코케이크"}
    ]
    assert manual_item.source_refs == [{"type": "manual"}]
    assert db.commit_count == 1
