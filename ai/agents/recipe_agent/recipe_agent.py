from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .recipe_config import (
    AGENT_NAME,
    CONSTRAINT_EASY_30,
    EXTERNAL_TOOLS,
    INGREDIENT_KEYWORDS,
    MAX_DISPLAY_RECIPES,
    TEMPLATE_FIELDS_BY_NAME,
    TEMPLATE_FRIDGE_RECOMMEND,
    TEMPLATE_INGREDIENT_RECOMMEND,
    TEMPLATE_RECIPE_PAIRING,
    TEMPLATE_RECIPE_SEARCH,
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
    _extract_keyword,
    _extract_recipe_ingredient,
    _is_cooking_time_question,
    _requires_login,
    analyze_recipe_intent,
)


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
    """Orchestrator 내부 실행 상태."""
    req: RecipeAgentRequest
    template: str | None = None
    steps_done: list[str] = field(default_factory=list)
    intermediate: dict[str, Any] = field(default_factory=dict)


def check_required_fields(state: RecipeExecutionState) -> list[str]:
    """누락된 필수 필드 키 목록. 없으면 []. 값 진리값은 보지 않음(P9-2)."""
    required = TEMPLATE_FIELDS_BY_NAME.get(state.template or "", ())
    return [k for k in required if k not in state.intermediate]


def _note_missing_required_fields(state: RecipeExecutionState) -> None:
    missing = check_required_fields(state)
    if missing:
        state.intermediate["missing_required_fields"] = missing


def check_recipe_integrity(items: list[dict]) -> list[str]:
    """이슈 코드 목록. 없으면 []. 후보 목록은 수정하지 않음(P9-4)."""
    issues: list[str] = []
    if len(items) > MAX_DISPLAY_RECIPES:
        issues.append("too_many_items")
    seen_ids: set = set()
    for i, item in enumerate(items):
        rid = item.get("recipe_id")
        if rid is None:
            issues.append(f"missing_recipe_id:{i}")
        elif rid in seen_ids:
            issues.append(f"duplicate_recipe_id:{rid}")
        else:
            seen_ids.add(rid)
        if not (item.get("title") or "").strip():
            issues.append(f"missing_title:{i}")
    return issues


def _note_integrity_issues(state: RecipeExecutionState) -> None:
    if state.template == TEMPLATE_FRIDGE_RECOMMEND:
        items = (state.intermediate.get("ranked_recipes") or [])[:MAX_DISPLAY_RECIPES]
    else:
        items = state.intermediate.get("selected_recipes") or []
    issues = check_recipe_integrity(items)
    if issues:
        state.intermediate["integrity_issues"] = issues


def check_recommend_constraints(state: RecipeExecutionState) -> list[str]:
    """조건 위반 이슈 코드. 데이터 없으면 해당 검사 스킵. 응답은 바꾸지 않음(P9-4)."""
    issues: list[str] = []
    constraints = state.intermediate.get("constraints") or {}
    if state.template == TEMPLATE_INGREDIENT_RECOMMEND:
        items = state.intermediate.get("selected_recipes") or []
        want_diff = constraints.get("difficulty")
        easy30 = constraints.get("cooking_time_label") == "30분이내"
        for i, item in enumerate(items):
            if want_diff and item.get("difficulty") and item["difficulty"] != want_diff:
                issues.append(f"difficulty_mismatch:{i}")
            if easy30 and item.get("cooking_time_min") is not None and item["cooking_time_min"] > 30:
                issues.append(f"cooking_time_mismatch:{i}")
    if state.template == TEMPLATE_FRIDGE_RECOMMEND:
        items = (state.intermediate.get("ranked_recipes") or [])[:MAX_DISPLAY_RECIPES]
        for i, item in enumerate(items):
            owned = item.get("owned_ingredient_count")
            missing = item.get("missing_ingredient_count")
            if owned is not None and owned < 0:
                issues.append(f"owned_missing_contradiction:{i}")
            elif missing is not None and missing < 0:
                issues.append(f"owned_missing_contradiction:{i}")
    return issues


def _note_constraint_issues(state: RecipeExecutionState) -> None:
    issues = check_recommend_constraints(state)
    if issues:
        state.intermediate["constraint_issues"] = issues


@dataclass(frozen=True)
class RepairTarget:
    field: str
    reason: str
    fallback_tool: str | None = None


def build_repair_targets(state: RecipeExecutionState) -> list[RepairTarget]:
    """P9-1~P9-3 이슈를 RepairTarget으로 변환. 재실행은 P9-5."""
    targets: list[RepairTarget] = []
    for key in state.intermediate.get("missing_required_fields") or []:
        targets.append(RepairTarget(field=key, reason="missing_required_field"))

    list_field = (
        "ranked_recipes"
        if state.template == TEMPLATE_FRIDGE_RECOMMEND
        else "selected_recipes"
    )
    for code in state.intermediate.get("integrity_issues") or []:
        targets.append(RepairTarget(field=list_field, reason=code))
    for code in state.intermediate.get("constraint_issues") or []:
        targets.append(RepairTarget(field=list_field, reason=code))

    if state.template in (TEMPLATE_RECIPE_SEARCH, TEMPLATE_INGREDIENT_RECOMMEND):
        candidates = state.intermediate.get("recipe_candidates")
        if candidates is not None and not candidates:
            targets.append(
                RepairTarget(
                    field="recipe_candidates",
                    reason="empty_candidates",
                    fallback_tool="external_search_tool",
                )
            )

    if state.template == TEMPLATE_FRIDGE_RECOMMEND and state.intermediate.get("recommend_error"):
        targets.append(
            RepairTarget(
                field="recipe_candidates",
                reason=state.intermediate["recommend_error"] or "recommend_failed",
            )
        )
    return targets


def _note_repair_targets(state: RecipeExecutionState) -> None:
    targets = build_repair_targets(state)
    if targets:
        state.intermediate["repair_targets"] = targets


@dataclass(frozen=True)
class ExternalJob:
    name: str
    tool: str
    kwargs: dict
    fills_field: str


def collect_external_jobs(state: RecipeExecutionState) -> list[ExternalJob]:
    """외부 호출 후보만 수집. 실행은 P10-3."""
    if state.template not in (TEMPLATE_RECIPE_SEARCH, TEMPLATE_INGREDIENT_RECOMMEND):
        return []
    candidates = state.intermediate.get("recipe_candidates")
    if candidates is None or candidates:
        return []
    if "external_summary" in state.intermediate:
        return []
    keyword = state.intermediate.get("keyword") or state.intermediate.get("ingredient") or ""
    job = ExternalJob(
        name="external_search",
        tool="external_search_tool",
        kwargs={"keyword": keyword, "query_text": state.req.text},
        fills_field="external_summary",
    )
    return [job]


def _note_external_jobs(state: RecipeExecutionState) -> None:
    jobs = collect_external_jobs(state)
    if jobs:
        state.intermediate["external_jobs"] = jobs


def filter_independent_jobs(jobs: list[ExternalJob]) -> list[ExternalJob]:
    """§7.2 최소 필터. 실행은 P10-3."""
    out: list[ExternalJob] = []
    seen_fields: set[str] = set()
    for job in jobs:
        if job.tool not in EXTERNAL_TOOLS:
            continue
        if job.fills_field in seen_fields:
            continue
        if any(isinstance(v, str) and v in seen_fields for v in job.kwargs.values()):
            continue
        seen_fields.add(job.fills_field)
        out.append(job)
    return out


def _note_independent_external_jobs(state: RecipeExecutionState) -> None:
    jobs = state.intermediate.get("external_jobs") or []
    independent = filter_independent_jobs(jobs)
    if independent:
        state.intermediate["independent_external_jobs"] = independent


def _run_one_external_job(job: ExternalJob) -> tuple[ExternalJob, ToolResult]:
    if job.tool == "external_search_tool":
        return job, external_search_tool(
            job.kwargs.get("keyword") or "",
            query_text=job.kwargs.get("query_text"),
        )
    return job, ToolResult(ok=False, error=f"unknown tool: {job.tool}", source=job.tool)


def run_independent_external_jobs(state: RecipeExecutionState) -> RecipeExecutionState:
    """independent_external_jobs 실행. job 2+면 ThreadPoolExecutor."""
    jobs = list(state.intermediate.get("independent_external_jobs") or [])
    if not jobs:
        return state
    if len(jobs) == 1:
        results = [_run_one_external_job(jobs[0])]
    else:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=min(4, len(jobs))) as pool:
            results = list(pool.map(_run_one_external_job, jobs))
    for job, tr in results:
        if job.fills_field == "external_summary":
            if not tr.ok:
                failed = list(state.intermediate.get("failed_external_jobs") or [])
                failed.append({"name": job.name, "tool": job.tool, "error": tr.error})
                state.intermediate["failed_external_jobs"] = failed
                state.steps_done.append(f"run_fail:{job.name}")
                continue
            summary = (tr.data or {}).get("summary", "")
            sources = (tr.data or {}).get("sources", [])
            state.intermediate["external_summary"] = summary
            state.intermediate["sources"] = sources
            state.steps_done.append("run_external_search")
        else:
            state.steps_done.append(f"run_skip:{job.name}")
    return state


def apply_repair_targets(state: RecipeExecutionState) -> RecipeExecutionState:
    """필드당 최대 1회 fallback. 전체 fill 재시작 금지. ponytail: external_search만 실제 호출."""
    repaired: set[str] = set()
    for target in state.intermediate.get("repair_targets") or []:
        if target.field in repaired:
            continue
        repaired.add(target.field)
        if target.fallback_tool == "external_search_tool" and target.field == "recipe_candidates":
            if "external_summary" in state.intermediate:
                state.steps_done.append(f"repair_skip:{target.field}")
                continue
            keyword = state.intermediate.get("keyword") or state.intermediate.get("ingredient") or ""
            ext = external_search_tool(keyword, query_text=state.req.text)
            summary = (ext.data or {}).get("summary", "") if ext.ok else (ext.error or "")
            sources = (ext.data or {}).get("sources", []) if ext.ok else []
            state.intermediate["external_summary"] = summary
            state.intermediate["sources"] = sources
            state.steps_done.append("repair_external_search")
        else:
            state.steps_done.append(f"repair_skip:{target.field}")
    return state


def review_recipe_quality(state: RecipeExecutionState, result: RecipeAgentResult) -> list[str]:
    """보강 제안 목록. 데이터 수정 금지. ponytail: 휴리스틱; 실 LLM은 Backlog."""
    notes: list[str] = []
    if not (result.message or "").strip():
        notes.append("empty_message")
    if state.intermediate.get("constraint_issues"):
        notes.append("has_constraint_issues")
    if state.intermediate.get("integrity_issues"):
        notes.append("has_integrity_issues")
    return notes


def _attach_review_notes(state: RecipeExecutionState, result: RecipeAgentResult) -> RecipeAgentResult:
    notes = review_recipe_quality(state, result)
    if notes:
        state.intermediate["review_notes"] = notes
        meta = dict(result.meta or {})
        meta["review_notes"] = notes
        return RecipeAgentResult(
            ok=result.ok,
            agent=result.agent,
            intent=result.intent,
            message=result.message,
            error=result.error,
            actions=result.actions,
            sources=result.sources,
            meta=meta,
        )
    return result


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
    """냉장고 추천 비회원 차단."""
    if _requires_login(req.intent, req.text) and not req.user_id:
        return build_recipe_response(message=LOGIN_REQUIRED_REPLY, intent=req.intent)
    return None


def _fridge_empty_guard(req: RecipeAgentRequest) -> RecipeAgentResult | None:
    """빈 냉장고 차단. fridge pipeline에서 연결."""
    from ai.agents.inventory_agent.inventory_agent import EMPTY_INVENTORY_REPLY, is_inventory_empty

    if is_inventory_empty(db=req.db, user_id=req.user_id or 0):
        return build_recipe_response(message=EMPTY_INVENTORY_REPLY, intent=req.intent)
    return None


class PairingTemplateEngine:
    """TEMPLATE_RECIPE_PAIRING 필드를 pairing_tool로 채우는 실행기. _select_engine이 recipe.pairing에 연결."""

    def run(self, req: RecipeAgentRequest) -> RecipeAgentResult:
        tr = pairing_tool(req.text)
        if not tr.ok:
            return build_recipe_response(
                message=tr.error or "조합 추천에 실패했어요.",
                intent=req.intent,
            )
        data = tr.data or {}
        return build_recipe_response(
            message=data.get("reply", ""),
            intent=req.intent,
            actions=data.get("actions") or [],
            sources=[],
        )


class SearchTemplateEngine:
    """TEMPLATE_RECIPE_SEARCH를 pipeline + renderer로 채우는 실행기."""

    def run(self, req: RecipeAgentRequest) -> RecipeAgentResult:
        state = RecipeExecutionState(req=req, template=TEMPLATE_RECIPE_SEARCH)
        state = _fill_search_pipeline(state)
        state = run_independent_external_jobs(state)
        state = apply_repair_targets(state)
        result = _render_search_response(state)
        return _attach_review_notes(state, result)


class IngredientTemplateEngine:
    """TEMPLATE_INGREDIENT_RECOMMEND를 pipeline + renderer로 채우는 실행기."""

    def run(self, req: RecipeAgentRequest) -> RecipeAgentResult:
        state = RecipeExecutionState(req=req, template=TEMPLATE_INGREDIENT_RECOMMEND)
        state = _fill_ingredient_pipeline(state)
        state = run_independent_external_jobs(state)
        state = apply_repair_targets(state)
        result = _render_ingredient_response(state)
        return _attach_review_notes(state, result)


class FridgeTemplateEngine:
    """TEMPLATE_FRIDGE_RECOMMEND를 guard + pipeline + renderer로 채우는 실행기."""

    def run(self, req: RecipeAgentRequest) -> RecipeAgentResult:
        guarded = _fridge_login_guard(req)
        if guarded is not None:
            return guarded
        empty = _fridge_empty_guard(req)
        if empty is not None:
            return empty
        state = RecipeExecutionState(req=req, template=TEMPLATE_FRIDGE_RECOMMEND)
        state = _fill_fridge_pipeline(state)
        state = run_independent_external_jobs(state)
        state = apply_repair_targets(state)
        result = _render_fridge_response(state)
        return _attach_review_notes(state, result)


def _select_engine(
    intent: str, text: str = "",
) -> PairingTemplateEngine | SearchTemplateEngine | IngredientTemplateEngine | FridgeTemplateEngine:
    """intent + text에 따라 실행기를 선택한다. unknown intent는 recommend와 동일 분기."""
    if intent == "recipe.pairing":
        return PairingTemplateEngine()
    if intent == "recipe.search":
        return SearchTemplateEngine()
    if _extract_recipe_ingredient(text):
        return IngredientTemplateEngine()
    return FridgeTemplateEngine()


def _select_template(intent: str, text: str) -> str:
    """intent + 텍스트로 템플릿을 선택한다. ponytail: 현재 응답 생성에 미사용. P3-4 shadow 비교에서 검증."""
    if intent == "recipe.search":
        return TEMPLATE_RECIPE_SEARCH
    if intent == "recipe.pairing":
        return TEMPLATE_RECIPE_PAIRING
    if any(kw in text for kw in INGREDIENT_KEYWORDS):
        return TEMPLATE_FRIDGE_RECOMMEND
    return TEMPLATE_INGREDIENT_RECOMMEND


def _fill_search_pipeline(state: RecipeExecutionState) -> RecipeExecutionState:
    """내부 검색 단계로 SEARCH_TEMPLATE_FIELDS를 채운다. 조리시간 질문은 외부 검색으로 조기 분기."""
    text = state.req.text
    keyword = _extract_recipe_ingredient(text) or _extract_keyword(text)
    state.intermediate["keyword"] = keyword
    state.steps_done.append("extract_keyword")

    if _is_cooking_time_question(text):
        ext = external_search_tool(keyword, query_text=text)
        summary = (ext.data or {}).get("summary", "") if ext.ok else (ext.error or "")
        sources = (ext.data or {}).get("sources", []) if ext.ok else []
        state.intermediate["recipe_candidates"] = []
        state.intermediate["selected_recipes"] = []
        state.intermediate["actions"] = []
        state.intermediate["sources"] = sources
        state.intermediate["external_summary"] = summary
        state.steps_done.append("external_cooking_time")
        state.template = TEMPLATE_RECIPE_SEARCH
        _note_missing_required_fields(state)
        _note_integrity_issues(state)
        _note_repair_targets(state)
        _note_external_jobs(state)
        _note_independent_external_jobs(state)
        return state

    search = search_recipe_tool(state.req.db, keyword)
    candidates = (search.data or {}).get("items", []) if search.ok else []
    state.intermediate["recipe_candidates"] = candidates
    state.steps_done.append("search_recipe")

    ranked = rank_search_candidates_tool(keyword, candidates)
    items = (ranked.data or {}).get("items", []) if ranked.ok else candidates
    selected = items[:3]
    state.intermediate["selected_recipes"] = selected
    state.steps_done.append("rank_and_select")

    state.intermediate["actions"] = []
    state.intermediate["sources"] = []
    state.template = TEMPLATE_RECIPE_SEARCH
    _note_missing_required_fields(state)
    _note_integrity_issues(state)
    _note_repair_targets(state)
    _note_external_jobs(state)
    _note_independent_external_jobs(state)
    return state


def _render_search_response(state: RecipeExecutionState) -> RecipeAgentResult:
    """SEARCH_TEMPLATE_FIELDS로 검색 응답을 조립한다. 0건/조리시간은 external_search_tool fallback."""
    keyword = state.intermediate.get("keyword") or ""
    selected = state.intermediate.get("selected_recipes") or []

    if state.intermediate.get("external_summary") is not None:
        summary = state.intermediate["external_summary"]
        sources = state.intermediate.get("sources") or []
        return build_recipe_response(
            message=summary,
            intent=state.req.intent,
            actions=[],
            sources=sources,
        )

    if not selected:
        ext = external_search_tool(keyword, query_text=state.req.text)
        summary = (ext.data or {}).get("summary", "") if ext.ok else (
            ext.error or (f"{keyword} 관련 레시피를 찾지 못했어요." if keyword else "관련 레시피를 찾지 못했어요.")
        )
        sources = (ext.data or {}).get("sources", []) if ext.ok else []
        state.intermediate["actions"] = []
        state.intermediate["sources"] = sources
        return build_recipe_response(
            message=summary,
            intent=state.req.intent,
            actions=[],
            sources=sources,
        )

    titles = [item.get("title") or "" for item in selected]
    reply = f"{keyword} 관련 레시피예요.\n" + "\n".join(
        f"{index + 1}. {title}" for index, title in enumerate(titles)
    )
    actions_tr = build_actions_tool(selected)
    actions = (actions_tr.data or {}).get("actions", []) if actions_tr.ok else []
    state.intermediate["actions"] = actions
    state.intermediate["sources"] = []
    return build_recipe_response(
        message=reply,
        intent=state.req.intent,
        actions=actions,
        sources=[],
    )


def _fill_ingredient_pipeline(state: RecipeExecutionState) -> RecipeExecutionState:
    """특정 재료 추천 intermediate를 채운다. actions는 P7-4."""
    ingredient = _extract_recipe_ingredient(state.req.text) or ""
    state.intermediate["ingredient"] = ingredient
    state.steps_done.append("extract_ingredient")

    if not ingredient:
        state.intermediate["constraints"] = {}
        state.intermediate["recipe_candidates"] = []
        state.intermediate["selected_recipes"] = []
        state.intermediate["actions"] = []
        state.template = TEMPLATE_INGREDIENT_RECOMMEND
        _note_missing_required_fields(state)
        _note_integrity_issues(state)
        _note_constraint_issues(state)
        _note_repair_targets(state)
        _note_external_jobs(state)
        _note_independent_external_jobs(state)
        return state

    tr = search_ingredient_relax_tool(state.req.db, ingredient)
    data = tr.data or {}
    state.intermediate["constraints"] = data.get("constraints") or {}
    state.intermediate["recipe_candidates"] = (data.get("items") or []) if tr.ok else []
    state.intermediate["actions"] = []
    state.steps_done.append("relax_search")

    candidates = state.intermediate.get("recipe_candidates") or []
    excluded = exclude_previous_tool(candidates, state.req.history)
    filtered = (excluded.data or {}).get("items", candidates) if excluded.ok else candidates
    state.intermediate["selected_recipes"] = filtered[:3]
    state.steps_done.append("exclude_previous")
    state.template = TEMPLATE_INGREDIENT_RECOMMEND
    _note_missing_required_fields(state)
    _note_integrity_issues(state)
    _note_constraint_issues(state)
    _note_repair_targets(state)
    _note_external_jobs(state)
    _note_independent_external_jobs(state)
    return state


def _fill_fridge_pipeline(state: RecipeExecutionState) -> RecipeExecutionState:
    """FRIDGE_TEMPLATE_FIELDS 중 candidates/ranked까지 채움. actions는 P8-6."""
    tr = recommend_recipe_tool(state.req.db, state.req.user_id or 0, state.req.settings_obj)
    if not tr.ok:
        state.intermediate["recommend_error"] = (
            tr.error or "냉장고 기반 추천을 불러오지 못했어요. 재료명을 넣어서 다시 물어봐주세요."
        )
    candidates = (tr.data or {}).get("items", []) if tr.ok else []
    state.intermediate["recipe_candidates"] = candidates
    state.steps_done.append("recommend_recipe")

    sorted_tr = sort_candidates_tool(candidates)
    ranked = (sorted_tr.data or {}).get("items", candidates) if sorted_tr.ok else candidates
    state.intermediate["ranked_recipes"] = ranked
    state.steps_done.append("sort_candidates")

    state.intermediate.setdefault("inventory_status", None)
    state.intermediate.setdefault("user_preferences", None)
    state.intermediate.setdefault("owned_ingredient_count", None)
    state.intermediate.setdefault("missing_ingredient_count", None)
    state.intermediate["actions"] = []
    state.template = TEMPLATE_FRIDGE_RECOMMEND
    _note_missing_required_fields(state)
    _note_integrity_issues(state)
    _note_constraint_issues(state)
    _note_repair_targets(state)
    _note_external_jobs(state)
    _note_independent_external_jobs(state)
    return state


def _render_fridge_response(state: RecipeExecutionState) -> RecipeAgentResult:
    """FRIDGE_TEMPLATE_FIELDS로 냉장고 추천 응답을 조립한다."""
    if state.intermediate.get("recommend_error"):
        return build_recipe_response(
            message=state.intermediate["recommend_error"],
            intent=state.req.intent,
        )

    ranked = state.intermediate.get("ranked_recipes") or []
    perfect = [i for i in ranked if i.get("missing_ingredient_count", 0) == 0]
    if perfect:
        selected = perfect[:3]
        prefix = "현재 냉장고 재료만으로 완벽하게 만들 수 있는 레시피예요.\n"
    else:
        selected = ranked[:3]
        if not selected or selected[0].get("owned_ingredient_count", 0) == 0:
            return build_recipe_response(
                message="현재 냉장고 재료와 매칭되는 레시피를 찾지 못했어요. 재료를 더 추가해 보세요.",
                intent=state.req.intent,
            )
        prefix = "부족한 재료가 약간 있지만, 냉장고 재료를 최대한 활용할 수 있는 레시피예요.\n"

    actions_tr = build_actions_tool(selected)
    actions = (actions_tr.data or {}).get("actions", []) if actions_tr.ok else []
    state.intermediate["actions"] = actions
    titles = [i.get("title") or "" for i in selected]
    reply = prefix + "\n".join(f"{n + 1}. {t}" for n, t in enumerate(titles))
    return build_recipe_response(message=reply, intent=state.req.intent, actions=actions)


def _render_ingredient_response(state: RecipeExecutionState) -> RecipeAgentResult:
    """INGREDIENT_TEMPLATE_FIELDS로 특정 재료 추천 응답을 조립한다."""
    from urllib.parse import quote

    ingredient = state.intermediate.get("ingredient") or ""
    selected = state.intermediate.get("selected_recipes") or []
    constraints = state.intermediate.get("constraints") or {}

    if not ingredient:
        return build_recipe_response(message="", intent=state.req.intent)

    if state.intermediate.get("external_summary") is not None:
        return build_recipe_response(
            message=state.intermediate["external_summary"],
            intent=state.req.intent,
            actions=[],
            sources=state.intermediate.get("sources") or [],
        )

    if not selected:
        ext = external_search_tool(ingredient, query_text=state.req.text)
        summary = (ext.data or {}).get("summary", "") if ext.ok else (ext.error or "")
        state.intermediate["actions"] = []
        return build_recipe_response(
            message=summary,
            intent=state.req.intent,
            actions=[],
            sources=[],
        )

    list_action = {
        "label": f"{ingredient} 레시피 더 보기",
        "url": f"/recipes?ingredient={quote(ingredient)}",
        "data": {"ingredient": ingredient},
    }
    actions_tr = build_actions_tool(selected)
    actions = (actions_tr.data or {}).get("actions", []) if actions_tr.ok else []
    actions = actions + [list_action]
    state.intermediate["actions"] = actions

    is_easy = constraints == CONSTRAINT_EASY_30
    prefix = (
        f"{_apply_josa(ingredient, '이가')} 주재료인 30분 이내 초급 레시피는 "
        if is_easy
        else f"{_apply_josa(ingredient, '이가')} 주재료인 레시피는 "
    )
    titles = [item.get("title") or "" for item in selected]
    reply = prefix + "\n" + "\n".join(
        f"{index + 1}. {title}" for index, title in enumerate(titles)
    )
    return build_recipe_response(
        message=reply,
        intent=state.req.intent,
        actions=actions,
        sources=[],
    )


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
    req = RecipeAgentRequest(
        text=text, db=db, user_id=user_id,
        history=history or [],
        settings_obj=settings_obj,
        intent=intent or analyze_recipe_intent(text, history),
    )
    engine = _select_engine(req.intent, req.text)
    result = engine.run(req)
    return to_supervisor_state(result)
