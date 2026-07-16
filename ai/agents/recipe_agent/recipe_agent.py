from __future__ import annotations

from dataclasses import dataclass, field
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
    build_actions_tool,
    exclude_previous_tool,
    external_search_tool,
    pairing_tool,
    rank_search_candidates_tool,
    recommend_recipe_tool,
    search_ingredient_relax_tool,
    search_recipe_tool,
    sort_candidates_tool,
)
from .recipe_utils import (
    LOGIN_REQUIRED_REPLY,
    _apply_josa,
    _requires_login,
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

@dataclass(frozen=True)
class PlanStep:
    tool: str
    args: dict[str, Any] = field(default_factory=dict)
    when: str = WHEN_ALWAYS


@dataclass
class RecipePlan:
    steps: list[PlanStep]
    max_fallback: int = 1


@dataclass
class RecipeAgentRequest:
    text: str
    db: Any
    user_id: int | None
    history: list
    settings_obj: Any
    intent: str


@dataclass
class RecipeAgentResult:
    ok: bool
    agent: str
    intent: str
    message: str
    error: dict[str, Any] | None
    actions: list[dict[str, Any]]
    sources: list[dict[str, Any]]
    meta: dict[str, Any]


@dataclass
class RecipeExecutionState:
    """Agent loop internal state."""
    req: RecipeAgentRequest
    plan: RecipePlan | None = None
    steps_done: list[str] = field(default_factory=list)
    intermediate: dict[str, Any] = field(default_factory=dict)
    last_tool: str | None = None


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
    ranked = rank_search_candidates_tool(keyword, candidates)
    items = (ranked.data or {}).get("items", candidates) if ranked.ok else candidates
    selected = items[:MAX_DISPLAY_RECIPES]
    return ToolResult(
        ok=True,
        data={"keyword": keyword, "items": selected, "total": len(selected)},
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
    excluded = exclude_previous_tool(candidates, req.history)
    filtered = (excluded.data or {}).get("items", candidates) if excluded.ok else candidates
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
    sorted_tr = sort_candidates_tool(candidates)
    ranked = (sorted_tr.data or {}).get("items", candidates) if sorted_tr.ok else candidates
    return ToolResult(ok=True, data={"items": ranked, "total": len(ranked)}, source=TOOL_RECOMMEND_FROM_FRIDGE)


def _tool_search_external(req: RecipeAgentRequest, args: dict[str, Any]) -> ToolResult:
    keyword = args.get("keyword") or ""
    query_text = args.get("query_text") or req.text
    tr = external_search_tool(keyword, query_text=query_text)
    if not tr.ok:
        return tr
    data = tr.data or {}
    return ToolResult(
        ok=True,
        data={"keyword": keyword, "summary": data.get("summary", ""), "sources": data.get("sources") or []},
        source=TOOL_SEARCH_EXTERNAL,
    )


def _tool_suggest_pairing(req: RecipeAgentRequest, args: dict[str, Any]) -> ToolResult:
    text = args.get("text") or req.text
    return pairing_tool(text)


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


def render_response(state: RecipeExecutionState) -> RecipeAgentResult:
    """Assemble final message from last meaningful tool result."""
    req = state.req
    intent = req.intent

    # Prefer last successful non-empty tool; walk backwards through plan
    if state.plan:
        for step in reversed(state.plan.steps):
            tr = state.intermediate.get(step.tool)
            if tr is None or not tr.ok:
                continue
            if _step_result_empty(tr, step.tool) and step.when == WHEN_ALWAYS:
                continue
            return _render_tool_result(step.tool, tr, req)

    # All failed or empty
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
        titles = [item.get("title") or "" for item in selected]
        reply = f"{keyword} 관련 레시피예요.\n" + "\n".join(
            f"{index + 1}. {title}" for index, title in enumerate(titles)
        )
        actions_tr = build_actions_tool(selected)
        actions = (actions_tr.data or {}).get("actions", []) if actions_tr.ok else []
        return build_recipe_response(message=reply, intent=intent, actions=actions)

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
        actions_tr = build_actions_tool(selected)
        actions = (actions_tr.data or {}).get("actions", []) if actions_tr.ok else []
        actions = actions + [list_action]
        is_easy = constraints == CONSTRAINT_EASY_30
        prefix = (
            f"{_apply_josa(ingredient, '이가')} 주재료인 30분 이내 초급 레시피는 "
            if is_easy
            else f"{_apply_josa(ingredient, '이가')} 주재료인 레시피는 "
        )
        titles = [item.get("title") or "" for item in selected]
        reply = prefix + "\n" + "\n".join(f"{index + 1}. {title}" for index, title in enumerate(titles))
        return build_recipe_response(message=reply, intent=intent, actions=actions)

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
        actions_tr = build_actions_tool(selected)
        actions = (actions_tr.data or {}).get("actions", []) if actions_tr.ok else []
        titles = [i.get("title") or "" for i in selected]
        reply = prefix + "\n".join(f"{n + 1}. {t}" for n, t in enumerate(titles))
        return build_recipe_response(message=reply, intent=intent, actions=actions)

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
    result = RecipeAgentResult(
        ok=result.ok,
        agent=result.agent,
        intent=result.intent,
        message=result.message,
        error=result.error,
        actions=result.actions,
        sources=result.sources,
        meta=meta,
    )
    return to_supervisor_state(result)


if __name__ == "__main__":
    # ponytail: -m 실행 시 패키지 선로딩과 네임스페이스가 갈릴 수 있어 agent.* 만 사용
    import ai.agents.recipe_agent.recipe_agent as agent
    import ai.agents.recipe_agent.recipe_planner as planner

    def _check_output_contract(result: dict) -> None:
        assert set(result) == {"response_text", "actions", "sources"}
        assert isinstance(result["response_text"], str)
        assert isinstance(result["actions"], list)
        assert isinstance(result["sources"], list)

    # (a) rule plan tool order by utterance type
    req_pairing = agent.RecipeAgentRequest(
        text="김치볶음밥이랑 먹기 좋은 음식", db=None, user_id=1,
        history=[], settings_obj=None, intent="recipe.pairing",
    )
    plan_p = planner.plan_recipe_request_rule(req_pairing)
    assert [s.tool for s in plan_p.steps] == [agent.TOOL_SUGGEST_PAIRING]

    req_cook = agent.RecipeAgentRequest(
        text="감자튀김 에어프라이기 시간", db=None, user_id=1,
        history=[], settings_obj=None, intent="recipe.search",
    )
    plan_c = planner.plan_recipe_request_rule(req_cook)
    assert [s.tool for s in plan_c.steps] == [agent.TOOL_SEARCH_EXTERNAL]

    req_search = agent.RecipeAgentRequest(
        text="김치볶음밥 레시피", db=None, user_id=1,
        history=[], settings_obj=None, intent="recipe.search",
    )
    plan_s = planner.plan_recipe_request_rule(req_search)
    assert plan_s.steps[0].tool == agent.TOOL_SEARCH_RECIPES
    assert plan_s.steps[1].tool == agent.TOOL_SEARCH_EXTERNAL
    assert plan_s.steps[1].when == agent.WHEN_PREV_EMPTY

    req_ing = agent.RecipeAgentRequest(
        text="두부로 뭐 해먹지?", db=None, user_id=1,
        history=[], settings_obj=None, intent="recipe.recommend",
    )
    plan_i = planner.plan_recipe_request_rule(req_ing)
    assert plan_i.steps[0].tool == agent.TOOL_RECOMMEND_BY_INGREDIENT
    assert plan_i.steps[1].when == agent.WHEN_PREV_EMPTY

    req_fridge = agent.RecipeAgentRequest(
        text="오늘 뭐 해먹지?", db=None, user_id=1,
        history=[], settings_obj=None, intent="recipe.recommend",
    )
    plan_f = planner.plan_recipe_request_rule(req_fridge)
    assert [s.tool for s in plan_f.steps] == [agent.TOOL_RECOMMEND_FROM_FRIDGE]

    # (e) LLM fail → rule plan matches
    orig_llm = planner._call_llm_planner
    planner._call_llm_planner = lambda r: None
    try:
        plan_fb, src = planner.plan_recipe_request(req_search)
        assert src == "rule"
        assert [s.tool for s in plan_fb.steps] == [agent.TOOL_SEARCH_RECIPES, agent.TOOL_SEARCH_EXTERNAL]
    finally:
        planner._call_llm_planner = orig_llm

    norm = planner._normalize_llm_plan(
        {"steps": [{"tool": "bogus", "args": {}}]}, req_search,
    )
    assert norm is None

    # (b) empty search → fallback external once
    def fake_empty_search(req: agent.RecipeAgentRequest, args: dict) -> agent.ToolResult:
        return agent.ToolResult(
            ok=True,
            data={"keyword": args.get("keyword", ""), "items": [], "total": 0},
            source=agent.TOOL_SEARCH_RECIPES,
        )

    def fake_external(req: agent.RecipeAgentRequest, args: dict) -> agent.ToolResult:
        return agent.ToolResult(
            ok=True,
            data={
                "keyword": args.get("keyword", ""),
                "summary": "웹 검색 답",
                "sources": [{"title": "출처", "url": "https://x.com"}],
            },
            source=agent.TOOL_SEARCH_EXTERNAL,
        )

    orig_search = agent.TOOL_REGISTRY[agent.TOOL_SEARCH_RECIPES]
    orig_external = agent.TOOL_REGISTRY[agent.TOOL_SEARCH_EXTERNAL]
    agent.TOOL_REGISTRY[agent.TOOL_SEARCH_RECIPES] = fake_empty_search
    agent.TOOL_REGISTRY[agent.TOOL_SEARCH_EXTERNAL] = fake_external
    try:
        r = agent.run_recipe_agent("김치볶음밥 레시피", db=None, intent="recipe.search")
        _check_output_contract(r)
        assert r["response_text"] == "웹 검색 답"
        assert r["sources"][0]["url"] == "https://x.com"
    finally:
        agent.TOOL_REGISTRY[agent.TOOL_SEARCH_RECIPES] = orig_search
        agent.TOOL_REGISTRY[agent.TOOL_SEARCH_EXTERNAL] = orig_external

    # (c) max_fallback cap: second prev_empty step skipped when cap=0
    cap_plan = agent.RecipePlan(
        steps=[
            agent.PlanStep(tool=agent.TOOL_SEARCH_RECIPES, args={"keyword": "x"}),
            agent.PlanStep(tool=agent.TOOL_SEARCH_EXTERNAL, args={"keyword": "x"}, when=agent.WHEN_PREV_EMPTY),
        ],
        max_fallback=0,
    )
    req_cap = agent.RecipeAgentRequest(
        text="x", db=None, user_id=1, history=[], settings_obj=None, intent="recipe.search",
    )
    state_cap = agent.RecipeExecutionState(req=req_cap, plan=cap_plan)
    agent.TOOL_REGISTRY[agent.TOOL_SEARCH_RECIPES] = fake_empty_search
    try:
        state_cap = agent.execute_plan(state_cap)
        assert "skip_fallback_cap:search_external" in state_cap.steps_done
        assert agent.TOOL_SEARCH_EXTERNAL not in state_cap.intermediate
    finally:
        agent.TOOL_REGISTRY[agent.TOOL_SEARCH_RECIPES] = orig_search

    # (d) search with hits
    def fake_search_hit(req: agent.RecipeAgentRequest, args: dict) -> agent.ToolResult:
        return agent.ToolResult(
            ok=True,
            data={"keyword": "김치볶음밥", "items": [{"recipe_id": 1, "title": "김치볶음밥"}], "total": 1},
            source=agent.TOOL_SEARCH_RECIPES,
        )

    agent.TOOL_REGISTRY[agent.TOOL_SEARCH_RECIPES] = fake_search_hit
    try:
        r = agent.run_recipe_agent("김치볶음밥 레시피", db=None, intent="recipe.search")
        _check_output_contract(r)
        assert "관련 레시피예요." in r["response_text"]
        assert r["actions"][0]["url"] == "/recipes/1"
        assert r["sources"] == []
    finally:
        agent.TOOL_REGISTRY[agent.TOOL_SEARCH_RECIPES] = orig_search

    print("recipe_agent ok")
