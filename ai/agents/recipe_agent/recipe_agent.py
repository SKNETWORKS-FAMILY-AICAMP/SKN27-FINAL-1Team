from __future__ import annotations

import inspect
from typing import Any

from .recipe_handlers import handle_recipe_pairing, handle_recipe_recommend, handle_recipe_search
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
    elif resolved_intent == "recipe.pairing":
        reply, actions = handle_recipe_pairing(text)
        sources = []
    elif resolved_intent == "recipe.recommend":
        reply, actions = handle_recipe_recommend(db, user_id or 0, text, history, settings_obj)
        sources = []
    else:
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
    def _check_output_contract(result: dict) -> None:
        assert set(result) == {"response_text", "actions", "sources"}
        assert isinstance(result["response_text"], str)
        assert isinstance(result["actions"], list)
        assert isinstance(result["sources"], list)

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
    _check_output_contract(supervisor)

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
        _check_output_contract(r)

        r = agent.run_recipe_agent("두부로 뭐 해먹지?", db=None, user_id=1, intent="recipe.recommend")
        assert set(r) == {"response_text", "actions", "sources"}
        assert r["response_text"] == "recommend:두부로 뭐 해먹지?"
        assert len(r["actions"]) == 1
        assert r["sources"] == []
        _check_output_contract(r)

        r = agent.run_recipe_agent("오늘 뭐 해먹지?", db=None, user_id=1)
        assert r["response_text"].startswith("recommend:")

        r = agent.run_recipe_agent("오늘 뭐 해먹지?", db=None, user_id=None, intent="recipe.recommend")
        assert LOGIN_REQUIRED_REPLY in r["response_text"]
        assert r["actions"] == [] and r["sources"] == []
        _check_output_contract(r)

        assert "placeholder" not in r["response_text"]

        r = agent.run_recipe_agent("김치볶음밥이랑 먹기 좋은 음식", db=None, intent="recipe.pairing")
        assert "김치볶음밥" in r["response_text"]
        assert "계란국" in r["response_text"]
        assert r["actions"] == []
        assert r["sources"] == []
        _check_output_contract(r)

        agent.handle_recipe_search = lambda db, text: ("결과 없음", [], [])
        r = agent.run_recipe_agent("없는레시피xyz", db=None, intent="recipe.search")
        _check_output_contract(r)
        assert r["actions"] == []

        # -- P0-4: Supervisor 통합 기준선 --
        agent.handle_recipe_search = fake_search
        r = agent.run_recipe_agent(
            "김치볶음밥 레시피",
            db=None, user_id=None, history=[], settings_obj=None, intent=None,
        )
        _check_output_contract(r)

        agent.handle_recipe_recommend = fake_recommend
        r = agent.run_recipe_agent(
            "두부로 뭐 해먹지?",
            db=None, user_id=1, history=[], settings_obj=None, intent="recipe.recommend",
        )
        _check_output_contract(r)
        assert len(r["response_text"]) > 0

        r = agent.run_recipe_agent(
            "김치볶음밥이랑 어울리는 반찬",
            db=None, user_id=None, history=[], settings_obj=None, intent=None,
        )
        _check_output_contract(r)

        class FakeMsg:
            def __init__(self, role, text):
                self.role = role
                self.text = text
        r = agent.run_recipe_agent(
            "다른 거 추천해줘",
            db=None, user_id=1,
            history=[FakeMsg("bot", "이전에 김치볶음밥을 추천했습니다.")],
            settings_obj=None, intent="recipe.search",
        )
        _check_output_contract(r)
    finally:
        agent.handle_recipe_search = orig_search
        agent.handle_recipe_recommend = orig_recommend

    print("recipe_agent ok")
