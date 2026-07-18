from sqlalchemy.orm import Session
import logging
import math

from app.backend.services.inventory_service.inventory_service import inventory_service
from ai.agents.inventory_agent.inventory_utils import (
    _apply_josa,
    _normalize_text,
    _inventory_refresh_action,
    _extract_expiry_keyword,
    _format_d_day,
    ADD_WORDS,
    CONSUME_WORDS,
    DEFAULT_STORAGE,
    STORAGE_KEYS,
    _extract_add_items,
    _extract_delete_name,
    _extract_consume_name,
    _extract_storage,
    _extract_quantity,
    _is_all_quantity_request,
    _quantity_text,
    _confirm_action,
    _pending_add_from_history,
    _pending_add_storage_from_history,
    _pending_consume_from_history,
    _storage_choice_response
)

logger = logging.getLogger(__name__)

EMPTY_INVENTORY_REPLY = '냉장고가 비어 있어요. 재료를 등록하면 소비 임박 재료와 추천 메뉴를 알려드릴게요.'


def _is_safe_action_name(name: str) -> bool:
    """내부 확인 명령을 깨뜨릴 수 있는 구분자가 식재료명에 없는지 확인합니다."""
    value = (name or "").strip()
    return bool(value) and len(value) <= 100 and not any(char in value for char in (":", "|", "\n", "\r"))


def _is_positive_quantity(value: str | float) -> bool:
    """수량이 유한한 양수인지 확인합니다."""
    try:
        quantity = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(quantity) and quantity > 0


def execute_inventory_action(action: str, parts: list[str], db: Session, user_id: int) -> dict:
    """
    내부 명령어(parts)를 받아서 실제 재고 CRUD 작업을 실행합니다.
    """
    try:
        if action == "consume_ingredient" and len(parts) >= 4:
            if not _is_safe_action_name(parts[2]) or not _is_positive_quantity(parts[3]):
                return {"response_text": "올바른 식재료명과 수량을 입력해주세요.", "slots": {"inventory_pending": None}}
            reply = inventory_service.consume_ingredient_by_name(db, user_id, parts[2], float(parts[3]))
            return {"response_text": reply, "actions": [_inventory_refresh_action()], "slots": {"inventory_pending": None}}

        if action == "add_ingredient" and len(parts) >= 5:
            if not _is_safe_action_name(parts[2]) or not _is_positive_quantity(parts[3]) or parts[4] not in STORAGE_KEYS:
                return {"response_text": "올바른 식재료명, 수량, 보관 위치를 입력해주세요.", "slots": {"inventory_pending": None}}
            reply = inventory_service.add_ingredient_by_name(db, user_id, parts[2], float(parts[3]), parts[4])
            return {"response_text": reply, "actions": [_inventory_refresh_action()], "slots": {"inventory_pending": None}}

        if action == "add_ingredient_unchecked" and len(parts) >= 5:
            if not _is_positive_quantity(parts[3]) or parts[4] not in STORAGE_KEYS:
                return {"response_text": "올바른 식재료명, 수량, 보관 위치를 입력해주세요.", "slots": {"inventory_pending": None}}
            if not is_valid_ingredient(parts[2]):
                return {"response_text": "올바른 식재료명을 입력해주세요.", "slots": {"inventory_pending": None}}
            reply = inventory_service.add_ingredient_unchecked_by_name(db, user_id, parts[2], float(parts[3]), parts[4])
            return {"response_text": reply, "actions": [_inventory_refresh_action()], "slots": {"inventory_pending": None}}

        if action == "add_ingredients" and len(parts) >= 3:
            added = []
            for raw_item in parts[2].split("|"):
                name, quantity, storage = raw_item.split(",", 2)
                if (
                    not _is_safe_action_name(name)
                    or not _is_positive_quantity(quantity)
                    or storage not in STORAGE_KEYS
                    or not resolve_ingredient_name(db, name)
                ):
                    raise ValueError("잘못된 재료 추가 명령입니다.")
                added.append(inventory_service.add_ingredient_by_name(db, user_id, name, float(quantity), storage, commit=False))
            db.commit()
            return {"response_text": "\n".join(added), "actions": [_inventory_refresh_action()], "slots": {"inventory_pending": None}}

        if action == "delete_ingredient" and len(parts) >= 4:
            if not _is_safe_action_name(parts[2]) or not _is_positive_quantity(parts[3]):
                return {"response_text": "올바른 식재료명과 수량을 입력해주세요.", "slots": {"inventory_pending": None}}
            reply = inventory_service.discard_ingredient_by_name(db, user_id, parts[2], float(parts[3]))
            return {"response_text": reply, "actions": [_inventory_refresh_action()], "slots": {"inventory_pending": None}}

    except Exception:
        db.rollback()
        logger.exception("Inventory Agent: 작업 실행 실패 %s", action)
        return {"response_text": "냉장고 작업을 처리하는 중 문제가 생겼어요. 잠시 후 다시 시도해주세요.", "slots": {"inventory_pending": None}}
        
    return {"response_text": "확인할 작업을 찾지 못했어요. 다시 요청해주세요.", "slots": {"inventory_pending": None}}


def get_inventory_list(db: Session, user_id: int) -> str:
    """냉장고 보유 재료를 짧게 요약합니다."""
    items = inventory_service.get_ingredients(db=db, user_id=user_id)
    if not items:
        return EMPTY_INVENTORY_REPLY

    names = [item["name"] for item in items[:8]]
    if len(items) > 8:
        return f"현재 냉장고에는 {', '.join(names)} 외 {len(items) - 8}개가 있어요."
    return f"현재 냉장고에는 {', '.join(names[:-1]) + ', ' if len(names) > 1 else ''}{_apply_josa(names[-1], '이가')} 있어요."


def _get_expiring_inventory_result(db: Session, user_id: int, text: str = "") -> dict:
    """임박 재료 안내문과 다음 Agent에 전달할 재료명 목록을 함께 반환합니다."""
    items = inventory_service.get_ingredients(db=db, user_id=user_id)
    if not items:
        return {"response_text": EMPTY_INVENTORY_REPLY, "slots": {"expiring_ingredients": []}}

    keyword = _extract_expiry_keyword(text)
    if keyword:
        matched = [item for item in items if keyword in item.get("name", "")]
        if not matched:
            return {
                "response_text": f"냉장고에 등록된 {keyword} 재료를 찾지 못했어요.",
                "slots": {"expiring_ingredients": []},
            }
        summary = [f"{item['name']} {_format_d_day(item['d_day'])}" for item in matched if item.get("d_day") is not None]
        return {
            "response_text": f"{keyword} 소비기한은 " + ", ".join(summary) + "예요.",
            "slots": {"expiring_ingredients": [item["name"] for item in matched[:5]]},
        }

    expiring = sorted(
        [item for item in items if item.get("d_day") is not None and item["d_day"] <= 3],
        key=lambda item: item["d_day"],
    )
    if not expiring:
        return {"response_text": "D-3 이내로 임박한 재료는 없어요.", "slots": {"expiring_ingredients": []}}

    summary = [f"{item['name']} {_format_d_day(item['d_day'])}" for item in expiring[:5]]
    return {
        "response_text": "소비기한 확인이 필요한 재료예요.\n" + ", ".join(summary),
        "slots": {"expiring_ingredients": [item["name"] for item in expiring[:5]]},
    }


def get_expiring_inventory(db: Session, user_id: int, text: str = "") -> str:
    """기존 호출부를 위해 소비기한 안내문만 반환합니다."""
    return _get_expiring_inventory_result(db, user_id, text)["response_text"]


def resolve_ingredient_name(db: Session, name: str) -> str | None:
    """마스터 식재료 DB에 존재하는 이름인지 확인하고 정규화된 이름을 반환합니다."""
    return inventory_service._resolve_known_ingredient_name(db, name)


def is_valid_ingredient(name: str) -> bool:
    """안전한 식재료명인지 확인한 뒤 AI 서비스로 유효성을 판별합니다."""
    if not _is_safe_action_name(name):
        return False
    from app.backend.services.inventory_service.expiration_ai_service import expiration_ai_service
    return expiration_ai_service.is_valid_ingredient_name(name)


def is_inventory_empty(db: Session, user_id: int) -> bool:
    """냉장고가 비어있는지 여부를 반환합니다."""
    items = inventory_service.get_ingredients(db=db, user_id=user_id)
    return len(items) == 0

def _unknown_add_response(items: list[dict], db: Session) -> dict | None:
    """마스터에 없는 식재료명을 추가 플로우로 넘길지 판단합니다."""
    for item in items:
        if _normalize_text(item["name"]) in {"안녕", "하이", "hello", "hi"}:
            return {"response_text": "올바른 식재료명을 입력해주세요.", "slots": {"inventory_pending": None}}
        if not resolve_ingredient_name(db, item["name"]):
            if item["quantity"] is None:
                return {"response_text": f"'{item['name']}'의 수량을 알려주시겠어요? (예: {item['name']} 1개)", "slots": {"inventory_pending": {"action": "add_quantity", "name": item["name"], "unchecked": True}}}
            if not item["storage"]:
                return _storage_choice_response(item["name"], item["quantity"], unchecked=True)
            command = f"확인:add_ingredient_unchecked:{item['name']}:{item['quantity']}:{item['storage']}"
            reply = f"{item['name']} {_quantity_text(item['quantity'])}개를 {item['storage']}에 추가할까요?"
            return {"response_text": reply, "actions": [_confirm_action("확인", command), _confirm_action("취소", "취소")], "slots": {"inventory_pending": None}}
    return None


def _quantity_action_response(db: Session, user_id: int, name: str, quantity: float | None, action: str) -> dict:
    """보유 수량을 확인해 소비 또는 폐기 확인 응답을 만듭니다."""
    if quantity is not None and not _is_positive_quantity(quantity):
        return {"response_text": "수량은 0보다 크게 입력해주세요.", "slots": {"inventory_pending": None}}

    total = inventory_service.get_total_quantity_by_name(db, user_id, name)
    if total <= 0:
        return {
            "response_text": f"냉장고에서 {_apply_josa(name, '을를')} 찾을 수 없어요.",
            "slots": {"inventory_pending": None},
        }

    actual_quantity = total if quantity is None else min(float(quantity), total)
    quantity_text = _quantity_text(actual_quantity)
    verb = "폐기" if action == "delete_ingredient" else "소비"
    if quantity is None or float(quantity) > total:
        reply = f"현재 {_apply_josa(name, '은는')} {_quantity_text(total)}개 있어요. {quantity_text}개를 모두 {verb} 처리할까요?"
    else:
        reply = f"{name} {quantity_text}개를 {verb} 처리할까요?"
    command = f"확인:{action}:{name}:{actual_quantity}"
    pending_action = "delete_confirm" if action == "delete_ingredient" else "consume_confirm"
    return {
        "response_text": reply,
        "actions": [_confirm_action("확인", command), _confirm_action("취소", "취소")],
        "slots": {
            "inventory_pending": {"action": pending_action, "name": name},
            "inventory_last_action": None,
        },
    }


def _handle_inventory_action(text: str, db: Session, user_id: int) -> dict:
    """식재료 추가/소비를 규칙 기반으로 처리합니다."""
    normalized = _normalize_text(text)

    if any(word in normalized for word in ADD_WORDS):
        items = _extract_add_items(text)
        
        invalid_items = [item['name'] for item in items if not is_valid_ingredient(item['name'])]
        if invalid_items:
            return {"response_text": "올바른 식재료명을 입력해주세요.", "slots": {"inventory_pending": None}}

        unknown_response = _unknown_add_response(items, db)
        if unknown_response:
            return unknown_response
        if len(items) > 1:
            if any(item["quantity"] is None for item in items):
                return {"response_text": "각 식재료의 수량을 알려주시면 추가해드릴게요.", "slots": {"inventory_pending": {"action": "add_many"}}}
            payload = "|".join(f"{item['name']},{item['quantity']},{item['storage'] or DEFAULT_STORAGE}" for item in items)
            summary = ", ".join(f"{item['name']} {_quantity_text(item['quantity'])}개" for item in items)
            return {"response_text": f"{summary}를 냉장고에 추가할까요?", "actions": [_confirm_action("확인", f"확인:add_ingredients:{payload}"), _confirm_action("취소", "취소")], "slots": {"inventory_pending": None}}
        if len(items) == 1:
            item = items[0]
            if item["quantity"] is None:
                return {"response_text": f"{_apply_josa(item['name'], '을를')} 몇 개 추가하시겠어요?", "slots": {"inventory_pending": {"action": "add_quantity", "name": item["name"], "unchecked": False}}}
            if not item["storage"]:
                return _storage_choice_response(item["name"], item["quantity"])
            reply_text = f"{item['name']} {_quantity_text(item['quantity'])}개를 {item['storage']}에 추가할까요?"
            command = f"확인:add_ingredient:{item['name']}:{item['quantity']}:{item['storage']}"
            return {"response_text": reply_text, "actions": [_confirm_action("확인", command), _confirm_action("취소", "취소")], "slots": {"inventory_pending": None}}
        return {"response_text": "어떤 식재료를 추가할까요? 식재료명과 수량을 함께 알려주세요."}

    if any(word in normalized for word in CONSUME_WORDS):
        name = _extract_consume_name(text)
        if not name:
            return {"response_text": "어떤 식재료를 소비 처리할까요?"}
        quantity = _extract_quantity(text)
        if quantity is None:
            return {"response_text": f"{_apply_josa(name, '을를')} 몇 개 소비할까요?", "slots": {"inventory_pending": {"action": "consume_quantity", "name": name}}}
        return _quantity_action_response(db, user_id, name, quantity, "consume_ingredient")

    return {"response_text": "음식과 관련된 대화만 지원하고 있어요! 요리 레시피, 식재료 보관법, 냉장고 재료 관리 등을 물어봐주세요!"}

def run_inventory_agent(intent: str, text: str, history: list, db: Session, user_id: int, slots: dict | None = None) -> dict:
    """냉장고 에이전트의 단일 진입점입니다."""
    pending = (slots or {}).get("inventory_pending")
    pending = pending if isinstance(pending, dict) else {}

    if intent == "action.confirm":
        parts = text.split(":")
        if len(parts) >= 2:
            return execute_inventory_action(parts[1], parts, db, user_id)
        return {"response_text": "확인할 작업을 찾지 못했어요. 다시 요청해주세요.", "slots": {"inventory_pending": None}}

    if intent == "inventory.list":
        return {"response_text": get_inventory_list(db, user_id)}
    
    if intent == "inventory.expiring":
        return _get_expiring_inventory_result(db, user_id, text)

    if intent == "inventory.cancel" or intent == "action.cancel":
        last_action = None
        if pending.get("action") in {"delete_confirm", "consume_confirm"}:
            last_action = {"action": pending["action"], "name": pending.get("name", "")}
        return {
            "response_text": "알겠습니다. 작업을 취소하겠습니다.",
            "slots": {"inventory_pending": None, "inventory_last_action": last_action},
        }
        
    if intent == "inventory.delete":
        name = _extract_delete_name(text)
        if not name:
            return {"response_text": "음식과 관련된 대화만 지원하고 있어요! 요리 레시피, 식재료 보관법, 냉장고 재료 관리 등을 물어봐주세요!"}
        quantity = _extract_quantity(text)
        if quantity is None and not _is_all_quantity_request(text):
            return {"response_text": f"{_apply_josa(name, '을를')} 몇 개 폐기할까요?", "slots": {"inventory_pending": {"action": "delete_quantity", "name": name}}}
        return _quantity_action_response(db, user_id, name, quantity, "delete_ingredient")

    if intent == "inventory.pending_delete":
        name = pending.get("name") if pending.get("action") in {"delete_quantity", "delete_confirm"} else ""
        quantity = _extract_quantity(text)
        all_request = _is_all_quantity_request(text)
        if not name or (quantity is None and not all_request):
            return {"response_text": "폐기할 식재료와 수량을 다시 알려주세요.", "slots": {"inventory_pending": pending or None}}
        return _quantity_action_response(db, user_id, name, quantity, "delete_ingredient")

    if intent == "inventory.pending_consume":
        name = pending.get("name") if pending.get("action") in {"consume_quantity", "consume_confirm"} else None
        name = name or _pending_consume_from_history(history) or ""
        quantity = _extract_quantity(text)
        if quantity is None:
            return {"response_text": "소비할 수량을 숫자와 함께 알려주세요. 예: 1개", "slots": {"inventory_pending": pending or None}}
        return _quantity_action_response(db, user_id, name, quantity, "consume_ingredient")

    if intent == "inventory.pending_add_storage":
        legacy_pending = _pending_add_storage_from_history(history)
        storage = _extract_storage(text) or DEFAULT_STORAGE
        if pending.get("action") == "add_storage":
            name = pending.get("name", "")
            quantity = float(pending.get("quantity") or 1)
            unchecked = bool(pending.get("unchecked"))
        elif legacy_pending:
            name, quantity = legacy_pending
            unchecked = not resolve_ingredient_name(db, name)
        else:
            return {"response_text": "음식과 관련된 대화만 지원하고 있어요! 요리 레시피, 식재료 보관법, 냉장고 재료 관리 등을 물어봐주세요!"}
        action = "add_ingredient_unchecked" if unchecked else "add_ingredient"
        reply = f"{name} {_quantity_text(quantity)}개를 {storage}에 추가할까요?"
        command = f"확인:{action}:{name}:{quantity}:{storage}"
        return {"response_text": reply, "actions": [_confirm_action("확인", command), _confirm_action("취소", "취소")], "slots": {"inventory_pending": None}}

    if intent == "inventory.pending_add":
        name = pending.get("name") if pending.get("action") == "add_quantity" else None
        name = name or _pending_add_from_history(history) or ""
        quantity = _extract_quantity(text)
        if quantity is None:
            return {"response_text": "추가할 수량을 숫자와 함께 알려주세요. 예: 1개", "slots": {"inventory_pending": pending or None}}
        storage = _extract_storage(text)
        unchecked = bool(pending.get("unchecked")) if pending.get("action") == "add_quantity" else not resolve_ingredient_name(db, name)
        if not storage:
            return _storage_choice_response(name, quantity, unchecked=unchecked)
        action = "add_ingredient_unchecked" if unchecked else "add_ingredient"
        reply = f"{name} {_quantity_text(quantity)}개를 {storage}에 추가할까요?"
        command = f"확인:{action}:{name}:{quantity}:{storage}"
        return {"response_text": reply, "actions": [_confirm_action("확인", command), _confirm_action("취소", "취소")], "slots": {"inventory_pending": None}}

    if intent == "inventory.pending_add_many_retry":
        return {"response_text": "식재료와 개수를 함께 말해주세요. 예: 파스타면1, 토마토소스1, 냉동 새우1", "slots": {"inventory_pending": {"action": "add_many"}}}

    if intent == "inventory.pending_add_many":
        items = _extract_add_items(text)
        payload = "|".join(f"{item['name']},{item['quantity'] or 1},{item['storage'] or DEFAULT_STORAGE}" for item in items)
        summary = ", ".join(f"{item['name']} {_quantity_text(item['quantity'] or 1)}개" for item in items)
        reply = f"{summary}를 냉장고에 추가할까요?"
        return {"response_text": reply, "actions": [_confirm_action("확인", f"확인:add_ingredients:{payload}"), _confirm_action("취소", "취소")], "slots": {"inventory_pending": None}}

    if intent == "inventory.action":
        return _handle_inventory_action(text, db, user_id)

    return {"response_text": "아직 지원하지 않는 냉장고 작업이에요."}
