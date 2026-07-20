import html
import logging
import re

import httpx

from app.backend.core.config import settings
from app.backend.services.shopping_service.providers.base import ProductSearchResult

logger = logging.getLogger(__name__)

TAG_RE = re.compile(r"<[^>]+>")
WORD_RE = re.compile(r"[가-힣a-zA-Z0-9]+")

SORT_OPTIONS = {"sim", "date", "asc", "dsc"}
FOOD_CATEGORY_ROOTS = {"식품"}
MIN_PRICE_OUTLIER_RATIO = 0.2
MAX_PRICE_OUTLIER_RATIO = 5.0
BLOCKED_TITLE_TERMS = (
    "강아지",
    "고양이",
    "반려견",
    "반려묘",
    "애견",
    "애묘",
    "펫",
    "사료",
)
BLOCKED_CATEGORY_TERMS = (
    "반려동물",
    "문구",
    "도서",
    "패션",
    "가구",
    "인테리어",
    "디지털",
    "가전",
)


class NaverShoppingProvider:
    """네이버 쇼핑 검색 API provider.

    프론트엔드는 네이버 API를 직접 호출하지 않고 백엔드의 장보기 API만 호출합니다.
    네이버 provider는 상품 검색 결과를 내부 표준 형식으로 변환합니다.
    """

    provider_name = "naver"

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        api_url: str | None = None,
        display: int | None = None,
        sort: str | None = None,
        exclude: str | None = None,
        timeout_seconds: int | None = None,
    ):
        self.client_id = client_id if client_id is not None else settings.NAVER_SHOPPING_CLIENT_ID
        self.client_secret = client_secret if client_secret is not None else settings.NAVER_SHOPPING_CLIENT_SECRET
        self.api_url = api_url or settings.NAVER_SHOPPING_API_URL
        self.display = min(max(int(display or settings.NAVER_SHOPPING_DISPLAY or 10), 1), 100)
        configured_sort = sort or settings.NAVER_SHOPPING_SORT or "sim"
        self.sort = configured_sort if configured_sort in SORT_OPTIONS else "sim"
        self.exclude = exclude if exclude is not None else settings.NAVER_SHOPPING_EXCLUDE
        self.timeout_seconds = int(timeout_seconds or settings.NAVER_SHOPPING_TIMEOUT_SECONDS or 5)

    @property
    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def search_best_product(self, keyword: str) -> ProductSearchResult | None:
        query = (keyword or "").strip()
        if not query:
            return None

        if not self.is_configured:
            logger.info("네이버 쇼핑 API 키가 없어 상품 검색을 건너뜁니다.")
            return None

        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                params = {
                    "query": query,
                    "display": self.display,
                    "start": 1,
                    "sort": self.sort,
                }
                if self.exclude:
                    params["exclude"] = self.exclude

                response = client.get(
                    self.api_url,
                    params=params,
                    headers={
                        "X-Naver-Client-Id": self.client_id,
                        "X-Naver-Client-Secret": self.client_secret,
                    },
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("네이버 쇼핑 검색 실패(query=%s): %s", query, exc)
            return None

        items = response.json().get("items") or []
        if not items:
            return None

        item = self._select_best_item(query, items)
        if not item:
            return None

        return ProductSearchResult(
            provider=self.provider_name,
            product_id=self._clean(item.get("productId")),
            product_name=self._clean(item.get("title")),
            product_link=self._clean(item.get("link")),
            product_image=self._clean(item.get("image")),
            price=self._parse_price(item.get("lprice")),
            mall_name=self._clean(item.get("mallName")),
            brand=self._clean(item.get("brand")),
            maker=self._clean(item.get("maker")),
            category1=self._clean(item.get("category1")),
            category2=self._clean(item.get("category2")),
            category3=self._clean(item.get("category3")),
            category4=self._clean(item.get("category4")),
            product_type=self._parse_product_type(item.get("productType")),
        )

    def build_product_link(self, product: ProductSearchResult) -> str | None:
        return product.product_link

    def _clean(self, value: object) -> str | None:
        if value is None:
            return None
        cleaned = TAG_RE.sub("", html.unescape(str(value))).strip()
        return cleaned or None

    def _parse_price(self, value: object) -> int | None:
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _parse_product_type(self, value: object) -> int | None:
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _select_best_item(self, query: str, items: list[dict]) -> dict | None:
        candidates = [item for item in items if self._is_recommendable(query, item)]
        candidates = self._remove_price_outliers(candidates)
        if not candidates:
            logger.info("네이버 쇼핑 추천 후보 필터 통과 상품이 없어 링크를 제공하지 않습니다(query=%s).", query)
            return None

        return max(
            enumerate(candidates),
            key=lambda indexed_item: (self._match_score(query, self._clean(indexed_item[1].get("title")) or ""), -indexed_item[0]),
        )[1]

    def _is_recommendable(self, query: str, item: dict) -> bool:
        title = self._clean(item.get("title")) or ""
        category_values = [
            self._clean(item.get("category1")),
            self._clean(item.get("category2")),
            self._clean(item.get("category3")),
            self._clean(item.get("category4")),
        ]
        category_text = " ".join(value for value in category_values if value)

        if self._has_blocked_term(title, BLOCKED_TITLE_TERMS):
            return False

        if self._has_blocked_term(category_text, BLOCKED_CATEGORY_TERMS):
            return False

        category1 = category_values[0]
        if category1 not in FOOD_CATEGORY_ROOTS:
            return False

        price = self._parse_price(item.get("lprice"))
        if price is None or price <= 0:
            return False

        return self._match_score(query, title) > 0

    def _match_score(self, query: str, title: str) -> int:
        query_tokens = self._tokens(query)
        if not query_tokens:
            return 1

        normalized_title = self._normalize(title)
        essential_tokens = [token for token in query_tokens if len(token) >= 2]
        if not essential_tokens:
            return 1

        score = 0
        normalized_query = self._normalize(query)
        if normalized_query and normalized_query in normalized_title:
            score += 3
        score += sum(2 for token in essential_tokens if token in normalized_title)
        score += sum(1 for token in query_tokens if token and len(token) < 2 and token in normalized_title)
        return score

    def _remove_price_outliers(self, items: list[dict]) -> list[dict]:
        if len(items) < 4:
            return items

        prices = sorted(price for item in items if (price := self._parse_price(item.get("lprice"))) is not None and price > 0)
        if len(prices) < 4:
            return items

        median = prices[len(prices) // 2] if len(prices) % 2 else (prices[len(prices) // 2 - 1] + prices[len(prices) // 2]) / 2
        min_price = median * MIN_PRICE_OUTLIER_RATIO
        max_price = median * MAX_PRICE_OUTLIER_RATIO
        filtered = [
            item
            for item in items
            if (price := self._parse_price(item.get("lprice"))) is not None and min_price <= price <= max_price
        ]
        return filtered or items

    def _matches_query_tokens(self, query: str, title: str) -> bool:
        return self._match_score(query, title) > 0

    def _has_blocked_term(self, text: str, blocked_terms: tuple[str, ...]) -> bool:
        normalized_text = self._normalize(text)
        return any(self._normalize(term) in normalized_text for term in blocked_terms)

    def _tokens(self, value: str) -> list[str]:
        return [self._normalize(match.group(0)) for match in WORD_RE.finditer(value or "")]

    def _normalize(self, value: str) -> str:
        return re.sub(r"[^0-9a-zA-Z가-힣]+", "", (value or "").lower())
