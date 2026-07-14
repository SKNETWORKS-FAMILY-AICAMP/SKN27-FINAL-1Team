from __future__ import annotations

from typing import Any

from ai.agents.shopping_agent.shopping_handlers import (
    handle_check_item,
    handle_compare,
    handle_create_confirm,
    handle_create_request,
    handle_current,
    handle_delete_item_confirm,
    handle_delete_item_request,
    handle_history,
    handle_owned,
    handle_purchase_confirm,
    handle_purchase_request,
)
from ai.agents.shopping_agent.shopping_utils import (
    build_shopping_response,
    to_supervisor_state,
)


def _success(message: str, intent: str, actions: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return to_supervisor_state(build_shopping_response(message=message, intent=intent, actions=actions))


def _failure(message: str, intent: str = "shopping.error") -> dict[str, Any]:
    return to_supervisor_state(
        build_shopping_response(
            message=message,
            intent=intent,
            ok=False,
            error={"code": "SHOPPING_AGENT_ERROR", "message": message},
        )
    )


def execute_shopping_action(action: str, payload: str, *, db: Any, user_id: int) -> dict[str, Any]:
    try:
        if action == "shopping_create":
            names = [name for name in payload.split("|") if name]
            message, actions = handle_create_confirm(db, user_id, names)
            return _success(message, "shopping.create", actions)

        if action == "shopping_purchase":
            shopping_list_id = int(payload) if payload else None
            message, actions = handle_purchase_confirm(db, user_id, shopping_list_id)
            return _success(message, "shopping.purchase", actions)

        if action == "shopping_delete_item":
            item_id = int(payload)
            message, actions = handle_delete_item_confirm(db, user_id, item_id)
            return _success(message, "shopping.delete_item", actions)
    except Exception:
        if db is not None:
            try:
                db.rollback()
            except Exception:
                pass
        return _failure("장보기 작업을 처리하는 중 문제가 생겼어요. 잠시 후 다시 시도해주세요.")

    return _failure("확인할 장보기 작업을 찾지 못했어요.")


def run_shopping_agent(
    text: str,
    *,
    db: Any,
    user_id: int | None = None,
    history: list | None = None,
    intent: str | None = None,
) -> dict[str, Any]:
    """Shopping Agent 단일 진입점. Supervisor GraphState subset과 boundary 호환."""
    del history
    resolved_intent = intent or "shopping.current"

    if not user_id:
        return _failure("로그인이 필요한 질문이에요. 로그인 후 장보기 기능을 이용할 수 있어요.", resolved_intent)

    if resolved_intent == "action.cancel":
        return _success("알겠어요. 장보기 작업을 취소했어요.", "shopping.cancel")

    if resolved_intent == "action.confirm":
        parts = text.split(":", 2)
        if len(parts) >= 2:
            action = parts[1]
            payload = parts[2] if len(parts) >= 3 else ""
            return execute_shopping_action(action, payload, db=db, user_id=user_id)
        return _failure("확인할 장보기 작업을 찾지 못했어요.")

    try:
        if resolved_intent == "shopping.current":
            message, actions = handle_current(db, user_id)
        elif resolved_intent == "shopping.owned":
            message, actions = handle_owned(db, user_id)
        elif resolved_intent == "shopping.history":
            message, actions = handle_history(db, user_id)
        elif resolved_intent == "shopping.compare":
            message, actions = handle_compare(text)
        elif resolved_intent == "shopping.create":
            message, actions = handle_create_request(text)
        elif resolved_intent == "shopping.purchase":
            message, actions = handle_purchase_request(db, user_id)
        elif resolved_intent == "shopping.delete_item":
            message, actions = handle_delete_item_request(db, user_id, text)
        elif resolved_intent == "shopping.check_item":
            message, actions = handle_check_item(db, user_id, text)
        else:
            message, actions = "장보기 요청을 이해하지 못했어요. 목록 조회, 가격 비교, 구매 완료를 요청할 수 있어요.", []
    except Exception:
        if db is not None:
            try:
                db.rollback()
            except Exception:
                pass
        return _failure("장보기 요청을 처리하는 중 문제가 생겼어요. 잠시 후 다시 시도해주세요.", resolved_intent)

    return _success(message, resolved_intent, actions)


if __name__ == "__main__":
    internal = build_shopping_response(
        message="테스트",
        intent="shopping.current",
        actions=[{"label": "장보기 목록 보기", "url": "/shopping-list"}],
    )
    supervisor = to_supervisor_state(internal)
    assert set(supervisor) == {"response_text", "actions", "sources"}
    assert supervisor["response_text"] == "테스트"
    assert supervisor["actions"][0]["url"] == "/shopping-list"
    print("shopping_agent ok")
