from __future__ import annotations

from typing import Any


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
    del text, db, user_id, history, settings_obj, intent  # ponytail: P1 shell — 시그니처만 고정
    return {
        "response_text": "recipe agent placeholder",
        "actions": [],
        "sources": [],
    }


if __name__ == "__main__":
    result = run_recipe_agent("김치볶음밥 레시피", db=None, intent="recipe.search")
    assert set(result) == {"response_text", "actions", "sources"}
    assert isinstance(result["response_text"], str) and result["response_text"]
    assert result["actions"] == [] and result["sources"] == []
    print("recipe_agent shell ok")
