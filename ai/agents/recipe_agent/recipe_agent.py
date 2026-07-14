from __future__ import annotations

import inspect
from typing import Any

from .recipe_handlers import handle_recipe_recommend, handle_recipe_search
from .recipe_intents import analyze_recipe_intent
from .recipe_utils import LOGIN_REQUIRED_REPLY, _requires_login

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
    resolved_intent = intent or analyze_recipe_intent(text, history)

    if resolved_intent == "recipe.recommend" and _requires_login(resolved_intent, text) and not user_id:
        internal = build_recipe_response(message=LOGIN_REQUIRED_REPLY, intent=resolved_intent)
        return to_supervisor_state(internal)

    if resolved_intent == "recipe.search":
        reply, actions, sources = handle_recipe_search(db, text)
    elif resolved_intent == "recipe.recommend":
        reply, actions = handle_recipe_recommend(db, user_id or 0, text, history, settings_obj)
        sources = []
    else:
        # ponytail: recipe agent 컨텍스트 fallback — analyze가 search/recommend만 반환
        reply, actions = handle_recipe_recommend(db, user_id or 0, text, history, settings_obj)
        sources = []

    internal = build_recipe_response(
        message=reply,
        intent=resolved_intent,
        actions=actions,
        sources=sources,
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

    source = inspect.getsource(build_recipe_response) + inspect.getsource(to_supervisor_state)
    assert "GraphState" not in source

    import ai.agents.recipe_agent.recipe_agent as agent

    orig_search = agent.handle_recipe_search
    orig_recommend = agent.handle_recipe_recommend

    def fake_search(db: Any, text: str) -> tuple[str, list[dict[str, Any]], list[dict[str, str]]]:
        return f"search:{text}", [{"label": "김치볶음밥", "url": "/recipes/1"}], []

    def fake_recommend(
        db: Any,
        user_id: int,
        text: str,
        history: list | None = None,
        settings_obj: Any = None,
    ) -> tuple[str, list[dict[str, Any]]]:
        return f"recommend:{text}", [{"label": "두부찌개", "url": "/recipes/2"}]

    agent.handle_recipe_search = fake_search
    agent.handle_recipe_recommend = fake_recommend
    try:
        r = agent.run_recipe_agent("김치볶음밥 레시피", db=None, intent="recipe.search")
        assert set(r) == {"response_text", "actions", "sources"}
        assert r["response_text"] == "search:김치볶음밥 레시피"
        assert r["actions"][0]["url"] == "/recipes/1"
        assert r["sources"] == []

        r = agent.run_recipe_agent("두부로 뭐 해먹지?", db=None, user_id=1, intent="recipe.recommend")
        assert set(r) == {"response_text", "actions", "sources"}
        assert r["response_text"] == "recommend:두부로 뭐 해먹지?"
        assert len(r["actions"]) == 1
        assert r["sources"] == []

        r = agent.run_recipe_agent("오늘 뭐 해먹지?", db=None, user_id=1)
        assert r["response_text"].startswith("recommend:")

        r = agent.run_recipe_agent("오늘 뭐 해먹지?", db=None, user_id=None, intent="recipe.recommend")
        assert LOGIN_REQUIRED_REPLY in r["response_text"]
        assert r["actions"] == [] and r["sources"] == []

        assert "placeholder" not in r["response_text"]
    finally:
        agent.handle_recipe_search = orig_search
        agent.handle_recipe_recommend = orig_recommend

    print("recipe_agent ok")
