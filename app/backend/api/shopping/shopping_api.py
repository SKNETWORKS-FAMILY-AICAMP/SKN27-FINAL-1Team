from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.backend.api.deps import get_current_user_required
from app.backend.db.session import get_db
from app.backend.schemas.common import MessageResponse
from app.backend.schemas.shopping import (
    ShoppingCompareRequest,
    ShoppingCompareResponse,
    ShoppingCurrentResponse,
    ShoppingListCreateRequest,
    ShoppingListItemUpdateRequest,
    ShoppingListResponse,
    ShoppingPurchaseRequest,
    ShoppingPurchaseResponse,
)
from app.backend.services.shopping_service import shopping_service


router = APIRouter(prefix="/shopping-list", tags=["Shopping List (장보기)"])


@router.post("", response_model=ShoppingListResponse, status_code=status.HTTP_201_CREATED)
def create_shopping_list(
    request_data: ShoppingListCreateRequest,
    current_user_id: int = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """레시피 부족 재료 또는 직접 입력 재료로 앱 내부 장보기 목록을 생성합니다."""
    return shopping_service.create_list(
        db=db,
        user_id=current_user_id,
        recipe_id=request_data.recipe_id,
        source=request_data.source,
        missing_ingredients=request_data.missing_ingredients,
    )


@router.post("/from-recipe", response_model=ShoppingListResponse, status_code=status.HTTP_201_CREATED)
def create_shopping_list_from_recipe(
    request_data: ShoppingListCreateRequest,
    current_user_id: int = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """레시피 상세 화면에서 넘긴 부족 재료로 장보기 목록을 생성합니다."""
    request_data.source = "recipe"
    return shopping_service.create_list(
        db=db,
        user_id=current_user_id,
        recipe_id=request_data.recipe_id,
        source=request_data.source,
        missing_ingredients=request_data.missing_ingredients,
    )


@router.get("/current", response_model=ShoppingCurrentResponse)
def get_current_shopping_list(
    current_user_id: int = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """최근 활성 장보기 목록을 반환합니다."""
    return {"shopping_list": shopping_service.get_current(db=db, user_id=current_user_id)}


@router.get("/{shopping_list_id}", response_model=ShoppingListResponse)
def get_shopping_list(
    shopping_list_id: int,
    current_user_id: int = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """장보기 목록 상세를 반환합니다."""
    return shopping_service.get_list(db=db, user_id=current_user_id, shopping_list_id=shopping_list_id)


@router.patch("/items/{item_id}", response_model=ShoppingListResponse)
def update_shopping_list_item(
    item_id: int,
    request_data: ShoppingListItemUpdateRequest,
    current_user_id: int = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """장보기 재료의 체크/구매 상태를 수정합니다."""
    return shopping_service.update_item(
        db=db,
        user_id=current_user_id,
        item_id=item_id,
        is_checked=request_data.is_checked,
        is_purchased=request_data.is_purchased,
    )


@router.delete("/items/{item_id}", response_model=ShoppingListResponse)
def delete_shopping_list_item(
    item_id: int,
    current_user_id: int = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """장보기 목록에서 재료를 삭제합니다."""
    return shopping_service.delete_item(db=db, user_id=current_user_id, item_id=item_id)


@router.post("/purchase", response_model=ShoppingPurchaseResponse)
def complete_shopping_purchase(
    request_data: ShoppingPurchaseRequest,
    current_user_id: int = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """구매 완료한 장보기 재료를 냉장고에 입고합니다."""
    return shopping_service.complete_purchase(
        db=db,
        user_id=current_user_id,
        shopping_list_id=request_data.shopping_list_id,
        item_ids=request_data.item_ids,
    )


@router.post("/compare", response_model=ShoppingCompareResponse)
def compare_shopping_prices(
    request_data: ShoppingCompareRequest,
    current_user_id: int = Depends(get_current_user_required),
):
    """하위 호환용: 부족 재료명 기준 네이버 쇼핑 상품 후보를 조회합니다."""
    return shopping_service.compare_products(request_data.missing_ingredients)


@router.post("/purchase/mock", response_model=MessageResponse)
def complete_shopping_purchase_mock(
    current_user_id: int = Depends(get_current_user_required),
):
    """구버전 프론트 임시 호환용 응답입니다."""
    return {"message": "구매한 식재료가 냉장고에 입고되었습니다."}
