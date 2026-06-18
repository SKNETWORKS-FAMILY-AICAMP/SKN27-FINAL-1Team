from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class OnboardingRequest(BaseModel):
    disliked_ingredients: List[str] = Field(
        default_factory=list, 
        description="비선호 식재료 목록 (예: ['오이', '당근'])"
    )
    allergy: List[str] = Field(
        default_factory=list, 
        description="알레르기 유발 식품 목록 (예: ['땅콩', '우유'])"
    )
    is_alert_allowed: bool = Field(
        default=True, 
        description="알림 수신 동의 여부"
    )

class OnboardingResponse(OnboardingRequest):
    id: int
    user_id: int
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
