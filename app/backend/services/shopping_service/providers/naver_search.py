import html
import logging
import re

import httpx

from app.backend.core.config import settings
from app.backend.services.shopping_service.providers.base import ProductSearchResult

logger = logging.getLogger(__name__)

TAG_RE = re.compile(r"<[^>]+>")


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
        timeout_seconds: int | None = None,
    ):
        self.client_id = client_id if client_id is not None else settings.NAVER_SHOPPING_CLIENT_ID
        self.client_secret = client_secret if client_secret is not None else settings.NAVER_SHOPPING_CLIENT_SECRET
        self.api_url = api_url or settings.NAVER_SHOPPING_API_URL
        self.display = max(int(display or settings.NAVER_SHOPPING_DISPLAY or 1), 1)
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
                response = client.get(
                    self.api_url,
                    params={
                        "query": query,
                        "display": self.display,
                        "start": 1,
                        "sort": "sim",
                    },
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

        item = items[0]
        return ProductSearchResult(
            provider=self.provider_name,
            product_id=self._clean(item.get("productId")),
            product_name=self._clean(item.get("title")),
            product_link=self._clean(item.get("link")),
            product_image=self._clean(item.get("image")),
            price=self._parse_price(item.get("lprice")),
            mall_name=self._clean(item.get("mallName")),
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
