from urllib.parse import parse_qs, urlparse

import httpx

from app.backend.services.shopping_service.providers.naver_search import NaverShoppingProvider


def _item(
    title: str,
    link: str,
    price: int,
    *,
    category1: str = "식품",
    category2: str = "농산물",
) -> dict:
    return {
        "productId": link.rsplit("/", 1)[-1],
        "title": title,
        "link": link,
        "image": f"{link}.jpg",
        "lprice": str(price),
        "mallName": "테스트몰",
        "category1": category1,
        "category2": category2,
    }


def _fallback_query(product_link: str) -> str:
    return parse_qs(urlparse(product_link).query)["sword"][0]


def test_returns_food_search_link_when_api_is_not_configured():
    provider = NaverShoppingProvider(client_id="", client_secret="")

    result = provider.search_best_product("버터")

    assert result is not None
    assert result.provider == "kurly"
    assert result.product_id is None
    assert result.product_name is None
    assert result.mall_name == "컬리"
    assert result.price is None
    assert _fallback_query(result.product_link) == "버터"


def test_uses_original_cooking_oil_name_for_fallback():
    provider = NaverShoppingProvider(client_id="", client_secret="")

    result = provider.search_best_product("올리브유")

    assert result is not None
    assert _fallback_query(result.product_link) == "올리브유"


def test_returns_search_link_when_all_api_candidates_are_filtered(monkeypatch):
    provider = NaverShoppingProvider(client_id="id", client_secret="secret")
    monkeypatch.setattr(
        provider,
        "_request_items",
        lambda query, display: [
            _item("강아지 버터 간식", "https://example.com/pet", 5000, category1="생활/건강", category2="반려동물"),
        ],
    )

    result = provider.search_best_product("버터")

    assert result is not None
    assert result.product_id is None
    assert _fallback_query(result.product_link) == "버터"


def test_keeps_filtered_product_selection_when_api_returns_valid_items(monkeypatch):
    provider = NaverShoppingProvider(client_id="id", client_secret="secret", display=6)
    monkeypatch.setattr(
        provider,
        "_request_items",
        lambda query, display: [
            _item("양파 특가", "https://example.com/outlier", 100),
            _item("강아지 양파 장난감", "https://example.com/pet", 4500, category1="생활/건강", category2="반려동물"),
            _item("국산 양파", "https://example.com/valid-1", 5000),
            _item("햇 양파", "https://example.com/valid-2", 5500),
            _item("무농약 양파", "https://example.com/valid-3", 6000),
            _item("친환경 양파", "https://example.com/valid-4", 6500),
        ],
    )

    result = provider.search_best_product("양파")

    assert result is not None
    assert result.product_id == "valid-1"
    assert result.product_link == "https://example.com/valid-1"
    assert result.price == 5000


def test_manual_product_search_returns_one_fallback_candidate(monkeypatch):
    provider = NaverShoppingProvider(client_id="id", client_secret="secret")
    monkeypatch.setattr(provider, "_request_items", lambda query, display: [])

    results = provider.search_products("파슬리가루", display=5)

    assert len(results) == 1
    assert results[0].product_name is None
    assert _fallback_query(results[0].product_link) == "파슬리가루"


def test_disables_retries_after_non_retryable_api_status(monkeypatch):
    provider = NaverShoppingProvider(client_id="id", client_secret="secret")
    request_count = 0

    def fail_request(*args, **kwargs):
        nonlocal request_count
        request_count += 1
        request = httpx.Request("GET", provider.api_url)
        response = httpx.Response(404, request=request)
        raise httpx.HTTPStatusError("not found", request=request, response=response)

    monkeypatch.setattr(httpx.Client, "get", fail_request)

    first = provider.search_best_product("양파")
    second = provider.search_best_product("감자")

    assert request_count == 1
    assert _fallback_query(first.product_link) == "양파"
    assert _fallback_query(second.product_link) == "감자"
