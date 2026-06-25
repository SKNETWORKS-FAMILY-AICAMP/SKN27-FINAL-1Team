from fastapi import APIRouter, Depends, HTTPException, Query

from app.backend.api.deps import get_current_user
from app.backend.schemas.guide import GuideDetailResponse, GuideListResponse, GuideResponse
from app.backend.services.guide_service.guide_service import guide_service


router = APIRouter(prefix="/guide", tags=["Guide (식재료 가이드)"])


@router.get("", response_model=GuideListResponse)
def search_ingredient_guide(
    keyword: str | None = Query(default=None, description="검색할 식재료명"),
    limit: int = Query(default=60, ge=1, le=100, description="반환 개수"),
    current_user_id: int = Depends(get_current_user),
):
    """Neo4j에 적재된 식재료 가이드를 검색합니다."""
    return guide_service.search_guides(keyword=keyword, limit=limit)


@router.get("/detail/{code}", response_model=GuideDetailResponse)
def get_ingredient_guide_detail(
    code: str,
    current_user_id: int = Depends(get_current_user),
):
    """식품 코드로 식재료 가이드 상세 정보를 조회합니다."""
    guide = guide_service.get_guide_detail(code)
    if guide is None:
        raise HTTPException(status_code=404, detail="식재료 가이드를 찾을 수 없습니다.")
    return guide


@router.get("/urgent", response_model=GuideResponse)
def get_urgent_guide(
    current_user_id: int = Depends(get_current_user),
):
    """소비 임박 식재료용 기본 가이드. 재고 연동 전까지는 기본값을 반환합니다."""
    return {
        "name": "파",
        "storage_tips": "냉장 보관하고, 남은 것은 잘게 썰어 밀폐용기에 넣어 냉장 또는 냉동 보관하세요.",
        "prep_tips": "시든 겉잎과 뿌리 부분을 정리한 뒤 용도에 맞게 손질하세요.",
        "freshness_tips": "줄기가 단단하고 잎 색이 선명한지 확인하세요.",
    }
