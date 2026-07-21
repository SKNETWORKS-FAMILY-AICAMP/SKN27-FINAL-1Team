from __future__ import annotations

from typing import Any

from ai.agents.shopping_agent.shopping_graph import (
    execute_confirmed_shopping_action,
    shopping_agent_graph,
)
from ai.agents.shopping_agent.shopping_utils import (
    build_shopping_response,
    latest_shopping_slots,
    to_supervisor_state,
)


def _success(
    message: str,
    intent: str,
    actions: list[dict[str, Any]] | None = None,
    slots: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return to_supervisor_state(build_shopping_response(message=message, intent=intent, actions=actions, slots=slots))


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
    """기존 확인 버튼 진입점은 유지하고 실행은 Shopping Graph 공통 핸들러에 위임합니다."""
    try:
        return execute_confirmed_shopping_action(action, payload, db=db, user_id=user_id)
    except Exception:
        if db is not None:
            try:
                db.rollback()
            except Exception:
                pass
        return _failure("장보기 작업을 처리하는 중 문제가 생겼어요. 잠시 후 다시 시도해주세요.")


def run_shopping_agent(
    text: str,
    *,
    db: Any,
    user_id: int | None = None,
    history: list | None = None,
    intent: str | None = None,
    slots: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Shopping Agent 호환 진입점. 내부 멀티턴 실행은 LangGraph가 담당합니다."""
    history = history or []
    resolved_slots = slots or latest_shopping_slots(history)
    resolved_intent = intent or "shopping.current"

    if resolved_intent != "shopping.price_help" and not user_id:
        return _failure("로그인이 필요한 질문이에요. 로그인 후 장보기 기능을 이용할 수 있어요.", resolved_intent)

    try:
        final_state = shopping_agent_graph.invoke(
            {
                "text": text,
                "db": db,
                "user_id": user_id,
                "history": history,
                "intent": resolved_intent,
                "slots": resolved_slots,
            }
        )
    except Exception:
        if db is not None:
            try:
                db.rollback()
            except Exception:
                pass
        return _failure("장보기 요청을 처리하는 중 문제가 생겼어요. 잠시 후 다시 시도해주세요.", resolved_intent)

    return {
        "response_text": final_state.get("response_text") or "장보기 요청을 처리하지 못했어요.",
        "actions": list(final_state.get("actions") or []),
        "sources": list(final_state.get("sources") or []),
        "slots": dict(final_state.get("slots") or {}),
    }


if __name__ == "__main__":
    internal = build_shopping_response(
        message="테스트",
        intent="shopping.current",
        actions=[{"label": "장보기 목록 보기", "url": "/shopping-list"}],
    )
    supervisor = to_supervisor_state(internal)
    assert set(supervisor) == {"response_text", "actions", "sources", "slots"}
    assert supervisor["response_text"] == "테스트"
    assert supervisor["actions"][0]["url"] == "/shopping-list"
    print("shopping_agent ok")
