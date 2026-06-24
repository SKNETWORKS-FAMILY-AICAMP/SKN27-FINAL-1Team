from datetime import date, datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from app.backend.api.deps import get_current_user_required
from app.backend.schemas.inventory import IngredientCreate, IngredientResponse, InventorySummaryResponse

router = APIRouter(prefix="/inventory", tags=["Mock Inventory"])


# 실제 DB 없이 API 계약을 확인할 때 사용하는 메모리 기반 mock 데이터입니다.
MOCK_INGREDIENTS = [
    {
        "id": 101,
        "fridge_id": 101,
        "name": "두부",
        "category": "가공식품",
        "quantity": 1.0,
        "unit": "개",
        "storage_method": "냉장",
        "purchase_date": date(2026, 6, 20),
        "expiration_date": date(2026, 6, 26),
        "created_at": datetime.now(),
        "updated_at": datetime.now(),
        "d_day": 2,
        "is_expiring_soon": True,
        "is_expired": False,
        "status": "expiring",
    },
    {
        "id": 102,
        "fridge_id": 102,
        "name": "계란",
        "category": "유제품",
        "quantity": 10.0,
        "unit": "개",
        "storage_method": "냉장",
        "purchase_date": date(2026, 6, 18),
        "expiration_date": date(2026, 6, 30),
        "created_at": datetime.now(),
        "updated_at": datetime.now(),
        "d_day": 6,
        "is_expiring_soon": False,
        "is_expired": False,
        "status": "normal",
    },
]

ingredient_id_counter = 103


# mock 식재료의 D-day와 상태 필드를 요청 시점 기준으로 갱신합니다.
def enrich_mock_item(item: dict) -> dict:
    today = date.today()
    expiration_date = item.get("expiration_date")
    d_day = (expiration_date - today).days if expiration_date else None
    status_value = "expired" if d_day is not None and d_day < 0 else "expiring" if d_day is not None and d_day <= 3 else "normal"
    return {
        **item,
        "d_day": d_day,
        "is_expired": d_day is not None and d_day < 0,
        "is_expiring_soon": d_day is not None and 0 <= d_day <= 3,
        "status": status_value,
    }


@router.get("/summary", response_model=InventorySummaryResponse)
def get_mock_inventory_summary(user_id: int = Depends(get_current_user_required)):
    """mock 냉장고 요약 정보를 반환합니다."""
    items = [enrich_mock_item(item) for item in MOCK_INGREDIENTS]
    return {
        "total": len(items),
        "expiring_soon": sum(1 for item in items if item["is_expiring_soon"]),
        "expired": sum(1 for item in items if item["is_expired"]),
        "today_added": sum(1 for item in items if item["purchase_date"] == date.today()),
        "storage": {
            "냉장": sum(1 for item in items if item["storage_method"] == "냉장"),
            "냉동": sum(1 for item in items if item["storage_method"] == "냉동"),
            "실온": sum(1 for item in items if item["storage_method"] == "실온"),
            "기타": sum(1 for item in items if item["storage_method"] not in ["냉장", "냉동", "실온"]),
        },
    }


@router.get("", response_model=List[IngredientResponse])
def get_mock_inventory(user_id: int = Depends(get_current_user_required)):
    """mock 냉장고 식재료 목록을 반환합니다."""
    return [enrich_mock_item(item) for item in MOCK_INGREDIENTS]


@router.post("", response_model=IngredientResponse, status_code=status.HTTP_201_CREATED)
def create_mock_ingredient(ingredient: IngredientCreate, user_id: int = Depends(get_current_user_required)):
    """mock 냉장고에 식재료를 추가합니다."""
    global ingredient_id_counter
    new_item = {
        "id": ingredient_id_counter,
        "fridge_id": ingredient_id_counter,
        **ingredient.model_dump(),
        "storage_method": ingredient.storage_method or "냉장",
        "purchase_date": ingredient.purchase_date or date.today(),
        "expiration_date": ingredient.expiration_date or date.today(),
        "created_at": datetime.now(),
        "updated_at": datetime.now(),
    }
    MOCK_INGREDIENTS.append(new_item)
    ingredient_id_counter += 1
    return enrich_mock_item(new_item)


@router.put("/{item_id}", response_model=IngredientResponse)
def update_mock_ingredient(item_id: int, updated_data: IngredientCreate, user_id: int = Depends(get_current_user_required)):
    """mock 냉장고 식재료 정보를 수정합니다."""
    for item in MOCK_INGREDIENTS:
        if item["id"] == item_id:
            item.update(updated_data.model_dump())
            item["storage_method"] = updated_data.storage_method or "냉장"
            item["purchase_date"] = updated_data.purchase_date or date.today()
            item["expiration_date"] = updated_data.expiration_date or date.today()
            item["updated_at"] = datetime.now()
            return enrich_mock_item(item)

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="해당 식재료를 찾을 수 없습니다.")


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_mock_ingredient(item_id: int, user_id: int = Depends(get_current_user_required)):
    """mock 냉장고 식재료를 삭제합니다."""
    global MOCK_INGREDIENTS
    before_count = len(MOCK_INGREDIENTS)
    MOCK_INGREDIENTS = [item for item in MOCK_INGREDIENTS if item["id"] != item_id]
    if len(MOCK_INGREDIENTS) == before_count:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="해당 식재료를 찾을 수 없습니다.")
