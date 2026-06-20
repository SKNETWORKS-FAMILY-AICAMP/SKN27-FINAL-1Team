from pydantic import BaseModel, Field
from typing import Optional
from datetime import date, datetime

class IngredientBase(BaseModel):
    name: str = Field(..., description="식재료 이름 (예: 시금치)")
    category: Optional[str] = Field(None, description="식재료 카테고리 (예: 채소)")
    quantity: float = Field(default=1.0, description="수량")
    unit: str = Field(default="개", description="수량 단위 (예: 개, g, ml)")
    storage_method: str = Field(default="냉장", description="보관 방법 (냉장, 냉동, 실온)")
    purchase_date: Optional[date] = Field(None, description="구매일/입고일 (없으면 오늘 날짜로 자동 지정)")
    expiration_date: Optional[date] = Field(None, description="표기된 유통기한 (없으면 권장 보관 기간으로 자동 계산)")

class IngredientCreate(IngredientBase):
    pass

class IngredientResponse(IngredientBase):
    id: int
    fridge_id: int
    purchase_date: date  # Response에서는 반드시 채워져서 나감
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    # 동적 계산 필드
    d_day: Optional[int] = Field(None, description="유통기한/권장보관기한까지 남은 일수 (양수면 남음, 음수면 지남)")
    is_expiring_soon: bool = Field(default=False, description="유통기한 임박 여부 (3일 이하)")

    class Config:
        from_attributes = True

class StorageSummary(BaseModel):
    냉장: int = Field(default=0)
    냉동: int = Field(default=0)
    실온: int = Field(default=0)
    기타: int = Field(default=0)

class InventorySummaryResponse(BaseModel):
    total: int = Field(default=0, description="전체 식재료 개수")
    expiring_soon: int = Field(default=0, description="소비 임박 (D-3 이내) 식재료 개수")
    today_added: int = Field(default=0, description="오늘 입고된 식재료 개수")
    storage: StorageSummary = Field(description="보관 위치별 식재료 개수")
