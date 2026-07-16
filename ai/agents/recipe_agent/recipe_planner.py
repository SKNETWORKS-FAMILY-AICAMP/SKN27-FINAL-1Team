from __future__ import annotations

import json
from typing import Any

from app.backend.core.config import settings as app_settings

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

from .recipe_config import (
    ENABLE_LLM_RECIPE_PLANNER,
    PLANNER_GOLDEN_CASES,
    PUBLIC_TOOL_NAMES,
    RECIPE_PLANNER_PROMPT,
    TOOL_ARGS_WHITELIST,
    TOOL_RECOMMEND_BY_INGREDIENT,
    TOOL_RECOMMEND_FROM_FRIDGE,
    TOOL_SEARCH_EXTERNAL,
    TOOL_SEARCH_RECIPES,
    TOOL_SUGGEST_PAIRING,
    WHEN_ALWAYS,
    WHEN_PREV_EMPTY,
)
from .recipe_utils import _extract_keyword, _extract_recipe_ingredient, _is_cooking_time_question

from .recipe_agent import PlanStep, RecipeAgentRequest, RecipePlan


def _plan_keyword(req: RecipeAgentRequest) -> str:
    return _extract_recipe_ingredient(req.text) or _extract_keyword(req.text)


def plan_recipe_request_rule(req: RecipeAgentRequest) -> RecipePlan:
    """Rule-based planner (1단계 stub). LLM 실패 시 폴백."""
    keyword = _plan_keyword(req)

    if req.intent == "recipe.pairing":
        return RecipePlan(steps=[PlanStep(tool=TOOL_SUGGEST_PAIRING, args={"text": req.text})])

    if req.intent == "recipe.search" and _is_cooking_time_question(req.text):
        return RecipePlan(
            steps=[
                PlanStep(
                    tool=TOOL_SEARCH_EXTERNAL,
                    args={"keyword": keyword, "query_text": req.text},
                )
            ]
        )

    if req.intent == "recipe.search":
        return RecipePlan(
            steps=[
                PlanStep(tool=TOOL_SEARCH_RECIPES, args={"keyword": keyword}),
                PlanStep(
                    tool=TOOL_SEARCH_EXTERNAL,
                    args={"keyword": keyword, "query_text": req.text},
                    when=WHEN_PREV_EMPTY,
                ),
            ]
        )

    ingredient = _extract_recipe_ingredient(req.text)
    if ingredient:
        return RecipePlan(
            steps=[
                PlanStep(tool=TOOL_RECOMMEND_BY_INGREDIENT, args={"ingredient": ingredient}),
                PlanStep(
                    tool=TOOL_SEARCH_EXTERNAL,
                    args={"keyword": ingredient, "query_text": req.text},
                    when=WHEN_PREV_EMPTY,
                ),
            ]
        )

    return RecipePlan(steps=[PlanStep(tool=TOOL_RECOMMEND_FROM_FRIDGE, args={})])


def _filter_args(tool: str, args: dict[str, Any]) -> dict[str, Any]:
    allowed = TOOL_ARGS_WHITELIST.get(tool, frozenset())
    return {k: v for k, v in args.items() if k in allowed and v is not None}


def _enrich_args(tool: str, args: dict[str, Any], req: RecipeAgentRequest) -> dict[str, Any]:
    """Fill missing keyword/ingredient/text from rules."""
    out = dict(args)
    if tool in (TOOL_SEARCH_RECIPES, TOOL_SEARCH_EXTERNAL) and not out.get("keyword"):
        out["keyword"] = _plan_keyword(req)
    if tool == TOOL_SEARCH_EXTERNAL:
        out["query_text"] = req.text  # ponytail: LLM keyword 축약 방어, 검색은 항상 원문
    if tool == TOOL_RECOMMEND_BY_INGREDIENT and not out.get("ingredient"):
        out["ingredient"] = _extract_recipe_ingredient(req.text) or ""
    if tool == TOOL_SUGGEST_PAIRING and not out.get("text"):
        out["text"] = req.text
    return _filter_args(tool, out)


def _normalize_llm_plan(raw: dict[str, Any] | None, req: RecipeAgentRequest) -> RecipePlan | None:
    if not isinstance(raw, dict):
        return None
    steps_raw = raw.get("steps")
    if not isinstance(steps_raw, list) or not steps_raw:
        return None

    max_fallback = raw.get("max_fallback", 1)
    try:
        max_fallback = max(0, min(1, int(max_fallback)))
    except (TypeError, ValueError):
        max_fallback = 1

    steps: list[PlanStep] = []
    for item in steps_raw:
        if not isinstance(item, dict):
            return None
        tool = item.get("tool")
        if tool not in PUBLIC_TOOL_NAMES:
            return None
        when = item.get("when", WHEN_ALWAYS)
        if when not in (WHEN_ALWAYS, WHEN_PREV_EMPTY):
            return None
        args = item.get("args") or {}
        if not isinstance(args, dict):
            return None
        steps.append(
            PlanStep(
                tool=tool,
                args=_enrich_args(tool, args, req),
                when=when,
            )
        )

    if not steps:
        return None
    return RecipePlan(steps=steps, max_fallback=max_fallback)


def _call_llm_planner(req: RecipeAgentRequest) -> dict[str, Any] | None:
    if not ENABLE_LLM_RECIPE_PLANNER or OpenAI is None or not app_settings.OPENAI_API_KEY:
        return None
    payload = json.dumps(
        {"text": req.text, "intent": req.intent, "user_id": req.user_id},
        ensure_ascii=False,
    )
    client = OpenAI(api_key=app_settings.OPENAI_API_KEY)
    response = client.chat.completions.create(
        model=app_settings.OPENAI_MODEL,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": RECIPE_PLANNER_PROMPT},
            {"role": "user", "content": payload},
        ],
    )
    content = response.choices[0].message.content if response.choices else ""
    return json.loads(content or "{}")


def plan_recipe_request(req: RecipeAgentRequest) -> tuple[RecipePlan, str]:
    """LLM planner 1회 → 실패 시 rule. Returns (plan, planner_source)."""
    try:
        raw = _call_llm_planner(req)
        plan = _normalize_llm_plan(raw, req)
        if plan is not None:
            return plan, "llm"
    except Exception:
        pass
    return plan_recipe_request_rule(req), "rule"


if __name__ == "__main__":
    import ai.agents.recipe_agent.recipe_planner as planner
    from ai.agents.recipe_agent.recipe_agent import RecipeAgentRequest

    # rule golden cases
    for utterance, intent, tools, last_when in PLANNER_GOLDEN_CASES:
        req = RecipeAgentRequest(
            text=utterance, db=None, user_id=1,
            history=[], settings_obj=None, intent=intent,
        )
        plan = planner.plan_recipe_request_rule(req)
        assert tuple(s.tool for s in plan.steps) == tools, f"{utterance!r}: tools mismatch"
        if last_when is not None and len(plan.steps) > 1:
            assert plan.steps[-1].when == last_when, f"{utterance!r}: when mismatch"

    # normalize valid JSON
    req = RecipeAgentRequest(
        text="김치볶음밥 레시피", db=None, user_id=1,
        history=[], settings_obj=None, intent="recipe.search",
    )
    valid = {
        "steps": [
            {"tool": "search_recipes", "args": {"keyword": "김치볶음밥"}, "when": "always"},
            {"tool": "search_external", "args": {"keyword": "김치볶음밥"}, "when": "prev_empty"},
        ],
        "max_fallback": 1,
    }
    norm = planner._normalize_llm_plan(valid, req)
    assert norm is not None
    assert norm.steps[0].tool == TOOL_SEARCH_RECIPES

    # invalid tool → None
    assert planner._normalize_llm_plan({"steps": [{"tool": "unknown", "args": {}}]}, req) is None

    # LLM mock smoke
    orig = planner._call_llm_planner

    def fake_llm(r):
        return valid

    planner._call_llm_planner = fake_llm
    try:
        plan, source = planner.plan_recipe_request(req)
        assert source == "llm"
        assert plan.steps[0].tool == TOOL_SEARCH_RECIPES
    finally:
        planner._call_llm_planner = orig

    # LLM fail → rule
    planner._call_llm_planner = lambda r: None
    rule_plan, source = planner.plan_recipe_request(req)
    assert source == "rule"
    assert [s.tool for s in rule_plan.steps] == [TOOL_SEARCH_RECIPES, TOOL_SEARCH_EXTERNAL]

    print("recipe_planner ok")
