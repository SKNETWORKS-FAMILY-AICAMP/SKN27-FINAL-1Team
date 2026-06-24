from datetime import datetime

from pydantic import BaseModel, Field


class RecommendationSaveRequest(BaseModel):
    recipe_id: int = Field(..., description="저장할 레시피 ID")
    recommendation_type: str = Field(default="manual_save", description="추천/저장 유형")


class RecommendationSaveResponse(BaseModel):
    recommendation_id: int = Field(..., description="추천 결과 ID (저장 건별 고유)")
    recipe_id: int = Field(..., description="레시피 ID")
    recommendation_type: str = Field(..., description="추천 유형")
    created_at: datetime = Field(..., description="저장 시각")


class RecommendationSavedRecipe(BaseModel):
    recommendation_id: int
    recipe_id: int
    title: str
    description: str | None = None
    category: str | None = None
    cooking_time_min: int | None = None
    difficulty: str | None = None
    image_url: str | None = None
    recommendation_type: str
    created_at: datetime
