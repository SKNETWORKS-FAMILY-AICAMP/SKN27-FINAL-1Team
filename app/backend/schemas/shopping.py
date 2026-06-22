from pydantic import BaseModel, Field
from typing import List


class ShoppingCompareRequest(BaseModel):
    missing_ingredients: List[str] = Field(default_factory=list, description="부족한 재료 목록")


class MarketPriceItem(BaseModel):
    name: str = Field(..., description="재료명")
    coupang: int | None = Field(default=None, description="쿠팡 가격")
    kurly: int | None = Field(default=None, description="마켓컬리 가격")
    best_market: str | None = Field(default=None, description="추천 마켓")


class ShoppingCompareResponse(BaseModel):
    total_price: int = Field(default=0, description="예상 총 가격")
    delivery_saving: int = Field(default=0, description="배달 대비 예상 절약 금액")
    market_prices: List[MarketPriceItem] = Field(default_factory=list, description="마켓별 가격 비교")
    recommended_market: str | None = Field(default=None, description="최종 추천 마켓")


class PurchasedItem(BaseModel):
    name: str = Field(..., description="구매한 재료명")
    quantity: float = Field(default=1, description="구매 수량")
    market: str | None = Field(default=None, description="구매 마켓")


class ShoppingPurchaseRequest(BaseModel):
    purchased_items: List[PurchasedItem] = Field(default_factory=list, description="구매 완료 목록")
