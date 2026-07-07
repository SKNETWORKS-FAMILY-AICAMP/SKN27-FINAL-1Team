from sqlalchemy.orm import Session
import logging

from app.backend.services.inventory_service.inventory_service import inventory_service
from ai.agents.supervisor_agent.chat_utils import (
    _inventory_refresh_action,
    _apply_josa,
    _extract_expiry_keyword,
    _format_d_day
)

logger = logging.getLogger(__name__)

EMPTY_INVENTORY_REPLY = '냉장고가 비어 있어요. 재료를 등록하면 소비 임박 재료와 추천 메뉴를 알려드릴게요.'

def execute_inventory_action(action: str, parts: list[str], db: Session, user_id: int) -> dict:
    """
    내부 명령어(parts)를 받아서 실제 재고 CRUD 작업을 실행합니다.
    """
    try:
        if action == "consume_ingredient" and len(parts) >= 4:
            reply = inventory_service.consume_ingredient_by_name(db, user_id, parts[2], float(parts[3]))
            return {"response_text": reply, "actions": [_inventory_refresh_action()]}

        if action == "add_ingredient" and len(parts) >= 5:
            reply = inventory_service.add_ingredient_by_name(db, user_id, parts[2], float(parts[3]), parts[4])
            return {"response_text": reply, "actions": [_inventory_refresh_action()]}

        if action == "add_ingredient_unchecked" and len(parts) >= 5:
            reply = inventory_service.add_ingredient_unchecked_by_name(db, user_id, parts[2], float(parts[3]), parts[4])
            return {"response_text": reply, "actions": [_inventory_refresh_action()]}

        if action == "add_ingredients" and len(parts) >= 3:
            added = []
            for raw_item in parts[2].split("|"):
                name, quantity, storage = raw_item.split(",", 2)
                added.append(inventory_service.add_ingredient_by_name(db, user_id, name, float(quantity), storage))
            return {"response_text": "\n".join(added), "actions": [_inventory_refresh_action()]}

        if action == "delete_ingredient" and len(parts) >= 3:
            reply = inventory_service.delete_ingredient_by_name(db, user_id, parts[2])
            return {"response_text": reply, "actions": [_inventory_refresh_action()]}

    except Exception:
        db.rollback()
        logger.exception("Inventory Agent: 작업 실행 실패 %s", action)
        return {"response_text": "냉장고 작업을 처리하는 중 문제가 생겼어요. 잠시 후 다시 시도해주세요."}
        
    return {"response_text": "확인할 작업을 찾지 못했어요. 다시 요청해주세요."}


def get_inventory_list(db: Session, user_id: int) -> str:
    """냉장고 보유 재료를 짧게 요약합니다."""
    items = inventory_service.get_ingredients(db=db, user_id=user_id)
    if not items:
        return EMPTY_INVENTORY_REPLY

    names = [item["name"] for item in items[:8]]
    suffix = "" if len(items) <= 8 else f" 외 {len(items) - 8}개"
    target_word = suffix if suffix else names[-1]
    return f"현재 냉장고에는 {', '.join(names[:-1]) + ', ' if len(names) > 1 else ''}{_apply_josa(target_word, '이가')} 있어요."


def get_expiring_inventory(db: Session, user_id: int, text: str = "") -> str:
    """소비기한이 가까운 재료 또는 특정 재료의 D-day를 안내합니다."""
    items = inventory_service.get_ingredients(db=db, user_id=user_id)
    if not items:
        return EMPTY_INVENTORY_REPLY

    keyword = _extract_expiry_keyword(text)
    if keyword:
        matched = [item for item in items if keyword in item.get("name", "")]
        if not matched:
            return f"냉장고에 등록된 {keyword} 재료를 찾지 못했어요."
        summary = [f"{item['name']} {_format_d_day(item['d_day'])}" for item in matched if item.get("d_day") is not None]
        return f"{keyword} 소비기한은 " + ", ".join(summary) + "예요."

    expiring = sorted(
        [item for item in items if item.get("d_day") is not None and item["d_day"] <= 3],
        key=lambda item: item["d_day"],
    )
    if not expiring:
        return "D-3 이내로 임박한 재료는 없어요."

    summary = [f"{item['name']} {_format_d_day(item['d_day'])}" for item in expiring[:5]]
    return "소비기한이 가까운 재료는\n" + ", ".join(summary) + "예요."


def resolve_ingredient_name(db: Session, name: str) -> str | None:
    """마스터 식재료 DB에 존재하는 이름인지 확인하고 정규화된 이름을 반환합니다."""
    return inventory_service._resolve_known_ingredient_name(db, name)


def is_valid_ingredient(name: str) -> bool:
    """식용 가능한 식재료 이름인지 AI 서비스로 판별합니다."""
    from app.backend.services.inventory_service.expiration_ai_service import expiration_ai_service
    return expiration_ai_service.is_valid_ingredient_name(name)


def is_inventory_empty(db: Session, user_id: int) -> bool:
    """냉장고가 비어있는지 여부를 반환합니다."""
    items = inventory_service.get_ingredients(db=db, user_id=user_id)
    return len(items) == 0
