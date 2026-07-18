from __future__ import annotations

from langchain_core.messages import ToolMessage

import ai.agents.recipe_agent.recipe_agent as recipe_agent
import ai.agents.recipe_agent.recipe_tools as recipe_tools
from ai.agents.recipe_agent.recipe_graph import parse_recipe_agent_result
from ai.agents.recipe_agent.recipe_state import RecipeAgentReply, RecipeToolContext, RecipeToolPayload


def _tools() -> dict:
    return {tool.name: tool for tool in recipe_tools.build_recipe_tools(RecipeToolContext(db=None))}


def test_recipe_tools_have_pydantic_schemas() -> None:
    tools = _tools()
    assert set(tools) == {
        "search_recipes",
        "recommend_by_ingredient",
        "recommend_from_fridge",
        "search_external",
    }
    assert tools["search_recipes"].args_schema.__name__ == "SearchRecipesInput"
    assert tools["search_external"].args_schema.__name__ == "SearchExternalInput"


def test_recommend_by_ingredient_handles_empty_input() -> None:
    payload = RecipeToolPayload.model_validate_json(
        _tools()["recommend_by_ingredient"].invoke({"ingredient": ""})
    )
    assert payload.status == "empty"
    assert payload.actions == []


def test_fridge_tool_requires_login() -> None:
    payload = RecipeToolPayload.model_validate_json(_tools()["recommend_from_fridge"].invoke({}))
    assert payload.status == "error"
    assert "로그인" in payload.message


def test_external_tool_returns_raw_results(monkeypatch) -> None:
    class FakeTavilyClient:
        def __init__(self, api_key: str):
            assert api_key == "test-key"

        def search(self, **kwargs):
            assert kwargs["query"] == "감자튀김 에어프라이기 시간"
            return {
                "results": [
                    {
                        "title": "감자튀김 에어프라이어 조리법",
                        "url": "https://example.com/fries",
                        "content": "감자튀김은 180도에서 조리합니다.",
                    }
                ]
            }

    monkeypatch.setattr(recipe_tools.app_settings, "TAVILY_API_KEY", "test-key")
    monkeypatch.setattr(recipe_tools, "TavilyClient", FakeTavilyClient)
    payload = RecipeToolPayload.model_validate_json(
        _tools()["search_external"].invoke(
            {"keyword": "감자튀김", "query_text": "감자튀김 에어프라이기 시간"}
        )
    )
    assert payload.status == "success"
    assert payload.data["query_text"] == "감자튀김 에어프라이기 시간"
    assert payload.data["results"][0]["content"] == "감자튀김은 180도에서 조리합니다."
    assert payload.sources[0].url == "https://example.com/fries"


def test_parser_uses_tool_actions_instead_of_model_actions() -> None:
    payload = RecipeToolPayload(
        tool="search_recipes",
        status="success",
        message="두부 관련 레시피예요.",
        actions=[
            {
                "label": "두부조림",
                "url": "/recipes/7",
                "data": {"recipe_id": 7, "title": "두부조림"},
            }
        ],
    )
    result = parse_recipe_agent_result(
        {
            "messages": [ToolMessage(content=payload.model_dump_json(), tool_call_id="call-1")],
            "structured_response": RecipeAgentReply(
                message="두부로 만들 수 있는 메뉴를 추천해 드릴게요.",
                actions=[{"label": "가짜 링크", "url": "/fake"}],
            ),
        }
    )
    assert result.message == "두부로 만들 수 있는 메뉴를 추천해 드릴게요."
    assert [action.url for action in result.actions] == ["/recipes/7"]


def test_run_recipe_agent_keeps_supervisor_contract(monkeypatch) -> None:
    payload = RecipeToolPayload(
        tool="search_recipes",
        status="success",
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
    assert result["response_text"] == "두부조림을 추천해요."
    assert result["actions"][0]["url"] == "/recipes/7"
    assert result["slots"] == {"shown_recipe_ids": [7]}

