from types import SimpleNamespace

from app.backend.services.shopping_service.providers.base import ProductSearchResult
from app.backend.services.shopping_service.shopping_service import ShoppingService


class FakeProvider:
    provider_name = "naver"

    def search_best_product(self, keyword: str):
        return ProductSearchResult(
            provider="naver",
            product_id="p1",
            product_name=f"{keyword} 상품",
            product_link="https://example.com/p1",
            product_image="https://example.com/p1.jpg",
            price=5900,
            mall_name="테스트몰",
        )

    def build_product_link(self, product):
        return product.product_link


def test_backfills_existing_shopping_items_without_product_snapshot():
    service = ShoppingService(provider=FakeProvider())
    item = SimpleNamespace(
        name="양파",
        is_purchased=False,
        provider="naver",
        product_id=None,
        product_name=None,
        product_link=None,
        product_image=None,
        price=None,
        mall_name=None,
    )

    changed = service._backfill_missing_products(SimpleNamespace(items=[item]))

    assert changed is True
    assert item.product_name == "양파 상품"
    assert item.product_link == "https://example.com/p1"
    assert item.price == 5900
