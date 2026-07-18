from __future__ import annotations

import logging

import pytest
from langchain_core.messages import ToolMessage

import ai.agents.recipe_agent.recipe_tools as recipe_tools
from ai.agents.recipe_agent.recipe_graph import parse_recipe_agent_result
from ai.agents.recipe_agent.recipe_state import RecipeAgentReply, RecipeToolPayload


@pytest.mark.parametrize(
    ("tool_name", "arguments"),
    [
        ("search_recipes", {"keyword": "   "}),
        ("recommend_by_ingredient", {"ingredient": ""}),
    ],
)
def test_blank_inputs_do_not_call_internal_services(
    monkeypatch,
    build_tools,
    tool_name,
    arguments,
) -> None:
    """A/B: 두 입력 경로 모두 공백을 서비스 호출 전에 차단한다."""

    def fail_if_called(*args, **kwargs):
        raise AssertionError("공백 입력은 내부 서비스에 전달하면 안 됩니다.")

    monkeypatch.setattr(recipe_tools, "search_internal_recipes", fail_if_called)
    monkeypatch.setattr(recipe_tools, "search_recipes_by_ingredient_with_fallback", fail_if_called)

    payload = RecipeToolPayload.model_validate_json(build_tools()[tool_name].invoke(arguments))

    assert payload.status == "empty"
    assert payload.metadata_policy == "none"


@pytest.mark.parametrize(
    ("internal_count", "expect_external_call"),
    [(3, False), (2, True), (0, True)],
)
def test_external_search_threshold_behavior(
    monkeypatch,
    build_tools,
    internal_count,
    expect_external_call,
) -> None:
    """A/B: 충분한 내부 결과에서만 외부 검색을 차단한다."""

    items = [
        {"recipe_id": recipe_id, "title": f"레시피 {recipe_id}"}
        for recipe_id in range(1, internal_count + 1)
    ]
    external_calls = []
    monkeypatch.setattr(
        recipe_tools,
        "search_internal_recipes",
        lambda db, keyword: recipe_tools.ToolResult(ok=True, data={"items": items}),
    )

    def search_external(keyword, query_text):
        external_calls.append(query_text)
        return recipe_tools.ToolResult(
            ok=True,
            data={
                "results": [{"title": "외부 조리법"}],
                "sources": [{"title": "외부 조리법", "url": "https://example.com"}],
            },
        )

    monkeypatch.setattr(recipe_tools, "search_external_recipes", search_external)
    tools = build_tools()
    internal = RecipeToolPayload.model_validate_json(
        tools["search_recipes"].invoke({"keyword": "두부"})
    )
    external = RecipeToolPayload.model_validate_json(
        tools["search_external"].invoke({"keyword": "두부", "query_text": "두부 레시피"})
    )

    assert bool(external_calls) is expect_external_call
    if internal_count >= 3:
        assert internal.metadata_policy == "actions"
        assert external.status == "empty"
        assert external.metadata_policy == "none"
    else:
        assert external.status == "success"
        assert external.metadata_policy == "sources"


@pytest.mark.parametrize(
    ("latest_policy", "expect_actions", "expect_sources"),
    [
        ("actions", True, False),
        ("sources", False, True),
        ("both", True, True),
        ("none", False, False),
    ],
)
def test_latest_successful_payload_metadata_policy(
    latest_policy,
    expect_actions,
    expect_sources,
) -> None:
    """A/B: 최종 성공 결과의 용도에 맞는 메타데이터만 노출한다."""

    previous = RecipeToolPayload(
        tool="search_recipes",
        status="success",
        metadata_policy="actions",
        message="이전 결과",
        actions=[{"label": "이전 레시피", "url": "/recipes/1"}],
    )
    latest = RecipeToolPayload(
        tool="test_tool",
        status="success",
        metadata_policy=latest_policy,
        message="최종 결과",
        actions=[{"label": "최종 레시피", "url": "/recipes/2"}],
        sources=[{"title": "최종 출처", "url": "https://example.com/source"}],
    )
    result = parse_recipe_agent_result(
        {
            "messages": [
                ToolMessage(content=previous.model_dump_json(), tool_call_id="call-1"),
                ToolMessage(content=latest.model_dump_json(), tool_call_id="call-2"),
            ],
            "structured_response": RecipeAgentReply(
                message="최종 답변",
                actions=[{"label": "모델 생성 액션", "url": "/fake"}],
            ),
        }
    )

    assert bool(result.actions) is expect_actions
    assert bool(result.sources) is expect_sources
    assert all(action.url != "/fake" for action in result.actions)
    assert all(action.url != "/recipes/1" for action in result.actions)


def test_internal_service_error_is_logged_but_not_exposed(monkeypatch, caplog) -> None:
    """B 케이스: 내부 장애 상세는 로그에만 남고 사용자 메시지에는 노출되지 않는다."""

    class BrokenSearchService:
        def search_recipes(self, **kwargs):
            raise RuntimeError("database-password-leak")

    import app.backend.services.recommendation_service.recipe_search_service as search_module

    monkeypatch.setattr(search_module, "recipe_search_service", BrokenSearchService())
    with caplog.at_level(logging.ERROR, logger=recipe_tools.__name__):
        result = recipe_tools.search_internal_recipes(db=None, keyword="김치찌개")

    assert result.ok is False
    assert "database-password-leak" not in (result.error or "")
    assert "database-password-leak" in caplog.text
