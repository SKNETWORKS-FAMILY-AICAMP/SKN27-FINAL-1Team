from datetime import date
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.backend.schemas.inventory import IngredientCreate
from app.backend.services.inventory_service.inventory_service import inventory_service


class FridgeItemsInput(BaseModel):
    """냉장고 재료 목록 조회 Tool 입력 스키마입니다."""

    user_id: int = Field(description="사용자 ID")


class AddFridgeItemInput(BaseModel):
    """냉장고 재료 추가 Tool 입력 스키마입니다."""

    user_id: int = Field(description="사용자 ID")
    name: str = Field(description="식재료명")
    quantity: float = Field(default=1.0, gt=0, description="수량")
    unit: str = Field(default="개", description="단위")
    storage: str | None = Field(default=None, description="냉장, 냉동, 실온")
    purchase_date: date | None = Field(default=None, description="구매일 YYYY-MM-DD")
    expiration_date: date | None = Field(default=None, description="소비기한 YYYY-MM-DD")


class ConsumeFridgeItemInput(BaseModel):
    """냉장고 재료 소비 Tool 입력 스키마입니다."""

    user_id: int = Field(description="사용자 ID")
    name: str = Field(description="식재료명")
    quantity: float = Field(default=1.0, gt=0, description="수량")


class DeleteFridgeItemInput(BaseModel):
    """냉장고 재료 폐기 Tool 입력 스키마입니다."""

    user_id: int = Field(description="사용자 ID")
    name: str = Field(description="식재료명")


class ExpiringFridgeItemsInput(BaseModel):
    """소비 임박 재료 조회 Tool 입력 스키마입니다."""

    user_id: int = Field(description="사용자 ID")
    days: int = Field(default=3, ge=0, description="소비 임박 기준 일수")


def _ok(message: str, data: Any = None) -> dict[str, Any]:
    """Tool 공통 성공 응답을 만듭니다."""
    return {"ok": True, "message": message, "data": data or {}, "error": None}


def _fail(message: str, code: str = "FRIDGE_TOOL_ERROR", detail: str | None = None) -> dict[str, Any]:
    """Tool 공통 실패 응답을 만듭니다."""
    return {"ok": False, "message": message, "data": None, "error": {"code": code, "detail": detail or message}}


def _item_data(item: dict[str, Any]) -> dict[str, Any]:
    """냉장고 응답 항목을 Tool용 JSON으로 정리합니다."""
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "quantity": item.get("quantity"),
        "unit": item.get("unit"),
        "storage": item.get("storage_method"),
        "expiration_date": str(item.get("expiration_date")) if item.get("expiration_date") else None,
        "d_day": item.get("d_day"),
        "status": item.get("status"),
    }


def _run_write(db: Session, action) -> dict[str, Any]:
    """쓰기 Tool 실패 시 DB 세션을 롤백합니다."""
    try:
        return action()
    except HTTPException as exc:
        db.rollback()
        return _fail(str(exc.detail), "FRIDGE_HTTP_ERROR", str(exc.detail))
    except Exception as exc:
        db.rollback()
        return _fail('냉장고 작업 중 문제가 생겼어요.', detail=str(exc))


def get_fridge_items_tool(db: Session, user_id: int) -> dict[str, Any]:
    """사용자의 활성 냉장고 재료를 조회합니다."""
    items = [_item_data(item) for item in inventory_service.get_ingredients(db=db, user_id=user_id)]
    return _ok('냉장고 재료를 조회했어요.', {"items": items})


def add_fridge_item_tool(
    db: Session,
    user_id: int,
    name: str,
    quantity: float = 1.0,
    unit: str = "개",
    storage: str | None = None,
    purchase_date: date | None = None,
    expiration_date: date | None = None,
) -> dict[str, Any]:
    """기존 냉장고 서비스를 사용해 재료를 추가합니다."""
    def action() -> dict[str, Any]:
        data = IngredientCreate(
            name=name,
            quantity=quantity,
            unit=unit,
            storage_method=storage,
            purchase_date=purchase_date,
            expiration_date=expiration_date,
        )
        item = inventory_service.add_ingredient(db=db, user_id=user_id, data=data)
        return _ok(f"{item['name']}을(를) 냉장고에 추가했어요.", {"item": _item_data(item)})

    return _run_write(db, action)


def consume_fridge_item_tool(db: Session, user_id: int, name: str, quantity: float = 1.0) -> dict[str, Any]:
    """재료명과 수량으로 냉장고 재고를 차감합니다."""
    return _run_write(db, lambda: _ok(inventory_service.consume_ingredient_by_name(db, user_id, name, quantity)))


def delete_fridge_item_tool(db: Session, user_id: int, name: str) -> dict[str, Any]:
    """재료명으로 냉장고 항목을 폐기 처리합니다."""
    return _run_write(db, lambda: _ok(inventory_service.delete_ingredient_by_name(db, user_id, name)))


def get_expiring_items_tool(db: Session, user_id: int, days: int = 3) -> dict[str, Any]:
    """지정한 기간 이내에 소비기한이 도래하는 재료를 조회합니다."""
    items = [
        _item_data(item)
        for item in inventory_service.get_ingredients(db=db, user_id=user_id)
        if item.get("d_day") is not None and item["d_day"] <= days
    ]
    return _ok('소비 임박 재료를 조회했어요.', {"items": items})


FRIDGE_MCP_TOOLS = {
    "get_fridge_items": get_fridge_items_tool,
    "add_fridge_item": add_fridge_item_tool,
    "consume_fridge_item": consume_fridge_item_tool,
    "delete_fridge_item": delete_fridge_item_tool,
    "get_expiring_items": get_expiring_items_tool,
}
