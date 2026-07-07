from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ProductSearchResult:
    """외부 쇼핑 provider가 반환하는 상품 검색 결과 표준 형식입니다."""

    provider: str
    product_id: str | None
    product_name: str | None
    product_link: str | None
    product_image: str | None
    price: int | None
    mall_name: str | None


class ShoppingProvider(Protocol):
    """네이버/쿠팡 등 쇼핑 상품 provider가 맞춰야 하는 공통 인터페이스입니다."""

    provider_name: str

    def search_best_product(self, keyword: str) -> ProductSearchResult | None:
        """검색어 기준 대표 상품 하나를 반환합니다."""
        ...

    def build_product_link(self, product: ProductSearchResult) -> str | None:
        """상품 링크를 반환합니다. 쿠팡 도입 시 제휴 딥링크 생성 지점입니다."""
        ...
