from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date, datetime
from decimal import Decimal

# ==========================================
# [식재료 (Ingredient) 관련 스키마]
# ==========================================

class IngredientBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="식재료명")
    category: Optional[str] = Field(None, description="식재료 카테고리 (채소, 육류 등)")
    quantity: Decimal = Field(default=Decimal("1.0"), ge=0, description="수량")
    unit: str = Field(default="개", description="수량 단위 (개, g, ml 등)")
    storage_method: str = Field(default="냉장", description="보관 방식 (냉장, 냉동, 실온)")
    purchase_date: date = Field(default_factory=date.today, description="구매/입고일")
    expiration_date: Optional[date] = Field(None, description="유통기한")

class IngredientCreate(IngredientBase):
    pass

class IngredientUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    quantity: Optional[Decimal] = None
    unit: Optional[str] = None
    storage_method: Optional[str] = None
    purchase_date: Optional[date] = None
    expiration_date: Optional[date] = None

class IngredientResponse(IngredientBase):
    id: int
    fridge_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# ==========================================
# [냉장고 (Fridge) 관련 스키마]
# ==========================================

class FridgeBase(BaseModel):
    name: str = Field(default="나의 냉장고", description="냉장고 명칭")

class FridgeCreate(FridgeBase):
    pass

class FridgeResponse(FridgeBase):
    id: int
    user_id: int
    created_at: datetime

    class Config:
        from_attributes = True

# ==========================================
# [벌크 등록(Bulk Insert) 관련 스키마]
# ==========================================

class IngredientBulkCreateRequest(BaseModel):
    ingredients: List[IngredientCreate]
