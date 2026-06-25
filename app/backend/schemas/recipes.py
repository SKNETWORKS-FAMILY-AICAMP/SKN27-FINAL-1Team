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
    mode: Literal["fridge_consume", "menu_custom"] = Field(
        default="fridge_consume",
        description="추천 모드 (fridge_consume | menu_custom)",
    )
    limit: int = Field(
        default=9,
        ge=1,
        le=50,
        description="반환 개수 (menu_custom). fridge_consume은 서버 고정 9",
    )
    exclude_recipe_ids: list[int] = Field(default_factory=list, description="제외할 레시피 ID")
    refresh_pool: bool = Field(default=False, description="true면 검색 풀 재생성 후 exclude 무시")
    query: Optional[str] = Field(None, description="레시피명 검색 (menu_custom)")
    category: Optional[str] = Field(None, description="카테고리 필터 (menu_custom)")
    difficulty: Optional[str] = Field(None, description="난이도 필터 (menu_custom)")
    cooking_time_label: Optional[str] = Field(None, description="조리시간 라벨 필터 (menu_custom)")
    min_display_match_rate: Optional[int] = Field(
        None, ge=0, le=100, description="최소 보유 재료 매칭률 (menu_custom)"
    )
    require_any_owned: bool = Field(
        default=False, description="보유 재료 1개 이상 필수 (menu_custom)"
    )
    use_expiry_priority: bool = Field(
        default=False, description="유통기한 임박 재료 우선 (menu_custom)"
    )
    pool_multiplier: int = Field(
        default=3, ge=1, le=10, description="후보 풀 크기 = limit * pool_multiplier (menu_custom)"
    )


class RecipeRecommendItem(RecipeSearchItem):
    match_rate: int = Field(..., ge=0, le=100, description="가중치 반영 매칭률")
    display_match_rate: int = Field(..., ge=0, le=100, description="표시용 매칭률")
    owned_ingredient_count: int = Field(..., ge=0, description="보유(부분 포함) 재료 수")
    missing_ingredient_count: int = Field(..., ge=0, description="부족 재료 수")
    expiry_score: int = Field(default=0, ge=0, description="유통기한 우선 점수")
    reason: Optional[str] = Field(None, description="추천 이유 한 줄")


class RecipeRecommendResponse(BaseModel):
    mode: str = Field(..., description="추천 모드")
    items: list[RecipeRecommendItem] = Field(default_factory=list, description="추천 결과")
    returned_count: int = Field(..., description="반환된 결과 수")
    has_more: bool = Field(..., description="같은 풀에서 추가 추천 가능 여부")


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
