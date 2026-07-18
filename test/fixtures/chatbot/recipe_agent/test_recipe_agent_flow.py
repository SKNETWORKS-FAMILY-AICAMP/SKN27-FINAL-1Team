from __future__ import annotations

from langchain_core.messages import ToolMessage

import ai.agents.recipe_agent.recipe_tools as recipe_tools
from ai.agents.recipe_agent.recipe_agent import build_supervisor_result
from ai.agents.recipe_agent.recipe_graph import parse_recipe_agent_result
from ai.agents.recipe_agent.recipe_state import RecipeAgentReply, RecipeToolPayload


def test_internal_search_flows_to_supervisor_actions(monkeypatch, build_tools) -> None:
    """내부 검색 결과가 액션과 추천 이력 슬롯으로 전달되는 전체 흐름을 감시한다."""

    items = [{"recipe_id": 7, "title": "두부조림"}]
    monkeypatch.setattr(
        recipe_tools,
        "search_internal_recipes",
        lambda db, keyword: recipe_tools.ToolResult(ok=True, data={"items": items}),
    )
    payload_json = build_tools()["search_recipes"].invoke({"keyword": "두부"})
    reply = parse_recipe_agent_result(
        {
            "messages": [ToolMessage(content=payload_json, tool_call_id="call-1")],
            "structured_response": RecipeAgentReply(message="두부조림을 추천해요."),
        }
    )

    result = build_supervisor_result(reply)

    assert [action["url"] for action in result["actions"]] == ["/recipes/7"]
    assert result["sources"] == []
    assert result["slots"] == {"shown_recipe_ids": [7]}


def test_external_search_flows_to_sources(monkeypatch, build_tools) -> None:
    """외부 조사는 내부 액션이 아니라 출처 근거로만 전달한다."""

    monkeypatch.setattr(
        recipe_tools,
        "search_external_recipes",
        lambda keyword, query_text: recipe_tools.ToolResult(
            ok=True,
            data={
                "results": [{"title": "조리법", "url": "https://example.com/recipe"}],
                "sources": [{"title": "조리법", "url": "https://example.com/recipe"}],
            },
        ),
    )
    payload_json = build_tools()["search_external"].invoke(
        {"keyword": "감자튀김", "query_text": "감자튀김 조리 시간"}
    )
    reply = parse_recipe_agent_result(
        {
            "messages": [ToolMessage(content=payload_json, tool_call_id="call-1")],
            "structured_response": RecipeAgentReply(message="조리 정보를 찾았어요."),
        }
    )

    assert reply.actions == []
    assert [source.url for source in reply.sources] == ["https://example.com/recipe"]


def test_fridge_recommendation_uses_fixed_policy_and_returns_actions(
    monkeypatch,
    build_tools,
) -> None:
    """냉장고 추천의 인증·재고·추천·액션 흐름을 한 경계에서 확인한다."""

    import ai.agents.inventory_agent.inventory_agent as inventory_agent

    monkeypatch.setattr(inventory_agent, "is_inventory_empty", lambda db, user_id: False)
    monkeypatch.setattr(
        recipe_tools,
        "recommend_fridge_recipes",
        lambda db, user_id: recipe_tools.ToolResult(
            ok=True,
            data={
                "items": [
                    {
                        "recipe_id": 11,
                        "title": "냉장고 볶음밥",
                        "owned_ingredient_count": 3,
                        "missing_ingredient_count": 0,
                        "final_score": 90,
                    }
                ]
            },
        ),
    )

    payload = RecipeToolPayload.model_validate_json(
        build_tools(user_id=3)["recommend_from_fridge"].invoke({})
    )

    assert payload.status == "success"
    assert payload.metadata_policy == "actions"
    assert [action.url for action in payload.actions] == ["/recipes/11"]
