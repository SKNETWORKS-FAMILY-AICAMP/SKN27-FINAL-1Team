from pydantic import BaseModel, Field


class GuideResponse(BaseModel):
    name: str = Field(..., description="식재료명")
    storage_tips: str = Field(..., description="보관 방법")
    prep_tips: str | None = Field(default=None, description="손질 방법")
    freshness_tips: str | None = Field(default=None, description="신선도 판별 방법")
