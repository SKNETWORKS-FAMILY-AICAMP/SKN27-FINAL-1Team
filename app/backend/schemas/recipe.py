from typing import Optional

from pydantic import BaseModel, Field


class RecipeSearchItem(BaseModel):
    recipe_id: int = Field(..., description="레시피 ID")
    recipe_name: str = Field(..., description="레시피명")
    category: Optional[str] = Field(None, description="카테고리")
    difficulty: Optional[str] = Field(None, description="난이도")
    cooking_time_min: Optional[int] = Field(None, description="조리 시간(분)")
    serving_count: Optional[int] = Field(None, description="기준 인분")
    main_image_url: Optional[str] = Field(None, description="대표 이미지 URL")


class RecipeSearchResponse(BaseModel):
    items: list[RecipeSearchItem] = Field(default_factory=list, description="검색 결과 목록")
    total: int = Field(..., description="전체 결과 수")
    page: int = Field(..., description="현재 페이지")
    page_size: int = Field(..., description="페이지 크기")
    has_next: bool = Field(..., description="다음 페이지 존재 여부")
