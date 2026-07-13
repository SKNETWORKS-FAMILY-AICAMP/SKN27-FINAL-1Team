from decimal import Decimal
import importlib
from types import SimpleNamespace

shopping_module = importlib.import_module("app.backend.services.shopping_service.shopping_service")
ShoppingService = shopping_module.ShoppingService


class FakeQuery:
    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return None


class FakeDb:
    def __init__(self):
        self.added = []
        self.deleted = []
        self.committed = False

    def query(self, *args, **kwargs):
        return FakeQuery()

    def add(self, item):
        self.added.append(item)

    def delete(self, item):
        self.deleted.append(item)

    def commit(self):
        self.committed = True


class FakeProvider:
    provider_name = "fake"

    def search_best_product(self, name):
        return SimpleNamespace(
            provider="fake",
            product_id=f"product-{name}",
            product_name=f"{name} 상품",
            product_link=f"https://shopping.example/{name}",
            product_image=None,
            price=1000,
            mall_name="테스트몰",
        )

    def build_product_link(self, product):
        return product.product_link


def test_shopping_service_syncs_recipe_list_with_current_fridge(monkeypatch):
    existing_missing_item = SimpleNamespace(
        id=21,
        ingredient_id=1,
        name="두부",
        required_quantity=Decimal("1"),
        unit="모",
        is_purchased=False,
    )
    shopping_list = SimpleNamespace(
        id=11,
        source="recipe",
        recipe_id=3,
        status="active",
        items=[existing_missing_item],
    )
    db = FakeDb()

    def fake_recipe_detail(*args, **kwargs):
        return {
            "owned_ingredients": [{"ingredient_id": 1, "name": "두부", "amount": "1모"}],
            "maybe_owned_ingredients": [],
            "missing_ingredients": [{"ingredient_id": 2, "name": "대파", "amount": "1대"}],
        }

    monkeypatch.setattr(shopping_module.recipe_detail_service, "get_recipe_detail", fake_recipe_detail)

    service = ShoppingService(provider=FakeProvider())
    result = service._sync_recipe_list(db, user_id=7, shopping_list=shopping_list)

    assert result["changed"] is True
    assert result["owned_ingredients"] == [{"ingredient_id": 1, "name": "두부", "amount": "1모"}]
    assert db.deleted == [existing_missing_item]
    assert len(db.added) == 1
    assert db.added[0].name == "대파"
    assert db.added[0].product_link == "https://shopping.example/대파"
    assert db.committed is True
