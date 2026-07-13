from datetime import date, datetime
from typing import List, Literal

from pydantic import BaseModel, Field


ShoppingSource = Literal["recipe", "manual"]
ShoppingStatus = Literal["active", "completed"]


class ShoppingIngredientInput(BaseModel):
    """장보기 목록에 담을 부족 재료 입력값입니다."""

    name: str = Field(..., min_length=1, description="재료명/검색어")
    ingredient_id: int | None = Field(default=None, description="식재료 마스터 ID")
    required_quantity: float | None = Field(default=None, description="필요 수량")
    unit: str | None = Field(default=None, description="필요 수량 단위")
    amount: str | None = Field(default=None, description="프론트/레시피 표시용 원본 수량 문자열")


class ShoppingListCreateRequest(BaseModel):
    """레시피 부족 재료 또는 직접 입력 재료로 장보기 목록을 생성합니다."""

    recipe_id: int | None = Field(default=None, description="기준 레시피 ID")
    source: ShoppingSource = Field(default="recipe", description="생성 출처")
    missing_ingredients: List[ShoppingIngredientInput] = Field(default_factory=list, description="부족 재료 목록")


class ShoppingListItemUpdateRequest(BaseModel):
    """장보기 재료의 체크/구매 상태를 수정합니다."""

    is_checked: bool | None = Field(default=None, description="구매 링크 열기 대상 여부")
    is_purchased: bool | None = Field(default=None, description="구매 완료 여부")


class ShoppingPurchaseRequest(BaseModel):
    """장보기 목록 구매 완료 후 냉장고 입고를 요청합니다."""

    shopping_list_id: int | None = Field(default=None, description="장보기 목록 ID")
    item_ids: List[int] | None = Field(default=None, description="입고 처리할 장보기 재료 ID 목록")


class ShoppingProductItem(BaseModel):
    """장보기 재료와 매칭된 외부 쇼핑 상품 스냅샷입니다."""

    id: int
    ingredient_id: int | None = None
    name: str
    required_quantity: float | None = None
    unit: str | None = None
    provider: str = "naver"
    product_id: str | None = None
    product_name: str | None = None
    product_link: str | None = None
    product_image: str | None = None
    price: int | None = None
    mall_name: str | None = None
    is_checked: bool = True
    is_purchased: bool = False
    created_at: datetime | None = None

    class Config:
        from_attributes = True


class ShoppingOwnedIngredientItem(BaseModel):
    """현재 냉장고 기준으로 레시피에 보유 중인 재료입니다."""

    name: str
    amount: str | None = None
    ingredient_id: int | None = None
    fridge_ingredient_name: str | None = None
    expiry_date: date | None = None
    status: str | None = None
    is_expired: bool = False


class ShoppingListResponse(BaseModel):
    """장보기 목록 상세 응답입니다."""

    id: int
    user_id: int
    recipe_id: int | None = None
    recipe_title: str | None = None
    source: ShoppingSource
    status: ShoppingStatus
    total_price: int = 0
    checked_count: int = 0
    purchased_count: int = 0
    created_at: datetime | None = None
    items: List[ShoppingProductItem] = Field(default_factory=list)
    owned_ingredients: List[ShoppingOwnedIngredientItem] = Field(default_factory=list)

    class Config:
        from_attributes = True


class ShoppingCurrentResponse(BaseModel):
    """사용자의 최근 활성 장보기 목록 응답입니다."""

    shopping_list: ShoppingListResponse | None = None


class ShoppingHistoryResponse(BaseModel):
    """사용자의 장보기 목록 내역 응답입니다."""

    shopping_lists: List[ShoppingListResponse] = Field(default_factory=list)


class ShoppingPurchaseResponse(BaseModel):
    """구매 완료 및 냉장고 입고 결과입니다."""

    message: str
    stocked_count: int = 0
    shopping_list: ShoppingListResponse | None = None


class ShoppingCompareRequest(BaseModel):
    """하위 호환용: 부족 재료명만 받아 상품 후보를 조회합니다."""

    missing_ingredients: List[str] = Field(default_factory=list, description="부족한 재료 목록")


class MarketPriceItem(BaseModel):
    """하위 호환용 가격 비교 응답 항목입니다."""

    name: str = Field(..., description="재료명")
    provider: str | None = Field(default=None, description="쇼핑 provider")
    coupang: int | None = Field(default=None, description="쿠팡 가격")
    kurly: int | None = Field(default=None, description="마켓컬리 가격")
    best_market: str | None = Field(default=None, description="추천 마켓")
    product_id: str | None = Field(default=None, description="외부 상품 ID")
    product_name: str | None = Field(default=None, description="추천 상품명")
    product_link: str | None = Field(default=None, description="추천 상품 링크")
    product_image: str | None = Field(default=None, description="추천 상품 이미지")
    price: int | None = Field(default=None, description="추천 상품 가격")
    mall_name: str | None = Field(default=None, description="판매몰")


class ShoppingCompareResponse(BaseModel):
    """하위 호환용 가격 비교 응답입니다."""

    total_price: int = Field(default=0, description="예상 총 가격")
    delivery_saving: int = Field(default=0, description="배달 대비 예상 절약 금액")
    market_prices: List[MarketPriceItem] = Field(default_factory=list, description="마켓별 가격 비교")
    recommended_market: str | None = Field(default=None, description="최종 추천 마켓")
