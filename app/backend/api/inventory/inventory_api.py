from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from typing import List
from app.backend.db.session import get_db
from app.backend.api.deps import get_current_user_required
from app.backend.schemas.inventory import IngredientCreate, IngredientResponse, InventorySummaryResponse, IngredientPredictionResponse
from app.backend.services.inventory_service.inventory_service import inventory_service

router = APIRouter(prefix="/inventory", tags=["Inventory (나의 냉장고)"])

from app.backend.services.inventory_service.expiration_ai_service import expiration_ai_service

@router.get("/summary", response_model=InventorySummaryResponse)
def get_inventory_summary_data(
    current_user_id: int = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    내 냉장고의 요약 통계 데이터를 반환합니다.
    (전체 식재료 개수, 소비 임박 개수, 보관 위치별 개수 등)
    """
    return inventory_service.get_inventory_summary(db=db, user_id=current_user_id)

@router.get("/predict", response_model=IngredientPredictionResponse)
def predict_ingredient_info(
    name: str,
    current_user_id: int = Depends(get_current_user_required)
):
    """
    식재료명 입력 시 AI가 해당 식재료가 맞는지 유효성을 검사하고,
    추천 보관 위치, 예상 소비기한을 실시간으로 반환합니다.
    """
    return expiration_ai_service.predict_ingredient_info(name)

@router.get("", response_model=List[IngredientResponse])
def get_my_fridge_ingredients(
    current_user_id: int = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    내 냉장고에 있는 모든 식재료 목록을 가져옵니다.
    자동으로 D-day와 임박 여부(is_expiring_soon)를 계산해서 내려줍니다.
    """
    return inventory_service.get_ingredients(db=db, user_id=current_user_id)

@router.post("", response_model=IngredientResponse, status_code=status.HTTP_201_CREATED)
def add_ingredient_to_fridge(
    request_data: IngredientCreate,
    current_user_id: int = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    내 냉장고에 새로운 식재료를 등록합니다.
    (최초 등록 시 냉장고가 없다면 자동으로 '나의 냉장고'가 생성됩니다.)
    """
    return inventory_service.add_ingredient(db=db, user_id=current_user_id, data=request_data)

@router.delete("/{ingredient_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_ingredient_from_fridge(
    ingredient_id: int,
    current_user_id: int = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    식재료를 냉장고에서 삭제(소진 처리) 합니다.
    """
    inventory_service.delete_ingredient(db=db, user_id=current_user_id, ingredient_id=ingredient_id)
    return None

@router.put("/{ingredient_id}", response_model=IngredientResponse)
def update_ingredient_in_fridge(
    ingredient_id: int,
    request_data: IngredientCreate,
    current_user_id: int = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    기존에 등록된 식재료의 정보(수량, 유통기한 등)를 수정합니다.
    """
    return inventory_service.update_ingredient(
        db=db,
        user_id=current_user_id,
        ingredient_id=ingredient_id,
        data=request_data
    )
