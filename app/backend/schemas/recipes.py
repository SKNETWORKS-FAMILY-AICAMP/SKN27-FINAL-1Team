from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class RecipeSearchItem(BaseModel):
    recipe_id: int = Field(..., description="레시피 ID")
    title: str = Field(..., description="레시피 제목")
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


class RecipeRecommendRequest(BaseModel):
    priority: str = Field(default="소비 임박 우선", description="추천 우선순위")


class RecipeRecommendItem(RecipeSearchItem):
    match_rate: int = Field(..., ge=0, le=100, description="추천 매칭률")


class RecipeIngredientItem(BaseModel):
    name: str = Field(..., description="재료명")
    amount: Optional[str] = Field(None, description="분량 (예: 1대, 100g)")
    ingredient_id: Optional[int] = Field(None, description="식재료 마스터 ID")


class MaybeOwnedIngredientItem(BaseModel):
    recipe_ingredient_name: str = Field(..., description="레시피 재료명")
    fridge_ingredient_name: str = Field(..., description="매칭된 냉장고 재료명")
    match_type: Literal["recipe_in_fridge", "fridge_in_recipe"] = Field(
        ..., description="문자열 포함 매칭 유형"
    )
    score: float = Field(..., description="유사도 점수 (초기 포함 매칭 시 1.0)")
    name: str = Field(..., description="레시피 재료명 (UI 호환)")
    amount: Optional[str] = Field(None, description="분량 (예: 1대, 100g)")
    ingredient_id: Optional[int] = Field(
        None, description="레시피 측 식재료 마스터 ID"
    )


class RecipeStepItem(BaseModel):
    title: str = Field(..., description="단계 제목")
    text: str = Field(..., description="단계 설명")
    image_url: Optional[str] = Field(None, description="단계 이미지 URL")


class RecipeDetailResponse(RecipeSearchItem):
    owned_ingredients: List[RecipeIngredientItem] = Field(
        default_factory=list, description="보유 재료 (ID exact match)"
    )
    maybe_owned_ingredients: List[MaybeOwnedIngredientItem] = Field(
        default_factory=list, description="부분 보유 재료 (문자열 포함 매칭)"
    )
    missing_ingredients: List[RecipeIngredientItem] = Field(
        default_factory=list, description="부족 재료"
    )
    match_rate: int = Field(
        default=0, ge=0, le=100, description="가중치 반영 매칭률 (maybe_owned 0.5)"
    )
    display_match_rate: int = Field(
        default=0, ge=0, le=100, description="표시용 매칭률 (maybe_owned 전량 보유 인정)"
    )
    steps: List[RecipeStepItem] = Field(default_factory=list, description="조리 단계")
    source_url: Optional[str] = Field(None, description="출처 URL")
