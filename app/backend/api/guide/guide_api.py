from fastapi import APIRouter, Depends, Query

from app.backend.api.deps import get_current_user_required
from app.backend.schemas.guide import GuideResponse


router = APIRouter(prefix="/guide", tags=["Guide (식재료 가이드)"])


@router.get("", response_model=GuideResponse)
def search_ingredient_guide(
    keyword: str = Query(..., description="검색할 식재료명"),
    current_user_id: int = Depends(get_current_user_required),
):
    """
    특정 식재료의 보관법, 손질법, 신선도 판별법을 조회합니다.
    현재는 API 계약 확인용 임시 응답을 반환합니다.
    """
    return {
        "name": keyword,
        "storage_tips": f"{keyword}는 상태에 따라 밀봉 후 적절한 온도에서 보관하세요.",
        "prep_tips": "흙이나 이물질을 제거한 뒤 용도에 맞게 손질하세요.",
        "freshness_tips": "색, 냄새, 물러짐 여부를 함께 확인하세요.",
    }


@router.get("/urgent", response_model=GuideResponse)
def get_urgent_guide(
    current_user_id: int = Depends(get_current_user_required),
):
    """
    소비 임박 식재료를 기준으로 긴급 보관 가이드를 추천합니다.
    현재는 API 계약 확인용 임시 응답을 반환합니다.
    """
    return {
        "name": "두부",
        "storage_tips": "개봉한 두부는 깨끗한 물에 담가 냉장 보관하고 빠르게 소비하세요.",
        "prep_tips": "사용 전 물기를 제거하면 조리하기 좋습니다.",
        "freshness_tips": "시큼한 냄새가 나거나 표면이 끈적하면 폐기하세요.",
    }
