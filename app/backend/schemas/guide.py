from pydantic import BaseModel, Field


class GuideListItem(BaseModel):
    code: str = Field(..., description="식품 코드")
    name: str = Field(..., description="식재료명")
    representative_name: str | None = Field(default=None, description="대표 식품명")
    raw_name: str | None = Field(default=None, description="원재료명")
    major_category: str | None = Field(default=None, description="대분류")
    middle_category: str | None = Field(default=None, description="중분류")
    minor_category: str | None = Field(default=None, description="소분류")
    seasonal_months: list[int] = Field(default_factory=list, description="제철 월")


class GuideListResponse(BaseModel):
    items: list[GuideListItem] = Field(default_factory=list, description="식재료 가이드 목록")
    total: int = Field(..., description="전체 검색 결과 수")
    returned_count: int = Field(..., description="반환 개수")


class GuideResponse(BaseModel):
    name: str = Field(..., description="식재료명")
    storage_tips: str = Field(..., description="보관 방법")
    prep_tips: str | None = Field(default=None, description="손질 방법")
    freshness_tips: str | None = Field(default=None, description="신선도 체크 방법")


class GuideDetailResponse(GuideListItem):
    aliases: list[str] = Field(default_factory=list, description="이명")
    existing_display_name: str | None = Field(default=None, description="기존 표시명")
    storage_tips: str | None = Field(default=None, description="보관 방법")
    horticultural_storage_tips: str | None = Field(default=None, description="원예 보관 방법")
    prep_tips: str | None = Field(default=None, description="손질 방법")
    washing_tips: str | None = Field(default=None, description="세척 방법")
    freshness_tips: str | None = Field(default=None, description="신선도 체크")
    intake_tips: str | None = Field(default=None, description="섭취 방법")
    nutrition_base_amount: str | None = Field(default=None, description="영양성분 기준량")
    energy_kcal: float | None = Field(default=None, description="에너지 kcal")
    protein_g: float | None = Field(default=None, description="단백질 g")
    fat_g: float | None = Field(default=None, description="지방 g")
    carbohydrate_g: float | None = Field(default=None, description="탄수화물 g")
    calcium_mg: float | None = Field(default=None, description="칼슘 mg")
    potassium_mg: float | None = Field(default=None, description="칼륨 mg")
    sodium_mg: float | None = Field(default=None, description="나트륨 mg")
    storage_source_name: str | None = Field(default=None, description="보관 출처명")
    storage_source_url: str | None = Field(default=None, description="보관 출처 URL")
    prep_source_name: str | None = Field(default=None, description="손질 출처명")
    prep_source_url: str | None = Field(default=None, description="손질 출처 URL")
    washing_source_name: str | None = Field(default=None, description="세척 출처명")
    washing_source_url: str | None = Field(default=None, description="세척 출처 URL")
    freshness_source_name: str | None = Field(default=None, description="신선도 출처명")
    freshness_source_url: str | None = Field(default=None, description="신선도 출처 URL")
    nutrition_source_name: str | None = Field(default=None, description="영양 출처명")
