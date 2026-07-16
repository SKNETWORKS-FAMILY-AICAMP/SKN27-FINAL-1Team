from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable
from urllib.parse import quote

from .recipe_config import (
    AGENT_NAME,
    CONSTRAINT_EASY_30,
    MAX_DISPLAY_RECIPES,
    TOOL_RECOMMEND_BY_INGREDIENT,
    TOOL_RECOMMEND_FROM_FRIDGE,
    TOOL_SEARCH_EXTERNAL,
    TOOL_SEARCH_RECIPES,
    TOOL_SUGGEST_PAIRING,
    WHEN_ALWAYS,
    WHEN_PREV_EMPTY,
)
from .recipe_tools import (
    ToolResult,
    handle_recipe_pairing,
    recommend_recipe_tool,
    reply_external_recipe,
    search_ingredient_relax_tool,
    search_recipe_tool,
)
from .recipe_types import (
    PlanStep,
    RecipeAgentRequest,
    RecipeAgentResult,
    RecipeExecutionState,
    RecipePlan,
)
from .recipe_utils import (
    LOGIN_REQUIRED_REPLY,
    _apply_josa,
    _exclude_previous_items,
    _rank_recipe_items,
    _recipe_actions,
    _requires_login,
    _sort_fridge_candidates,
    analyze_recipe_intent,
)

# Re-export for tests / backward compat
__all__ = [
    "PlanStep",
    "RecipePlan",
    "RecipeAgentRequest",
    "RecipeAgentResult",
    "RecipeExecutionState",
    "TOOL_SEARCH_RECIPES",
    "TOOL_RECOMMEND_BY_INGREDIENT",
    "TOOL_RECOMMEND_FROM_FRIDGE",
    "TOOL_SEARCH_EXTERNAL",
    "TOOL_SUGGEST_PAIRING",
    "WHEN_ALWAYS",
    "WHEN_PREV_EMPTY",
    "TOOL_REGISTRY",
    "build_recipe_response",
    "execute_plan",
    "render_response",
    "run_recipe_agent",
    "to_supervisor_state",
]


def build_recipe_response(
    *,
    message: str,
    intent: str = "unknown",
    ok: bool = True,
    actions: list[dict[str, Any]] | None = None,
    sources: list[dict[str, Any]] | None = None,
    error: dict[str, Any] | None = None,
    meta: dict[str, Any] | None = None,
) -> RecipeAgentResult:
    """Recipe Agent 내부 응답 계약."""
    return RecipeAgentResult(
        ok=ok and error is None,
        agent=AGENT_NAME,
        intent=intent,
        message=message,
        error=error,
        actions=list(actions or []),
        sources=list(sources or []),
        meta=meta or {},
    )


def to_supervisor_state(result: RecipeAgentResult) -> dict[str, Any]:
    """내부 계약 → LangGraph merge partial update."""
    return {
        "response_text": result.message,
        "actions": result.actions,
        "sources": result.sources,
    }


def _fridge_login_guard(req: RecipeAgentRequest) -> RecipeAgentResult | None:
    if _requires_login(req.intent, req.text) and not req.user_id:
        return build_recipe_response(message=LOGIN_REQUIRED_REPLY, intent=req.intent)
    return None


def _fridge_empty_guard(req: RecipeAgentRequest) -> RecipeAgentResult | None:
    from ai.agents.inventory_agent.inventory_agent import EMPTY_INVENTORY_REPLY, is_inventory_empty

    if is_inventory_empty(db=req.db, user_id=req.user_id or 0):
        return build_recipe_response(message=EMPTY_INVENTORY_REPLY, intent=req.intent)
    return None


def _apply_policy_guards(req: RecipeAgentRequest, plan: RecipePlan) -> RecipeAgentResult | None:
    """Run login/empty guards only when plan needs fridge recommendation."""
    if not any(step.tool == TOOL_RECOMMEND_FROM_FRIDGE for step in plan.steps):
        return None
    guarded = _fridge_login_guard(req)
    if guarded is not None:
        return guarded
    return _fridge_empty_guard(req)


def _tool_search_recipes(req: RecipeAgentRequest, args: dict[str, Any]) -> ToolResult:
    keyword = args.get("keyword") or ""
    search = search_recipe_tool(req.db, keyword)
    if not search.ok:
        return search
    candidates = (search.data or {}).get("items", [])
    items = _rank_recipe_items(keyword, candidates)[:MAX_DISPLAY_RECIPES]
    return ToolResult(
        ok=True,
        data={"keyword": keyword, "items": items, "total": len(items)},
        source=TOOL_SEARCH_RECIPES,
    )


def _tool_recommend_by_ingredient(req: RecipeAgentRequest, args: dict[str, Any]) -> ToolResult:
    ingredient = args.get("ingredient") or ""
    if not ingredient:
        return ToolResult(ok=True, data={"ingredient": "", "items": [], "constraints": {}}, source=TOOL_RECOMMEND_BY_INGREDIENT)
    tr = search_ingredient_relax_tool(req.db, ingredient)
    if not tr.ok:
        return tr
    data = tr.data or {}
    candidates = data.get("items") or []
    filtered = _exclude_previous_items(candidates, req.history)
    selected = filtered[:MAX_DISPLAY_RECIPES]
    return ToolResult(
        ok=True,
        data={
            "ingredient": ingredient,
            "items": selected,
            "constraints": data.get("constraints") or {},
            "total": len(selected),
        },
        source=TOOL_RECOMMEND_BY_INGREDIENT,
    )


def _tool_recommend_from_fridge(req: RecipeAgentRequest, args: dict[str, Any]) -> ToolResult:
    del args
    tr = recommend_recipe_tool(req.db, req.user_id or 0, req.settings_obj)
    if not tr.ok:
        return ToolResult(
            ok=False,
            error=tr.error or "냉장고 기반 추천을 불러오지 못했어요. 재료명을 넣어서 다시 물어봐주세요.",
            source=TOOL_RECOMMEND_FROM_FRIDGE,
        )
    candidates = (tr.data or {}).get("items", [])
    ranked = _sort_fridge_candidates(candidates)
    return ToolResult(ok=True, data={"items": ranked, "total": len(ranked)}, source=TOOL_RECOMMEND_FROM_FRIDGE)


def _tool_search_external(req: RecipeAgentRequest, args: dict[str, Any]) -> ToolResult:
    keyword = args.get("keyword") or ""
    query_text = args.get("query_text") or req.text
    try:
        summary, sources = reply_external_recipe(keyword, query_text=query_text)
        return ToolResult(
            ok=True,
            data={"keyword": keyword, "summary": summary, "sources": sources},
            source=TOOL_SEARCH_EXTERNAL,
        )
    except Exception as e:
        return ToolResult(ok=False, error=str(e), source=TOOL_SEARCH_EXTERNAL)


def _tool_suggest_pairing(req: RecipeAgentRequest, args: dict[str, Any]) -> ToolResult:
    text = args.get("text") or req.text
    try:
        reply, actions = handle_recipe_pairing(text)
        return ToolResult(
            ok=True,
            data={"reply": reply, "actions": actions},
            source=TOOL_SUGGEST_PAIRING,
        )
    except Exception as e:
        return ToolResult(ok=False, error=str(e), source=TOOL_SUGGEST_PAIRING)


ToolFn = Callable[[RecipeAgentRequest, dict[str, Any]], ToolResult]

TOOL_REGISTRY: dict[str, ToolFn] = {
    TOOL_SEARCH_RECIPES: _tool_search_recipes,
    TOOL_RECOMMEND_BY_INGREDIENT: _tool_recommend_by_ingredient,
    TOOL_RECOMMEND_FROM_FRIDGE: _tool_recommend_from_fridge,
    TOOL_SEARCH_EXTERNAL: _tool_search_external,
    TOOL_SUGGEST_PAIRING: _tool_suggest_pairing,
}


def _step_result_empty(tr: ToolResult, tool: str) -> bool:
    if not tr.ok:
        return True
    data = tr.data or {}
    if tool == TOOL_SEARCH_EXTERNAL:
        return not (data.get("summary") or "").strip()
    if tool == TOOL_SUGGEST_PAIRING:
        return not (data.get("reply") or "").strip()
    if tool == TOOL_RECOMMEND_FROM_FRIDGE:
        return not data.get("items")
    return not data.get("items")


def execute_plan(state: RecipeExecutionState) -> RecipeExecutionState:
    """Run plan steps sequentially. prev_empty steps respect max_fallback."""
    plan = state.plan
    if not plan:
        return state

    fallback_used = 0
    prev_empty = False

    for step in plan.steps:
        if step.when == WHEN_PREV_EMPTY:
            if not prev_empty:
                state.steps_done.append(f"skip:{step.tool}")
                continue
            if fallback_used >= plan.max_fallback:
                state.steps_done.append(f"skip_fallback_cap:{step.tool}")
                continue
            fallback_used += 1

        fn = TOOL_REGISTRY.get(step.tool)
        if fn is None:
            tr = ToolResult(ok=False, error=f"unknown tool: {step.tool}", source=step.tool)
        else:
            tr = fn(state.req, dict(step.args))

        state.intermediate[step.tool] = tr
        state.last_tool = step.tool
        state.steps_done.append(f"run:{step.tool}")
        prev_empty = _step_result_empty(tr, step.tool)

    return state


def _numbered_list(items: list[dict[str, Any]]) -> str:
    return "\n".join(f"{index + 1}. {item.get('title') or ''}" for index, item in enumerate(items))


def _recipe_list_response(
    *,
    prefix: str,
    items: list[dict[str, Any]],
    intent: str,
    extra_actions: list[dict[str, Any]] | None = None,
) -> RecipeAgentResult:
    actions = _recipe_actions(items) + (extra_actions or [])
    return build_recipe_response(message=prefix + _numbered_list(items), intent=intent, actions=actions)


def render_response(state: RecipeExecutionState) -> RecipeAgentResult:
    """Assemble final message from last meaningful tool result."""
    req = state.req
    intent = req.intent

    if state.plan:
        for step in reversed(state.plan.steps):
            tr = state.intermediate.get(step.tool)
            if tr is None or not tr.ok:
                continue
            if _step_result_empty(tr, step.tool) and step.when == WHEN_ALWAYS:
                continue
            return _render_tool_result(step.tool, tr, req)

    last = state.last_tool
    if last and last in state.intermediate:
        return _render_tool_result(last, state.intermediate[last], req)

    return build_recipe_response(message="요청을 처리하지 못했어요.", intent=intent)


def _render_tool_result(tool: str, tr: ToolResult, req: RecipeAgentRequest) -> RecipeAgentResult:
    intent = req.intent
    data = tr.data or {}

    if tool == TOOL_SUGGEST_PAIRING:
        if not tr.ok:
            return build_recipe_response(message=tr.error or "조합 추천에 실패했어요.", intent=intent)
        return build_recipe_response(
            message=data.get("reply", ""),
            intent=intent,
            actions=data.get("actions") or [],
        )

    if tool == TOOL_SEARCH_EXTERNAL:
        summary = data.get("summary", "") if tr.ok else (tr.error or "")
        sources = (data.get("sources") or []) if tr.ok else []
        keyword = data.get("keyword") or ""
        if not summary and tr.ok:
            summary = f"{keyword} 관련 레시피를 찾지 못했어요." if keyword else "관련 레시피를 찾지 못했어요."
        return build_recipe_response(message=summary, intent=intent, actions=[], sources=sources)

    if tool == TOOL_SEARCH_RECIPES:
        keyword = data.get("keyword") or ""
        selected = data.get("items") or []
        if not tr.ok or not selected:
            return build_recipe_response(
                message=tr.error or (f"{keyword} 관련 레시피를 찾지 못했어요." if keyword else "관련 레시피를 찾지 못했어요."),
                intent=intent,
            )
        return _recipe_list_response(
            prefix=f"{keyword} 관련 레시피예요.\n",
            items=selected,
            intent=intent,
        )

    if tool == TOOL_RECOMMEND_BY_INGREDIENT:
        ingredient = data.get("ingredient") or ""
        selected = data.get("items") or []
        constraints = data.get("constraints") or {}
        if not ingredient:
            return build_recipe_response(message="", intent=intent)
        if not tr.ok or not selected:
            return build_recipe_response(message=tr.error or "", intent=intent)
        list_action = {
            "label": f"{ingredient} 레시피 더 보기",
            "url": f"/recipes?ingredient={quote(ingredient)}",
            "data": {"ingredient": ingredient},
        }
        is_easy = constraints == CONSTRAINT_EASY_30
        prefix = (
            f"{_apply_josa(ingredient, '이가')} 주재료인 30분 이내 초급 레시피는 \n"
            if is_easy
            else f"{_apply_josa(ingredient, '이가')} 주재료인 레시피는 \n"
        )
        return _recipe_list_response(
            prefix=prefix,
            items=selected,
            intent=intent,
            extra_actions=[list_action],
        )

    if tool == TOOL_RECOMMEND_FROM_FRIDGE:
        if not tr.ok:
            return build_recipe_response(message=tr.error or "냉장고 기반 추천을 불러오지 못했어요.", intent=intent)
        ranked = data.get("items") or []
        perfect = [i for i in ranked if i.get("missing_ingredient_count", 0) == 0]
        if perfect:
            selected = perfect[:MAX_DISPLAY_RECIPES]
            prefix = "현재 냉장고 재료만으로 완벽하게 만들 수 있는 레시피예요.\n"
        else:
            selected = ranked[:MAX_DISPLAY_RECIPES]
            if not selected or selected[0].get("owned_ingredient_count", 0) == 0:
                return build_recipe_response(
                    message="현재 냉장고 재료와 매칭되는 레시피를 찾지 못했어요. 재료를 더 추가해 보세요.",
                    intent=intent,
                )
            prefix = "부족한 재료가 약간 있지만, 냉장고 재료를 최대한 활용할 수 있는 레시피예요.\n"
        return _recipe_list_response(prefix=prefix, items=selected, intent=intent)

    return build_recipe_response(message=tr.error or "요청을 처리하지 못했어요.", intent=intent)


def run_recipe_agent(
    text: str,
    *,
    db: Any,
    user_id: int | None = None,
    history: list | None = None,
    settings_obj: Any = None,
    intent: str | None = None,
) -> dict:
    """Recipe Agent 단일 진입점. plan → execute → render."""
    from .recipe_planner import plan_recipe_request

    req = RecipeAgentRequest(
        text=text,
        db=db,
        user_id=user_id,
        history=history or [],
        settings_obj=settings_obj,
        intent=intent or analyze_recipe_intent(text, history),
    )
    plan, planner_source = plan_recipe_request(req)
    guarded = _apply_policy_guards(req, plan)
    if guarded is not None:
        return to_supervisor_state(guarded)

    state = RecipeExecutionState(req=req, plan=plan)
    state = execute_plan(state)
    result = render_response(state)
    meta = dict(result.meta or {})
    meta["planner"] = planner_source
    result = replace(result, meta=meta)
    out = to_supervisor_state(result)
    shown_recipe_ids = [
        int(action.get("data", {}).get("recipe_id"))
        for action in result.actions
        if isinstance(action, dict)
        and isinstance(action.get("data"), dict)
        and action["data"].get("recipe_id") is not None
    ]
    if shown_recipe_ids:
        out["slots"] = {"shown_recipe_ids": shown_recipe_ids}
    return out
