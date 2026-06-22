from fastapi import APIRouter, Depends

from app.backend.api.deps import get_current_user_required
from app.backend.schemas.common import MessageResponse
from app.backend.schemas.shopping import (
    ShoppingCompareRequest,
    ShoppingCompareResponse,
    ShoppingPurchaseRequest,
)


router = APIRouter(prefix="/shopping-list", tags=["Shopping List (장보기)"])


@router.post("/compare", response_model=ShoppingCompareResponse)
def compare_shopping_prices(
    request_data: ShoppingCompareRequest,
    current_user_id: int = Depends(get_current_user_required),
):
    """
    부족한 재료의 마켓별 가격을 비교합니다.
    2차 기능 예정이므로 현재는 API 계약 확인용 임시 응답을 반환합니다.
    """
    market_prices = [
        {
            "name": name,
            "coupang": 3000,
            "kurly": 3500,
            "best_market": "coupang",
        }
        for name in request_data.missing_ingredients
    ]
    return {
        "total_price": sum(item["coupang"] for item in market_prices),
        "delivery_saving": 10500,
        "market_prices": market_prices,
        "recommended_market": "쿠팡",
    }


@router.post("/purchase", response_model=MessageResponse)
def complete_shopping_purchase(
    request_data: ShoppingPurchaseRequest,
    current_user_id: int = Depends(get_current_user_required),
):
    """
    외부 마켓 구매 완료 후 냉장고 자동 입고를 처리합니다.
    2차 기능 예정이므로 현재는 API 계약 확인용 임시 응답을 반환합니다.
    """
    return {"message": "구매한 식재료가 냉장고에 입고되었습니다."}
