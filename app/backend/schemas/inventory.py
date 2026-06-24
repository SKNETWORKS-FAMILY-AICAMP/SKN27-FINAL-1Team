from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


class IngredientBase(BaseModel):
    """냉장고 식재료 등록/수정에 공통으로 사용하는 입력 스키마입니다."""

    name: str = Field(..., min_length=1, description="식재료 이름")
    category: Optional[str] = Field(None, description="식재료 카테고리")
    quantity: float = Field(default=1.0, gt=0, description="보유 수량")
    unit: str = Field(default="개", description="수량 단위")
    storage_method: Optional[str] = Field(default=None, description="보관 위치")
    purchase_date: Optional[date] = Field(None, description="구매일")
    expiration_date: Optional[date] = Field(None, description="표기된 소비기한")


class IngredientCreate(IngredientBase):
    """냉장고 식재료 생성/수정 요청 스키마입니다."""

    pass


class IngredientResponse(IngredientBase):
    """냉장고 식재료 조회 응답 스키마입니다."""

    id: int
    fridge_id: int
    purchase_date: date
    created_at: datetime
    updated_at: Optional[datetime] = None
    d_day: Optional[int] = Field(None, description="소비기한까지 남은 일수")
    is_expiring_soon: bool = Field(default=False, description="D-3 이내 소비 임박 여부")
    is_expired: bool = Field(default=False, description="소비기한 경과 여부")
    status: str = Field(default="normal", description="normal, expiring, expired, used 중 하나")

    class Config:
        from_attributes = True


class StorageSummary(BaseModel):
    """보관 위치별 냉장고 식재료 개수 요약입니다."""

    냉장: int = Field(default=0)
    냉동: int = Field(default=0)
    실온: int = Field(default=0)
    기타: int = Field(default=0)


class InventorySummaryResponse(BaseModel):
    """냉장고 목록 상단에서 사용하는 요약 응답 스키마입니다."""

    total: int = Field(default=0, description="전체 식재료 개수")
    expiring_soon: int = Field(default=0, description="D-3 이내 소비 임박 식재료 개수")
    expired: int = Field(default=0, description="소비기한이 지난 식재료 개수")
    today_added: int = Field(default=0, description="오늘 입고된 식재료 개수")
    storage: StorageSummary = Field(default_factory=StorageSummary, description="보관 위치별 식재료 개수")


class IngredientPredictionResponse(BaseModel):
    """식재료명 입력 시 AI가 예측한 유효성, 보관 위치, 예상 기한 응답 스키마입니다."""

    is_valid_food: bool
    storage_method: str
    lifespan_days: int
