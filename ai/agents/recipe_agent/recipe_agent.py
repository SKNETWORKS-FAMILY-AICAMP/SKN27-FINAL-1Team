from __future__ import annotations

import inspect
from typing import Any

from .recipe_intents import analyze_recipe_intent

AGENT_NAME = "recipe"


def build_recipe_response(
    *,
    message: str,
    intent: str = "unknown",
    ok: bool = True,
    actions: list[dict[str, Any]] | None = None,
    sources: list[dict[str, Any]] | None = None,
    error: dict[str, Any] | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Recipe Agent 내부 응답 계약."""
    return {
        "ok": ok and error is None,
        "agent": AGENT_NAME,
        "intent": intent,
        "message": message,
        "error": error,
        "ui": {
            "actions": list(actions or []),
            "sources": list(sources or []),
        },
        "meta": meta or {},
    }


def to_supervisor_state(agent_result: dict[str, Any]) -> dict[str, Any]:
    """내부 계약 → LangGraph merge partial update."""
    ui = agent_result.get("ui") or {}
    return {
        "response_text": agent_result.get("message", ""),
        "actions": list(ui.get("actions") or []),
        "sources": list(ui.get("sources") or []),
    }


def run_recipe_agent(
    text: str,
    *,
    db: Any,
    user_id: int | None = None,
    history: list | None = None,
    settings_obj: Any = None,
    intent: str | None = None,
) -> dict:
    """Recipe Agent 단일 진입점. Supervisor GraphState subset과 boundary 호환."""
    del db, user_id, settings_obj  # ponytail: P3 — handler/DB는 P4-P5
    resolved_intent = intent or analyze_recipe_intent(text, history)
    internal = build_recipe_response(
        message="recipe agent placeholder",
        intent=resolved_intent,
    )
    return to_supervisor_state(internal)


if __name__ == "__main__":
    internal = build_recipe_response(
        message="테스트",
        intent="recipe.search",
        actions=[{"label": "김치볶음밥", "url": "/recipes/1"}],
        sources=[{"title": "출처", "url": "https://example.com"}],
    )
    assert internal["agent"] == "recipe"
    assert internal["ok"] is True
    assert internal["ui"]["actions"][0]["label"] == "김치볶음밥"

    supervisor = to_supervisor_state(internal)
    assert set(supervisor) == {"response_text", "actions", "sources"}
    assert supervisor["response_text"] == "테스트"
    assert len(supervisor["actions"]) == 1
    assert supervisor["sources"][0]["title"] == "출처"

    result = run_recipe_agent("김치볶음밥 레시피", db=None, intent="recipe.search")
    assert set(result) == {"response_text", "actions", "sources"}
    assert isinstance(result["response_text"], str) and result["response_text"]
    assert result["actions"] == [] and result["sources"] == []

    stub = run_recipe_agent("두부로 뭐 해먹지?", db=None)
    assert stub["response_text"]

    source = inspect.getsource(build_recipe_response) + inspect.getsource(to_supervisor_state)
    assert "GraphState" not in source

    print("recipe_agent contract ok")
