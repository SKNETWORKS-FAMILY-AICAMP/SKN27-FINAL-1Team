from app.backend.services.shopping_service.providers import naver_search
from app.backend.services.shopping_service.providers.naver_search import NaverShoppingProvider


def product_item(**extra):
    data = {
        "title": "국산 두부 1모",
        "link": "https://shopping.example/products/100",
        "image": "https://shopping.example/products/100.jpg",
        "lprice": "5900",
        "mallName": "네이버쇼핑",
        "productId": "100",
        "productType": "1",
        "brand": "",
        "maker": "",
        "category1": "식품",
        "category2": "가공식품",
        "category3": "두부",
        "category4": "",
    }
    data.update(extra)
    return data


class FakeResponse:
    def __init__(self, items):
        self._items = items

    def raise_for_status(self):
        return None

    def json(self):
        return {"items": self._items}


class FakeClient:
    def __init__(self, calls, items):
        self.calls = calls
        self.items = items

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def get(self, url, *, params, headers):
        self.calls["url"] = url
        self.calls["params"] = params
        self.calls["headers"] = headers
        return FakeResponse(self.items)


def test_provider_requests_multiple_candidates_and_selects_first_recommendable(monkeypatch):
    calls = {}
    items = [
        product_item(title="강아지 두부 간식", productId="pet"),
        product_item(title="수입 두부 장난감", productId="toy", category1="반려동물"),
        product_item(title="<b>국산</b> 두부 1모", productId="good", lprice="3900"),
    ]

    def fake_client(timeout):
        calls["timeout"] = timeout
        return FakeClient(calls, items)

    monkeypatch.setattr(naver_search.httpx, "Client", fake_client)

    provider = NaverShoppingProvider(
        client_id="client-id",
        client_secret="client-secret",
        api_url="https://openapi.example/shop.json",
        display=10,
        sort="asc",
        exclude="used:rental:cbshop",
        timeout_seconds=3,
    )

    result = provider.search_best_product("두부")

    assert result.product_id == "good"
    assert result.product_name == "국산 두부 1모"
    assert result.price == 3900
    assert calls["timeout"] == 3
    assert calls["params"] == {
        "query": "두부",
        "display": 10,
        "start": 1,
        "sort": "asc",
        "exclude": "used:rental:cbshop",
    }
    assert calls["headers"]["X-Naver-Client-Id"] == "client-id"


def test_provider_config_normalizes_display_and_sort():
    high_display = NaverShoppingProvider(
        client_id="id",
        client_secret="secret",
        display=500,
        sort="sales",
    )
    low_display = NaverShoppingProvider(
        client_id="id",
        client_secret="secret",
        display=0,
        sort="date",
    )

    assert high_display.display == 100
    assert high_display.sort == "sim"
    assert low_display.display == 10
    assert low_display.sort == "date"


def test_provider_falls_back_to_first_item_when_all_candidates_are_filtered():
    provider = NaverShoppingProvider(client_id="id", client_secret="secret")
    items = [
        product_item(title="강아지 사료 두부맛", productId="fallback"),
        product_item(title="고양이 두부 모래", productId="also-bad"),
    ]

    selected = provider._select_best_item("두부", items)

    assert selected["productId"] == "fallback"
