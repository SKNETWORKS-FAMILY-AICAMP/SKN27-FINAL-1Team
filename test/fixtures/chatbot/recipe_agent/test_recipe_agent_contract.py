from __future__ import annotations

from langchain_core.messages import ToolMessage

import ai.agents.recipe_agent.recipe_agent as recipe_agent
from ai.agents.recipe_agent.recipe_state import RecipeAgentReply, RecipeToolPayload


def test_recipe_tools_preserve_llm_contract(build_tools) -> None:
    """Tool 이름과 입력 스키마는 LLM이 의존하는 고정 계약이다."""

    tools = build_tools()

    assert set(tools) == {
        "search_recipes",
        "recommend_by_ingredient",
        "recommend_from_fridge",
        "search_recipes_by_ingredients",
        "search_recipes_by_food_knowledge",
        "find_similar_recipes",
        "search_external",
    }
    assert tools["search_recipes"].args_schema.__name__ == "SearchRecipesInput"
    assert tools["search_external"].args_schema.__name__ == "SearchExternalInput"
    assert tools["search_recipes_by_ingredients"].args_schema.__name__ == "IngredientGraphSearchInput"
    assert tools["search_recipes_by_food_knowledge"].args_schema.__name__ == "FoodKnowledgeGraphSearchInput"
    assert tools["find_similar_recipes"].args_schema.__name__ == "SimilarRecipeGraphSearchInput"


def test_recipe_agent_preserves_supervisor_contract(monkeypatch) -> None:
    """내부 구현이 바뀌어도 Supervisor 반환 구조와 슬롯 계약을 유지한다."""

    payload = RecipeToolPayload(
        tool="search_recipes",
        status="success",
        metadata_policy="actions",
        message="두부 관련 레시피예요.",
        actions=[
            {
                "label": "두부조림",
                "url": "/recipes/7",
                "data": {"recipe_id": 7, "title": "두부조림"},
            }
        ],
    )

    class FakeAgent:
        def invoke(self, state, config):
            assert "intent" not in state
            assert config["recursion_limit"] == 8
            return {
                "messages": [ToolMessage(content=payload.model_dump_json(), tool_call_id="call-1")],
                "structured_response": RecipeAgentReply(message="두부조림을 추천해요."),
            }

    monkeypatch.setattr(recipe_agent, "build_recipe_agent", lambda *args, **kwargs: FakeAgent())

    result = recipe_agent.run_recipe_agent(
        "두부 레시피",
        db=None,
        user_id=1,
        intent="recipe.search",
    )

    assert result == {
        "response_text": "두부조림을 추천해요.",
        "actions": [
            {
                "label": "두부조림",
                "url": "/recipes/7",
                "data": {"recipe_id": 7, "title": "두부조림"},
            }
        ],
        "sources": [],
        "slots": {"shown_recipe_ids": [7]},
    }
