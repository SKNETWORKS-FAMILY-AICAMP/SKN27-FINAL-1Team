from pydantic import BaseModel, Field
from typing import List, Optional


class ReceiptParsedItem(BaseModel):
    name: str = Field(..., description="OCR에서 추출한 식재료명")
    qty: float = Field(default=1, description="영수증 기준 수량")
    price: Optional[int] = Field(default=None, description="상품 가격")


class ReceiptUploadResponse(BaseModel):
    items: List[ReceiptParsedItem] = Field(default_factory=list, description="OCR 파싱 결과")


class ReceiptConfirmItem(BaseModel):
    name: str = Field(..., description="최종 입고할 식재료명")
    quantity: float = Field(default=1, description="최종 입고 수량")
    storage_method: str = Field(default="냉장", description="보관 방법")
    price: Optional[int] = Field(default=None, description="OCR 확인 금액")


class ReceiptConfirmRequest(BaseModel):
    items: List[ReceiptConfirmItem] = Field(default_factory=list, description="검수 완료된 입고 목록")
    calendar_cost_enabled: bool = Field(default=True, description="캘린더 사용비용 자동 등록 여부")
