from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .recipe_handlers import handle_recipe_pairing
from .recipe_intents import analyze_recipe_intent
from .recipe_utils import LOGIN_REQUIRED_REPLY, _extract_recipe_ingredient, _requires_login

AGENT_NAME = "recipe"


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


@dataclass
class ToolResult:
    """Tool 실행 공통 결과."""
    ok: bool
    data: Any = None
    error: str | None = None
    source: str | None = None


TEMPLATE_RECIPE_SEARCH = "RECIPE_SEARCH"
TEMPLATE_INGREDIENT_RECOMMEND = "INGREDIENT_RECOMMEND"
TEMPLATE_FRIDGE_RECOMMEND = "FRIDGE_RECOMMEND"
TEMPLATE_RECIPE_PAIRING = "RECIPE_PAIRING"

SEARCH_TEMPLATE_FIELDS = (
    "keyword",
    "recipe_candidates",
    "selected_recipes",
    "actions",
    "sources",
)

INGREDIENT_TEMPLATE_FIELDS = (
    "ingredient",
    "constraints",
    "recipe_candidates",
    "selected_recipes",
    "actions",
)

FRIDGE_TEMPLATE_FIELDS = (
    "inventory_status",
    "user_preferences",
    "recipe_candidates",
    "ranked_recipes",
    "owned_ingredient_count",
    "missing_ingredient_count",
    "actions",
)

_TEMPLATE_FIELDS_BY_NAME = {
    TEMPLATE_RECIPE_SEARCH: SEARCH_TEMPLATE_FIELDS,
    TEMPLATE_INGREDIENT_RECOMMEND: INGREDIENT_TEMPLATE_FIELDS,
    TEMPLATE_FRIDGE_RECOMMEND: FRIDGE_TEMPLATE_FIELDS,
}


def check_required_fields(state: RecipeExecutionState) -> list[str]:
    """누락된 필수 필드 키 목록. 없으면 []. 값 진리값은 보지 않음(P9-2)."""
    required = _TEMPLATE_FIELDS_BY_NAME.get(state.template or "", ())
    return [k for k in required if k not in state.intermediate]


def _note_missing_required_fields(state: RecipeExecutionState) -> None:
    missing = check_required_fields(state)
    if missing:
        state.intermediate["missing_required_fields"] = missing


MAX_DISPLAY_RECIPES = 3


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


_EXTERNAL_TOOLS = frozenset({"external_search_tool"})


def filter_independent_jobs(jobs: list[ExternalJob]) -> list[ExternalJob]:
    """§7.2 최소 필터. 실행은 P10-3."""
    out: list[ExternalJob] = []
    seen_fields: set[str] = set()
    for job in jobs:
        if job.tool not in _EXTERNAL_TOOLS:
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


CONSTRAINT_EASY_30 = {"difficulty": "초급", "cooking_time_label": "30분이내", "main_ingredient_only": True}
CONSTRAINT_INGREDIENT_ONLY = {"main_ingredient_only": True}


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
    ingredient_keywords = ("냉장고", "재료", "있는 것", "남은")
    if any(kw in text for kw in ingredient_keywords):
        return TEMPLATE_FRIDGE_RECOMMEND
    return TEMPLATE_INGREDIENT_RECOMMEND


def search_recipe_tool(db: Any, keyword: str) -> ToolResult:
    """recipe_search_service를 ToolResult로 감싼다."""
    try:
        from .recipe_handlers import recipe_search_service
        result = recipe_search_service.search_recipes(
            db=db, ingredient=keyword, main_ingredient_only=True, page=1, page_size=10,
        )
        items = result["items"]
        if not items:
            result = recipe_search_service.search_recipes(db=db, query=keyword, page=1, page_size=10)
            items = result["items"]
        return ToolResult(ok=True, data={"items": items, "total": result.get("total", len(items))}, source="recipe_search")
    except Exception as e:
        return ToolResult(ok=False, error=str(e), source="recipe_search")


def build_recommend_config_tool(settings_obj: Any = None) -> ToolResult:
    """settings_obj → RecipeRecommendConfig. ponytail: Legacy 설정 반영. exclude_dislikes는 config 필드 없음 → data sidecar."""
    try:
        from dataclasses import replace

        from app.backend.services.recommendation_service.recommend_config import RecipeRecommendConfig

        config = RecipeRecommendConfig.fridge_consume_preset()
        exclude_dislikes = True
        if settings_obj:
            if not getattr(settings_obj, "expiringFirst", True):
                config = replace(config, mode="fridge_all")  # type: ignore[arg-type]
            if not getattr(settings_obj, "excludeDislikes", True):
                exclude_dislikes = False
        return ToolResult(
            ok=True,
            data={"config": config, "exclude_dislikes": exclude_dislikes},
            source="recommend_config",
        )
    except Exception as e:
        return ToolResult(ok=False, error=str(e), source="recommend_config")


def recommend_recipe_tool(db: Any, user_id: int, settings_obj: Any = None) -> ToolResult:
    """recommendation_service를 ToolResult로 감싼다."""
    try:
        from .recipe_handlers import recommendation_service

        cfg = build_recommend_config_tool(settings_obj)
        if not cfg.ok:
            return ToolResult(ok=False, error=cfg.error, source="recommendation")
        config = (cfg.data or {})["config"]
        result = recommendation_service.recommend_recipes(db, user_id, config)
        items = result.get("items", [])
        return ToolResult(ok=True, data={"items": items, "total": len(items)}, source="recommendation")
    except Exception as e:
        return ToolResult(ok=False, error=str(e), source="recommendation")


def sort_candidates_tool(items: list[dict[str, Any]]) -> ToolResult:
    """추천 후보를 보유 재료·부족 재료·점수 기준으로 정렬한다."""
    try:
        sorted_items = sorted(
            items,
            key=lambda x: (
                -x.get("owned_ingredient_count", 0),
                x.get("missing_ingredient_count", 0),
                -x.get("final_score", 0),
            ),
        )
        return ToolResult(ok=True, data={"items": sorted_items, "total": len(sorted_items)}, source="sort_candidates")
    except Exception as e:
        return ToolResult(ok=False, error=str(e), source="sort_candidates")


def exclude_previous_tool(items: list[dict[str, Any]], history: list) -> ToolResult:
    """이전 봇 응답에 포함된 레시피를 후보에서 제외한다. ponytail: 문자열 비교 방식. 구조화 이력 전환은 Backlog."""
    try:
        past_bot_texts = " ".join(getattr(msg, "text", "") for msg in history if getattr(msg, "role", "") == "bot")
        filtered = [item for item in items if item.get("title", "") not in past_bot_texts]
        if not filtered:
            filtered = list(items)
        return ToolResult(ok=True, data={"items": filtered, "total": len(filtered)}, source="exclude_previous")
    except Exception as e:
        return ToolResult(ok=False, error=str(e), source="exclude_previous")


def build_actions_tool(items: list[dict[str, Any]]) -> ToolResult:
    """레시피 후보에서 프론트엔드 Action 목록을 생성한다."""
    try:
        from .recipe_utils import _recipe_actions
        actions = _recipe_actions(items)
        return ToolResult(ok=True, data={"actions": actions, "total": len(actions)}, source="build_actions")
    except Exception as e:
        return ToolResult(ok=False, error=str(e), source="build_actions")


def external_search_tool(keyword: str, query_text: str | None = None) -> ToolResult:
    """외부 소스(Tavily)로 레시피를 검색하고 요약한다."""
    try:
        from .recipe_handlers import reply_external_recipe
        summary, sources = reply_external_recipe(keyword, query_text)
        return ToolResult(ok=True, data={"summary": summary, "sources": sources}, source="external_search")
    except Exception as e:
        return ToolResult(ok=False, error=str(e), source="external_search")


def pairing_tool(text: str) -> ToolResult:
    """음식 조합(곁들임) 메뉴를 조회한다. ponytail: 정적 dict — P5-3에서 Orchestrator가 호출."""
    try:
        reply, actions = handle_recipe_pairing(text)
        return ToolResult(
            ok=True,
            data={"reply": reply, "actions": actions},
            source="pairing",
        )
    except Exception as e:
        return ToolResult(ok=False, error=str(e), source="pairing")


def rank_search_candidates_tool(keyword: str, items: list[dict[str, Any]]) -> ToolResult:
    """검색 후보를 키워드 매칭 점수로 정렬한다. ponytail: _rank_recipe_items 재사용."""
    try:
        from .recipe_utils import _rank_recipe_items
        ranked = _rank_recipe_items(keyword, items)
        return ToolResult(ok=True, data={"items": ranked, "total": len(ranked)}, source="rank_search")
    except Exception as e:
        return ToolResult(ok=False, error=str(e), source="rank_search")


def search_ingredient_relax_tool(db: Any, ingredient: str) -> ToolResult:
    """주재료+초급+30분 → 주재료만 순으로 검색한다. ponytail: Legacy 완화 순서 고정."""
    try:
        from .recipe_handlers import recipe_search_service
        from .recipe_utils import _rank_recipe_items

        result = recipe_search_service.search_recipes(
            db=db, ingredient=ingredient, difficulty="초급", cooking_time_label="30분이내",
            main_ingredient_only=True, page=1, page_size=10,
        )
        items = _rank_recipe_items(ingredient, result["items"])
        constraints = dict(CONSTRAINT_EASY_30)
        if not items:
            result = recipe_search_service.search_recipes(
                db=db, ingredient=ingredient, main_ingredient_only=True, page=1, page_size=10,
            )
            items = _rank_recipe_items(ingredient, result["items"])
            constraints = dict(CONSTRAINT_INGREDIENT_ONLY)
        return ToolResult(
            ok=True,
            data={"items": items, "total": len(items), "constraints": constraints},
            source="ingredient_relax",
        )
    except Exception as e:
        return ToolResult(ok=False, error=str(e), source="ingredient_relax")


def _fill_search_pipeline(state: RecipeExecutionState) -> RecipeExecutionState:
    """내부 검색 단계로 SEARCH_TEMPLATE_FIELDS를 채운다. 조리시간 질문은 외부 검색으로 조기 분기."""
    from .recipe_utils import _extract_keyword, _extract_recipe_ingredient, _is_cooking_time_question

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
    from .recipe_utils import _extract_recipe_ingredient

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
    from .recipe_utils import _apply_josa

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
