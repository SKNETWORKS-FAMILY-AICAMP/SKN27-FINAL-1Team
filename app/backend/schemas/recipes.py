from pydantic import BaseModel, Field
from typing import List


class RecipeSearchItem(BaseModel):
    recipe_id: int = Field(..., description="레시피 ID")
    title: str = Field(..., description="레시피 제목")


class RecipeRecommendRequest(BaseModel):
    priority: str = Field(default="소비 임박 우선", description="추천 우선순위")


class RecipeRecommendItem(RecipeSearchItem):
    match_rate: int = Field(..., ge=0, le=100, description="추천 매칭률")


class RecipeDetailResponse(RecipeSearchItem):
    ingredients: List[str] = Field(default_factory=list, description="필요 재료")
    steps: List[str] = Field(default_factory=list, description="조리 단계")
