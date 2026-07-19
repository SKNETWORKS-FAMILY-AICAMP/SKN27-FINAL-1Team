from __future__ import annotations

import pytest

import ai.agents.recipe_agent.recipe_tools as recipe_tools
from ai.agents.recipe_agent.recipe_state import RecipeToolContext


@pytest.fixture
def build_tools():
    """동일 실행 상태를 공유하는 Recipe Tool 묶음을 생성한다."""

    def _build(**context_overrides):
        context = RecipeToolContext(db=None, **context_overrides)
        return {tool.name: tool for tool in recipe_tools.build_recipe_tools(context)}

    return _build
