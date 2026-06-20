from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from datetime import date, datetime
from decimal import Decimal
from app.backend.schemas.inventory import (
    IngredientCreate, IngredientUpdate, IngredientResponse, IngredientBulkCreateRequest
)
from app.backend.api.deps import get_current_user_required

router = APIRouter(prefix="/inventory", tags=["Mock Inventory (냉장고 재고 관리)"])

# 가상 재고 데이터 저장소 (In-Memory 가상 DB 역할)
MOCK_INGREDIENTS = [
    {
        "id": 101,
        "fridge_id": 1,
        "name": "대파",
        "category": "채소",
        "quantity": Decimal("2.00"),
        "unit": "개",
        "storage_method": "냉장",
        "purchase_date": date(2026, 6, 15),
        "expiration_date": date(2026, 6, 22),
        "created_at": datetime.now(),
        "updated_at": datetime.now()
    },
    {
        "id": 102,
        "fridge_id": 1,
        "name": "우유",
        "category": "유제품",
        "quantity": Decimal("1.00"),
        "unit": "개",
        "storage_method": "냉장",
        "purchase_date": date(2026, 6, 16),
        "expiration_date": date(2026, 6, 26),
        "created_at": datetime.now(),
        "updated_at": datetime.now()
    },
    {
        "id": 103,
        "fridge_id": 1,
        "name": "돼지고기 (삼겹살)",
        "category": "육류",
        "quantity": Decimal("600.00"),
        "unit": "g",
        "storage_method": "냉동",
        "purchase_date": date(2026, 6, 10),
        "expiration_date": date(2026, 7, 10),
        "created_at": datetime.now(),
        "updated_at": datetime.now()
    }
]

# 새로운 ID 생성을 위한 시퀀스 값
ingredient_id_counter = 104

@router.get("", response_model=List[IngredientResponse])
def get_mock_inventory(user_id: int = Depends(get_current_user_required)):
    """
    [Mock] 현재 냉장고 내 모든 식재료 목록 조회 API.
    """
    # 임시 목업 환경에서는 user_id에 무관하게 전체 가상 재고 리스트를 반환합니다.
    return MOCK_INGREDIENTS

@router.post("", response_model=IngredientResponse, status_code=status.HTTP_201_CREATED)
def create_mock_ingredient(ingredient: IngredientCreate, user_id: int = Depends(get_current_user_required)):
    """
    [Mock] 식재료 수동 등록 API.
    """
    global ingredient_id_counter
    
    new_ingredient = {
        "id": ingredient_id_counter,
        "fridge_id": 1,  # 임시로 1번 냉장고 매핑
        **ingredient.dict(),
        "created_at": datetime.now(),
        "updated_at": datetime.now()
    }
    
    MOCK_INGREDIENTS.append(new_ingredient)
    ingredient_id_counter += 1
    
    return new_ingredient

@router.put("/{item_id}", response_model=IngredientResponse)
def update_mock_ingredient(item_id: int, updated_data: IngredientUpdate, user_id: int = Depends(get_current_user_required)):
    """
    [Mock] 식재료 정보 수정 API.
    """
    for item in MOCK_INGREDIENTS:
        if item["id"] == item_id:
            update_dict = updated_data.dict(exclude_unset=True)
            for key, val in update_dict.items():
                item[key] = val
            item["updated_at"] = datetime.now()
            return item
            
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="해당 식재료를 찾을 수 없습니다.")

@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_mock_ingredient(item_id: int, user_id: int = Depends(get_current_user_required)):
    """
    [Mock] 식재료 삭제 API.
    """
    global MOCK_INGREDIENTS
    
    for item in MOCK_INGREDIENTS:
        if item["id"] == item_id:
            MOCK_INGREDIENTS = [i for i in MOCK_INGREDIENTS if i["id"] != item_id]
            return
            
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="해당 식재료를 찾을 수 없습니다.")

@router.post("/bulk", response_model=List[IngredientResponse], status_code=status.HTTP_201_CREATED)
def bulk_create_mock_ingredients(request_data: IngredientBulkCreateRequest, user_id: int = Depends(get_current_user_required)):
    """
    [Mock] 영수증 OCR 정제 결과 일괄(Bulk) 등록 API.
    박준희 님이 OCR/정규화 처리한 식재료들을 한꺼번에 냉장고 DB에 집어넣는 동작을 모사합니다.
    """
    global ingredient_id_counter
    added_ingredients = []
    
    for ingredient in request_data.ingredients:
        new_ingredient = {
            "id": ingredient_id_counter,
            "fridge_id": 1,
            **ingredient.dict(),
            "created_at": datetime.now(),
            "updated_at": datetime.now()
        }
        MOCK_INGREDIENTS.append(new_ingredient)
        added_ingredients.append(new_ingredient)
        ingredient_id_counter += 1
        
    return added_ingredients
