from __future__ import annotations

import ai.agents.recipe_agent.recipe_planner as planner
from ai.agents.recipe_agent.recipe_types import RecipeAgentRequest
from ai.agents.recipe_agent.recipe_config import (
    PLANNER_GOLDEN_CASES,
    TOOL_RECOMMEND_BY_INGREDIENT,
    TOOL_RECOMMEND_FROM_FRIDGE,
    TOOL_SEARCH_EXTERNAL,
    TOOL_SEARCH_RECIPES,
    TOOL_SUGGEST_PAIRING,
    WHEN_PREV_EMPTY,
)


def _req(text: str, intent: str = "recipe.search") -> RecipeAgentRequest:
    return RecipeAgentRequest(
        text=text,
        db=None,
        user_id=1,
        history=[],
        settings_obj=None,
        intent=intent,
    )


def test_compare_planner_shadow_with_mock_llm() -> None:
    req = _req("김치볶음밥 레시피", "recipe.search")
    fake = {
        "steps": [
            {"tool": TOOL_SEARCH_RECIPES, "args": {"keyword": "김치볶음밥"}},
            {"tool": TOOL_SEARCH_EXTERNAL, "args": {"keyword": "김치볶음밥"}, "when": WHEN_PREV_EMPTY},
        ],
        "max_fallback": 1,
    }
    original = planner._call_llm_planner
    planner._call_llm_planner = lambda _: fake
    try:
        shadow = planner.compare_planner_shadow(req)
        assert shadow["source"] == "llm"
        assert shadow["match"] is True
        assert shadow["diff"]["rule_only"] == []
        assert shadow["diff"]["llm_only"] == []
    finally:
        planner._call_llm_planner = original


def test_compare_planner_shadow_reports_diff() -> None:
    req = _req("김치볶음밥 레시피", "recipe.search")
    fake = {"steps": [{"tool": TOOL_SEARCH_EXTERNAL, "args": {"keyword": "김치볶음밥"}}], "max_fallback": 1}
    original = planner._call_llm_planner
    planner._call_llm_planner = lambda _: fake
    try:
        shadow = planner.compare_planner_shadow(req)
        assert shadow["source"] == "llm"
        assert shadow["match"] is False
        assert TOOL_SEARCH_RECIPES in shadow["diff"]["rule_only"]
    finally:
        planner._call_llm_planner = original


def test_compare_planner_shadow_golden_cases_mock_llm() -> None:
    """골든 케이스에서 rule plan을 그대로 mock하여 diff가 비어 있어야 한다."""
    req = _req("김치볶음밥 레시피", "recipe.search")
    original = planner._call_llm_planner

    def fake_llm(r: RecipeAgentRequest):
        rule = planner.plan_recipe_request_rule(r)
        steps = []
        for s in rule.steps:
            # when 필드 포함 (prev_empty 동작을 그대로 반영)
            step = {"tool": s.tool, "args": dict(s.args), "when": s.when}
            steps.append(step)
        return {"steps": steps, "max_fallback": rule.max_fallback}

    planner._call_llm_planner = fake_llm
    try:
        for utterance, intent, *_ in PLANNER_GOLDEN_CASES:
            r = _req(utterance, intent)
            shadow = planner.compare_planner_shadow(r)
            assert shadow["match"] is True
            assert shadow["diff"]["rule_only"] == []
            assert shadow["diff"]["llm_only"] == []
    finally:
        planner._call_llm_planner = original
