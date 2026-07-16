from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any

from .recipe_handlers import handle_recipe_pairing, handle_recipe_recommend, handle_recipe_search
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
    """Orchestrator 내부 실행 상태. ponytail: 현재 미사용. P3-2 이후 Orchestrator에서 활용."""
    req: RecipeAgentRequest
    template: str | None = None
    steps_done: list[str] = field(default_factory=list)
    intermediate: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResult:
    """Tool 실행 공통 결과. ponytail: 현재 미사용. P4-2 이후 Tool 래퍼에서 활용."""
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


ENABLE_LLM_REVIEWER = False  # ponytail: 기본 off. on 시 stub/휴리스틱.


def review_recipe_quality(state: RecipeExecutionState, result: RecipeAgentResult) -> list[str]:
    """보강 지침 목록. 데이터 수정 금지. flag off면 []."""
    if not ENABLE_LLM_REVIEWER:
        return []
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
    """냉장고 추천 비회원 차단. ponytail: LegacyRecipeEngine과 동일 조건."""
    if _requires_login(req.intent, req.text) and not req.user_id:
        return build_recipe_response(message=LOGIN_REQUIRED_REPLY, intent=req.intent)
    return None


def _fridge_empty_guard(req: RecipeAgentRequest) -> RecipeAgentResult | None:
    """빈 냉장고 차단. ponytail: Legacy handle_recipe_recommend와 동일. fridge pipeline에서 연결."""
    from ai.agents.inventory_agent.inventory_agent import EMPTY_INVENTORY_REPLY, is_inventory_empty

    if is_inventory_empty(db=req.db, user_id=req.user_id or 0):
        return build_recipe_response(message=EMPTY_INVENTORY_REPLY, intent=req.intent)
    return None


class LegacyRecipeEngine:
    """기존 Handler를 그대로 호출하는 레거시 실행기."""

    def run(self, req: RecipeAgentRequest) -> RecipeAgentResult:
        guarded = _fridge_login_guard(req)
        if guarded is not None:
            return guarded

        if req.intent == "recipe.search":
            reply, actions, sources = handle_recipe_search(req.db, req.text)
        elif req.intent == "recipe.pairing":
            reply, actions = handle_recipe_pairing(req.text)
            sources = []
        elif req.intent == "recipe.recommend":
            reply, actions = handle_recipe_recommend(req.db, req.user_id or 0, req.text, req.history, req.settings_obj)
            sources = []
        else:
            reply, actions = handle_recipe_recommend(req.db, req.user_id or 0, req.text, req.history, req.settings_obj)
            sources = []

        return build_recipe_response(
            message=reply, intent=req.intent, actions=actions, sources=sources,
        )


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
) -> LegacyRecipeEngine | PairingTemplateEngine | SearchTemplateEngine | IngredientTemplateEngine | FridgeTemplateEngine:
    """intent + text에 따라 실행기를 선택한다."""
    if intent == "recipe.pairing":
        return PairingTemplateEngine()
    if intent == "recipe.search":
        return SearchTemplateEngine()
    if intent == "recipe.recommend" and _extract_recipe_ingredient(text):
        return IngredientTemplateEngine()
    if intent == "recipe.recommend":
        return FridgeTemplateEngine()
    return LegacyRecipeEngine()


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
    """recipe_search_service를 ToolResult로 감싼다. ponytail: 현재 미사용. Orchestrator 전환 시 활용."""
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
    """recommendation_service를 ToolResult로 감싼다. ponytail: 현재 미사용. Orchestrator 전환 시 활용."""
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
    """추천 후보를 보유 재료·부족 재료·점수 기준으로 정렬한다. ponytail: 현재 미사용. Orchestrator 전환 시 활용."""
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
    """레시피 후보에서 프론트엔드 Action 목록을 생성한다. ponytail: 현재 미사용. Orchestrator 전환 시 활용."""
    try:
        from .recipe_utils import _recipe_actions
        actions = _recipe_actions(items)
        return ToolResult(ok=True, data={"actions": actions, "total": len(actions)}, source="build_actions")
    except Exception as e:
        return ToolResult(ok=False, error=str(e), source="build_actions")


def external_search_tool(keyword: str, query_text: str | None = None) -> ToolResult:
    """외부 소스(Tavily)로 레시피를 검색하고 요약한다. ponytail: 현재 미사용. Orchestrator 전환 시 활용."""
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


if __name__ == "__main__":
    def _check_output_contract(result: dict) -> None:
        assert set(result) == {"response_text", "actions", "sources"}
        assert isinstance(result["response_text"], str)
        assert isinstance(result["actions"], list)
        assert isinstance(result["sources"], list)

    def _test_contract():
        """외부 계약 + 경계 규칙 검증"""
        internal = build_recipe_response(
            message="테스트",
            intent="recipe.search",
            actions=[{"label": "김치볶음밥", "url": "/recipes/1"}],
            sources=[{"title": "출처", "url": "https://example.com"}],
        )
        assert internal.agent == "recipe"
        assert internal.ok is True
        assert internal.actions[0]["label"] == "김치볶음밥"

        supervisor = to_supervisor_state(internal)
        assert set(supervisor) == {"response_text", "actions", "sources"}
        assert supervisor["response_text"] == "테스트"
        assert len(supervisor["actions"]) == 1
        assert supervisor["sources"][0]["title"] == "출처"
        _check_output_contract(supervisor)
        assert "meta" not in supervisor
        assert "error" not in supervisor

        source = inspect.getsource(build_recipe_response) + inspect.getsource(to_supervisor_state)
        assert "GraphState" not in source

        req = RecipeAgentRequest(
            text="테스트", db=None, user_id=1,
            history=[], settings_obj=None, intent="recipe.search",
        )
        assert req.text == "테스트"
        assert req.intent == "recipe.search"

        engine = LegacyRecipeEngine()
        assert hasattr(engine, "run")

        selected = _select_engine("recipe.search")
        assert isinstance(selected, SearchTemplateEngine)

        state = RecipeExecutionState(req=req)
        assert state.template is None
        assert state.steps_done == []
        assert state.intermediate == {}

        templates = {TEMPLATE_RECIPE_SEARCH, TEMPLATE_INGREDIENT_RECOMMEND, TEMPLATE_FRIDGE_RECOMMEND, TEMPLATE_RECIPE_PAIRING}
        assert len(templates) == 4

        assert SEARCH_TEMPLATE_FIELDS == (
            "keyword", "recipe_candidates", "selected_recipes", "actions", "sources",
        )
        assert len(set(SEARCH_TEMPLATE_FIELDS)) == len(SEARCH_TEMPLATE_FIELDS)

        assert INGREDIENT_TEMPLATE_FIELDS == (
            "ingredient", "constraints", "recipe_candidates", "selected_recipes", "actions",
        )
        assert len(set(INGREDIENT_TEMPLATE_FIELDS)) == len(INGREDIENT_TEMPLATE_FIELDS)

        assert FRIDGE_TEMPLATE_FIELDS == (
            "inventory_status", "user_preferences", "recipe_candidates",
            "ranked_recipes", "owned_ingredient_count", "missing_ingredient_count", "actions",
        )
        assert len(set(FRIDGE_TEMPLATE_FIELDS)) == len(FRIDGE_TEMPLATE_FIELDS)

        assert _select_template("recipe.search", "김치볶음밥 레시피") == TEMPLATE_RECIPE_SEARCH
        assert _select_template("recipe.pairing", "파스타와 어울리는 반찬") == TEMPLATE_RECIPE_PAIRING
        assert _select_template("recipe.recommend", "냉장고 재료로 뭐 해먹지?") == TEMPLATE_FRIDGE_RECOMMEND
        assert _select_template("recipe.recommend", "두부로 뭐 해먹지?") == TEMPLATE_INGREDIENT_RECOMMEND

        ok_result = ToolResult(ok=True, data={"recipes": []}, source="search")
        assert ok_result.ok and ok_result.data is not None and ok_result.error is None
        fail_result = ToolResult(ok=False, error="timeout", source="search")
        assert not fail_result.ok and fail_result.data is None
        empty_result = ToolResult(ok=True, data=None, source="search")
        assert empty_result.ok and empty_result.data is None

        assert callable(search_recipe_tool)
        assert callable(recommend_recipe_tool)
        assert callable(build_recommend_config_tool)
        assert callable(sort_candidates_tool)
        assert callable(exclude_previous_tool)
        assert callable(build_actions_tool)
        assert callable(external_search_tool)
        assert callable(handle_recipe_pairing)
        assert callable(pairing_tool)
        assert hasattr(PairingTemplateEngine(), "run")
        assert isinstance(_select_engine("recipe.pairing"), PairingTemplateEngine)
        assert isinstance(_select_engine("recipe.search"), SearchTemplateEngine)
        assert isinstance(_select_engine("recipe.recommend", "두부로 뭐 해먹지?"), IngredientTemplateEngine)
        assert isinstance(_select_engine("recipe.recommend", "오늘 뭐 해먹지?"), FridgeTemplateEngine)
        assert hasattr(IngredientTemplateEngine(), "run")
        assert hasattr(FridgeTemplateEngine(), "run")
        assert callable(rank_search_candidates_tool)
        assert callable(search_ingredient_relax_tool)
        assert callable(_fill_search_pipeline)
        assert callable(_fill_ingredient_pipeline)
        assert callable(_fill_fridge_pipeline)
        assert callable(_render_search_response)
        assert callable(_render_ingredient_response)
        assert callable(_render_fridge_response)
        assert callable(_fridge_login_guard)
        assert callable(_fridge_empty_guard)
        assert callable(check_required_fields)
        assert callable(check_recipe_integrity)
        assert callable(check_recommend_constraints)
        assert callable(build_repair_targets)
        assert callable(apply_repair_targets)
        assert callable(review_recipe_quality)
        assert ENABLE_LLM_REVIEWER is False
        assert callable(collect_external_jobs)
        assert callable(filter_independent_jobs)
        assert callable(run_independent_external_jobs)

    def _test_behavior():
        """기능 동작 검증 (mock 핸들러 / Tool 사용)"""
        import ai.agents.recipe_agent.recipe_agent as agent

        orig_recommend = agent.handle_recipe_recommend
        orig_search_tool = agent.search_recipe_tool
        orig_external = agent.external_search_tool
        orig_relax = agent.search_ingredient_relax_tool
        orig_recommend_tool = agent.recommend_recipe_tool

        def fake_recommend(
            db: Any,
            user_id: int,
            text: str,
            history: list | None = None,
            settings_obj: Any = None,
        ) -> tuple[str, list[dict[str, Any]]]:
            return f"recommend:{text}", [{"label": "두부찌개", "url": "/recipes/2"}]

        def fake_search_tool(db: Any, keyword: str) -> ToolResult:
            return ToolResult(
                ok=True,
                data={"items": [{"recipe_id": 1, "title": "김치볶음밥"}], "total": 1},
                source="recipe_search",
            )

        def fake_external(keyword: str, query_text: str | None = None) -> ToolResult:
            return ToolResult(
                ok=True,
                data={
                    "summary": f"{keyword} 웹 검색",
                    "sources": [{"title": "출처", "url": "https://example.com"}],
                },
                source="external_search",
            )

        def fake_relax(db: Any, ingredient: str) -> ToolResult:
            return ToolResult(
                ok=True,
                data={
                    "items": [{"recipe_id": 2, "title": "두부찌개"}],
                    "total": 1,
                    "constraints": dict(CONSTRAINT_EASY_30),
                },
                source="ingredient_relax",
            )

        import ai.agents.inventory_agent.inventory_agent as inv

        orig_empty = inv.is_inventory_empty
        agent.handle_recipe_recommend = fake_recommend
        agent.search_recipe_tool = fake_search_tool
        agent.external_search_tool = fake_external
        try:
            r = agent.run_recipe_agent("김치볶음밥 레시피", db=None, intent="recipe.search")
            assert isinstance(_select_engine("recipe.search"), SearchTemplateEngine)
            assert set(r) == {"response_text", "actions", "sources"}
            assert "관련 레시피예요." in r["response_text"]
            assert "김치볶음밥" in r["response_text"]
            assert r["actions"] and r["actions"][0]["url"] == "/recipes/1"
            assert r["sources"] == []
            _check_output_contract(r)

            agent.search_ingredient_relax_tool = fake_relax
            r = agent.run_recipe_agent("두부로 뭐 해먹지?", db=None, user_id=1, intent="recipe.recommend")
            assert isinstance(_select_engine("recipe.recommend", "두부로 뭐 해먹지?"), IngredientTemplateEngine)
            assert set(r) == {"response_text", "actions", "sources"}
            assert "30분 이내 초급 레시피는" in r["response_text"]
            assert "1. 두부찌개" in r["response_text"]
            assert r["sources"] == []
            _check_output_contract(r)

            inv.is_inventory_empty = lambda **kwargs: False
            agent.recommend_recipe_tool = lambda db, user_id, settings_obj=None: ToolResult(
                ok=True,
                data={
                    "items": [
                        {
                            "recipe_id": 10,
                            "title": "계란볶음밥",
                            "owned_ingredient_count": 3,
                            "missing_ingredient_count": 0,
                            "final_score": 0.9,
                        },
                    ],
                    "total": 1,
                },
                source="recommendation",
            )
            r = agent.run_recipe_agent("오늘 뭐 해먹지?", db=None, user_id=1, intent="recipe.recommend")
            assert isinstance(_select_engine("recipe.recommend", "오늘 뭐 해먹지?"), FridgeTemplateEngine)
            assert "완벽하게" in r["response_text"]
            assert "계란볶음밥" in r["response_text"]
            assert r["actions"] and r["actions"][0]["url"] == "/recipes/10"
            _check_output_contract(r)

            r = agent.run_recipe_agent("오늘 뭐 해먹지?", db=None, user_id=None, intent="recipe.recommend")
            assert LOGIN_REQUIRED_REPLY in r["response_text"]
            assert r["actions"] == [] and r["sources"] == []
            _check_output_contract(r)

            inv.is_inventory_empty = lambda **kwargs: True
            r = agent.run_recipe_agent("오늘 뭐 해먹지?", db=None, user_id=1, intent="recipe.recommend")
            assert inv.EMPTY_INVENTORY_REPLY in r["response_text"]
            assert r["actions"] == []
            _check_output_contract(r)

            assert "placeholder" not in r["response_text"]

            r = agent.run_recipe_agent("김치볶음밥이랑 먹기 좋은 음식", db=None, intent="recipe.pairing")
            assert isinstance(_select_engine("recipe.pairing"), PairingTemplateEngine)
            assert "김치볶음밥" in r["response_text"]
            assert "계란국" in r["response_text"]
            assert r["actions"] == []
            assert r["sources"] == []
            _check_output_contract(r)

            state = RecipeExecutionState(
                req=RecipeAgentRequest(
                    text="김치볶음밥 레시피",
                    db=None,
                    user_id=None,
                    history=[],
                    settings_obj=None,
                    intent="recipe.search",
                ),
            )
            state = agent._fill_search_pipeline(state)
            assert set(SEARCH_TEMPLATE_FIELDS) <= set(state.intermediate)
            assert check_required_fields(state) == []
            assert not state.intermediate.get("integrity_issues")
            assert state.intermediate["keyword"]
            assert len(state.intermediate["selected_recipes"]) <= 3
            assert state.template == TEMPLATE_RECIPE_SEARCH
            del state.intermediate["keyword"]
            assert "keyword" in check_required_fields(state)
            state.intermediate["keyword"] = "김치볶음밥"
            assert check_recipe_integrity([]) == []
            assert "missing_recipe_id:0" in check_recipe_integrity([{"title": "A"}])
            assert "missing_title:0" in check_recipe_integrity([{"recipe_id": 1, "title": ""}])
            assert "duplicate_recipe_id:1" in check_recipe_integrity([
                {"recipe_id": 1, "title": "A"}, {"recipe_id": 1, "title": "B"},
            ])
            assert "too_many_items" in check_recipe_integrity([
                {"recipe_id": i, "title": str(i)} for i in range(4)
            ])
            bad_ing = RecipeExecutionState(
                req=RecipeAgentRequest(
                    text="두부로 뭐 해먹지?", db=None, user_id=1,
                    history=[], settings_obj=None, intent="recipe.recommend",
                ),
                template=TEMPLATE_INGREDIENT_RECOMMEND,
            )
            bad_ing.intermediate["constraints"] = dict(CONSTRAINT_EASY_30)
            bad_ing.intermediate["selected_recipes"] = [
                {"recipe_id": 1, "title": "A", "difficulty": "고급", "cooking_time_min": 45},
            ]
            ci = check_recommend_constraints(bad_ing)
            assert "difficulty_mismatch:0" in ci
            assert "cooking_time_mismatch:0" in ci
            bad_fridge = RecipeExecutionState(
                req=RecipeAgentRequest(
                    text="오늘 뭐 해먹지?", db=None, user_id=1,
                    history=[], settings_obj=None, intent="recipe.recommend",
                ),
                template=TEMPLATE_FRIDGE_RECOMMEND,
            )
            bad_fridge.intermediate["ranked_recipes"] = [
                {"recipe_id": 1, "title": "X", "owned_ingredient_count": -1, "missing_ingredient_count": 0},
            ]
            assert "owned_missing_contradiction:0" in check_recommend_constraints(bad_fridge)
            miss_kw = RecipeExecutionState(
                req=RecipeAgentRequest(
                    text="김치볶음밥 레시피", db=None, user_id=None,
                    history=[], settings_obj=None, intent="recipe.search",
                ),
                template=TEMPLATE_RECIPE_SEARCH,
            )
            miss_kw.intermediate["missing_required_fields"] = ["keyword"]
            targets = build_repair_targets(miss_kw)
            assert any(t.field == "keyword" and t.reason == "missing_required_field" for t in targets)
            empty_cand = RecipeExecutionState(
                req=RecipeAgentRequest(
                    text="없는레시피", db=None, user_id=None,
                    history=[], settings_obj=None, intent="recipe.search",
                ),
                template=TEMPLATE_RECIPE_SEARCH,
            )
            empty_cand.intermediate["recipe_candidates"] = []
            targets = build_repair_targets(empty_cand)
            assert any(
                t.field == "recipe_candidates"
                and t.reason == "empty_candidates"
                and t.fallback_tool == "external_search_tool"
                for t in targets
            )
            rec_err = RecipeExecutionState(
                req=RecipeAgentRequest(
                    text="오늘 뭐 해먹지?", db=None, user_id=1,
                    history=[], settings_obj=None, intent="recipe.recommend",
                ),
                template=TEMPLATE_FRIDGE_RECOMMEND,
            )
            rec_err.intermediate["recommend_error"] = "db down"
            targets = build_repair_targets(rec_err)
            assert any(t.field == "recipe_candidates" and "db down" in t.reason for t in targets)

            repair_state = RecipeExecutionState(
                req=RecipeAgentRequest(
                    text="없는레시피xyz", db=None, user_id=None,
                    history=[], settings_obj=None, intent="recipe.search",
                ),
                template=TEMPLATE_RECIPE_SEARCH,
            )
            repair_state.intermediate["keyword"] = "없는레시피xyz"
            repair_state.intermediate["recipe_candidates"] = []
            repair_state.intermediate["selected_recipes"] = []
            repair_state.intermediate["actions"] = []
            repair_state.intermediate["sources"] = []
            repair_state.intermediate["repair_targets"] = [
                RepairTarget(
                    field="recipe_candidates",
                    reason="empty_candidates",
                    fallback_tool="external_search_tool",
                ),
                RepairTarget(
                    field="recipe_candidates",
                    reason="empty_candidates_again",
                    fallback_tool="external_search_tool",
                ),
            ]
            repair_state = agent.apply_repair_targets(repair_state)
            assert repair_state.steps_done.count("repair_external_search") == 1
            assert repair_state.intermediate.get("sources")
            assert repair_state.intermediate.get("external_summary") is not None

            empty_res = build_recipe_response(message="", intent="recipe.search")
            empty_st = RecipeExecutionState(
                req=RecipeAgentRequest(
                    text="x", db=None, user_id=None,
                    history=[], settings_obj=None, intent="recipe.search",
                ),
            )
            assert review_recipe_quality(empty_st, empty_res) == []
            orig_flag = agent.ENABLE_LLM_REVIEWER
            agent.ENABLE_LLM_REVIEWER = True
            try:
                notes = agent.review_recipe_quality(empty_st, empty_res)
                assert "empty_message" in notes
                attached = agent._attach_review_notes(empty_st, empty_res)
                assert attached.message == ""
                assert attached.meta.get("review_notes") == notes
            finally:
                agent.ENABLE_LLM_REVIEWER = orig_flag

            empty_jobs_st = RecipeExecutionState(
                req=RecipeAgentRequest(
                    text="없는레시피xyz", db=None, user_id=None,
                    history=[], settings_obj=None, intent="recipe.search",
                ),
                template=TEMPLATE_RECIPE_SEARCH,
            )
            empty_jobs_st.intermediate["keyword"] = "없는레시피xyz"
            empty_jobs_st.intermediate["recipe_candidates"] = []
            jobs = collect_external_jobs(empty_jobs_st)
            assert len(jobs) == 1
            assert jobs[0].tool == "external_search_tool"
            assert jobs[0].fills_field == "external_summary"
            filled_st = RecipeExecutionState(
                req=empty_jobs_st.req,
                template=TEMPLATE_RECIPE_SEARCH,
            )
            filled_st.intermediate["recipe_candidates"] = [{"recipe_id": 1, "title": "A"}]
            assert collect_external_jobs(filled_st) == []
            one = [
                ExternalJob(name="a", tool="external_search_tool", kwargs={}, fills_field="external_summary"),
            ]
            assert filter_independent_jobs(one) == one
            dup = one + [
                ExternalJob(name="b", tool="external_search_tool", kwargs={}, fills_field="external_summary"),
            ]
            assert len(filter_independent_jobs(dup)) == 1
            bad = [
                ExternalJob(name="c", tool="not_allowed", kwargs={}, fills_field="other"),
            ]
            assert filter_independent_jobs(bad) == []

            run_st = RecipeExecutionState(
                req=RecipeAgentRequest(
                    text="없는레시피xyz", db=None, user_id=None,
                    history=[], settings_obj=None, intent="recipe.search",
                ),
                template=TEMPLATE_RECIPE_SEARCH,
            )
            run_st.intermediate["independent_external_jobs"] = [
                ExternalJob(
                    name="external_search",
                    tool="external_search_tool",
                    kwargs={"keyword": "없는레시피xyz", "query_text": "없는레시피xyz"},
                    fills_field="external_summary",
                ),
            ]
            run_st = agent.run_independent_external_jobs(run_st)
            assert "run_external_search" in run_st.steps_done
            assert run_st.intermediate.get("external_summary") is not None
            assert run_st.intermediate.get("sources")

            # P10-4: fail must not overwrite an existing external_summary
            keep_st = RecipeExecutionState(
                req=RecipeAgentRequest(
                    text="없는레시피xyz", db=None, user_id=None,
                    history=[], settings_obj=None, intent="recipe.search",
                ),
                template=TEMPLATE_RECIPE_SEARCH,
            )
            keep_st.intermediate["external_summary"] = "keep"
            keep_st.intermediate["independent_external_jobs"] = [
                ExternalJob(
                    name="external_search",
                    tool="external_search_tool",
                    kwargs={"keyword": "x", "query_text": "x"},
                    fills_field="external_summary",
                ),
            ]
            _real_ext = agent.external_search_tool
            agent.external_search_tool = lambda keyword, query_text=None: ToolResult(
                ok=False, data=None, source="web_search", error="boom",
            )
            keep_st = agent.run_independent_external_jobs(keep_st)
            agent.external_search_tool = _real_ext
            assert keep_st.intermediate.get("external_summary") == "keep"
            assert keep_st.intermediate.get("failed_external_jobs")
            assert "run_fail:external_search" in keep_st.steps_done
            assert "run_external_search" not in keep_st.steps_done

            # P10-4: fail with no prior summary → failed only, no summary key
            fail_st = RecipeExecutionState(
                req=RecipeAgentRequest(
                    text="없는레시피xyz", db=None, user_id=None,
                    history=[], settings_obj=None, intent="recipe.search",
                ),
                template=TEMPLATE_RECIPE_SEARCH,
            )
            fail_st.intermediate["independent_external_jobs"] = [
                ExternalJob(
                    name="external_search",
                    tool="external_search_tool",
                    kwargs={"keyword": "x", "query_text": "x"},
                    fills_field="external_summary",
                ),
            ]
            agent.external_search_tool = lambda keyword, query_text=None: ToolResult(
                ok=False, data=None, source="web_search", error="boom",
            )
            fail_st = agent.run_independent_external_jobs(fail_st)
            agent.external_search_tool = _real_ext
            assert "external_summary" not in fail_st.intermediate
            assert fail_st.intermediate.get("failed_external_jobs")
            assert "run_fail:external_search" in fail_st.steps_done

            result = agent._render_search_response(state)
            out = to_supervisor_state(result)
            kw = state.intermediate["keyword"]
            assert f"{kw} 관련 레시피예요." in out["response_text"]
            assert "1. 김치볶음밥" in out["response_text"]
            assert out["actions"] and out["actions"][0]["url"] == "/recipes/1"
            assert out["sources"] == []

            agent.search_recipe_tool = lambda db, keyword: ToolResult(
                ok=True, data={"items": [], "total": 0}, source="recipe_search",
            )
            r = agent.run_recipe_agent("없는레시피xyz", db=None, intent="recipe.search")
            _check_output_contract(r)
            assert "웹 검색" in r["response_text"]
            assert r["sources"] and r["sources"][0]["url"] == "https://example.com"
            assert r["actions"] == []

            r = agent.run_recipe_agent("감자튀김 에어프라이기 시간", db=None, intent="recipe.search")
            _check_output_contract(r)
            assert "웹 검색" in r["response_text"]
            assert r["sources"]
            assert r["actions"] == []

            # -- P0-4: Supervisor 통합 기준선 --
            agent.search_recipe_tool = fake_search_tool
            r = agent.run_recipe_agent(
                "김치볶음밥 레시피",
                db=None, user_id=None, history=[], settings_obj=None, intent=None,
            )
            _check_output_contract(r)

            agent.search_ingredient_relax_tool = fake_relax
            r = agent.run_recipe_agent(
                "두부로 뭐 해먹지?",
                db=None, user_id=1, history=[], settings_obj=None, intent="recipe.recommend",
            )
            _check_output_contract(r)
            assert len(r["response_text"]) > 0

            r = agent.run_recipe_agent(
                "김치볶음밥이랑 어울리는 반찬",
                db=None, user_id=None, history=[], settings_obj=None, intent=None,
            )
            _check_output_contract(r)

            class FakeMsg:
                def __init__(self, role, text):
                    self.role = role
                    self.text = text
            r = agent.run_recipe_agent(
                "다른 거 추천해줘",
                db=None, user_id=1,
                history=[FakeMsg("bot", "이전에 김치볶음밥을 추천했습니다.")],
                settings_obj=None, intent="recipe.search",
            )
            _check_output_contract(r)

            # -- P3-4: Shadow 비교 --
            assert _select_template("recipe.search", "김치볶음밥 레시피") == TEMPLATE_RECIPE_SEARCH
            assert _select_template("recipe.recommend", "두부로 뭐 해먹지?") == TEMPLATE_INGREDIENT_RECOMMEND
            assert _select_template("recipe.recommend", "오늘 뭐 해먹지?") == TEMPLATE_INGREDIENT_RECOMMEND
            assert _select_template("recipe.pairing", "김치볶음밥이랑 먹기 좋은 음식") == TEMPLATE_RECIPE_PAIRING
            assert _select_template("recipe.search", "없는레시피xyz") == TEMPLATE_RECIPE_SEARCH

            agent.search_ingredient_relax_tool = lambda db, ingredient: ToolResult(
                ok=True,
                data={
                    "items": [{"recipe_id": 2, "title": "두부찌개"}],
                    "total": 1,
                    "constraints": dict(CONSTRAINT_EASY_30),
                },
                source="ingredient_relax",
            )
            state = RecipeExecutionState(
                req=RecipeAgentRequest(
                    text="두부로 뭐 해먹지?",
                    db=None,
                    user_id=1,
                    history=[],
                    settings_obj=None,
                    intent="recipe.recommend",
                ),
            )
            state = agent._fill_ingredient_pipeline(state)
            assert set(INGREDIENT_TEMPLATE_FIELDS) <= set(state.intermediate)
            assert check_required_fields(state) == []
            assert not state.intermediate.get("integrity_issues")
            assert not state.intermediate.get("constraint_issues")
            assert state.intermediate["ingredient"]
            assert state.intermediate["recipe_candidates"]
            assert state.intermediate["selected_recipes"]
            assert state.intermediate["selected_recipes"][0]["title"] == "두부찌개"
            assert state.intermediate["constraints"] == CONSTRAINT_EASY_30
            assert state.template == TEMPLATE_INGREDIENT_RECOMMEND
            result = agent._render_ingredient_response(state)
            out = to_supervisor_state(result)
            assert "30분 이내 초급 레시피는" in out["response_text"]
            assert "1. 두부찌개" in out["response_text"]
            assert any(a.get("url") == "/recipes/2" for a in out["actions"])
            assert any("레시피 더 보기" in a.get("label", "") for a in out["actions"])

            agent.search_ingredient_relax_tool = lambda db, ingredient: ToolResult(
                ok=True,
                data={"items": [], "total": 0, "constraints": {}},
                source="ingredient_relax",
            )
            state = RecipeExecutionState(
                req=RecipeAgentRequest(
                    text="두부로 뭐 해먹지?",
                    db=None,
                    user_id=1,
                    history=[],
                    settings_obj=None,
                    intent="recipe.recommend",
                ),
            )
            state = agent._fill_ingredient_pipeline(state)
            result = agent._render_ingredient_response(state)
            out = to_supervisor_state(result)
            assert "웹 검색" in out["response_text"]
            assert out["actions"] == []
            assert out["sources"] == []

            agent.search_ingredient_relax_tool = lambda db, ingredient: ToolResult(
                ok=True,
                data={
                    "items": [
                        {"recipe_id": 1, "title": "두부찌개"},
                        {"recipe_id": 2, "title": "두부조림"},
                    ],
                    "total": 2,
                    "constraints": dict(CONSTRAINT_EASY_30),
                },
                source="ingredient_relax",
            )
            state = RecipeExecutionState(
                req=RecipeAgentRequest(
                    text="두부로 뭐 해먹지?",
                    db=None,
                    user_id=1,
                    history=[FakeMsg("bot", "두부찌개를 추천했습니다.")],
                    settings_obj=None,
                    intent="recipe.recommend",
                ),
            )
            state = agent._fill_ingredient_pipeline(state)
            assert state.intermediate["selected_recipes"]
            assert state.intermediate["selected_recipes"][0]["title"] == "두부조림"
            assert len(state.intermediate["selected_recipes"]) <= 3

            state = RecipeExecutionState(
                req=RecipeAgentRequest(
                    text="두부로 뭐 해먹지?",
                    db=None,
                    user_id=1,
                    history=[FakeMsg("bot", "두부찌개와 두부조림을 추천했습니다.")],
                    settings_obj=None,
                    intent="recipe.recommend",
                ),
            )
            state = agent._fill_ingredient_pipeline(state)
            assert state.intermediate["selected_recipes"] == state.intermediate["recipe_candidates"][:3]

            inv.is_inventory_empty = lambda **kwargs: True
            req = RecipeAgentRequest(
                text="오늘 뭐 해먹지?", db=None, user_id=1,
                history=[], settings_obj=None, intent="recipe.recommend",
            )
            guarded = agent._fridge_empty_guard(req)
            assert guarded is not None
            assert inv.EMPTY_INVENTORY_REPLY in guarded.message
            assert guarded.actions == []

            class FakeSettings:
                expiringFirst = False
                excludeDislikes = False

            tr = agent.build_recommend_config_tool(FakeSettings())
            assert tr.ok
            assert tr.data["config"].mode == "fridge_all"
            assert tr.data["exclude_dislikes"] is False

            tr_default = agent.build_recommend_config_tool(None)
            assert tr_default.ok
            assert tr_default.data["config"].mode == "fridge_consume"
            assert tr_default.data["exclude_dislikes"] is True

            agent.recommend_recipe_tool = lambda db, user_id, settings_obj=None: ToolResult(
                ok=True,
                data={
                    "items": [
                        {"recipe_id": 1, "title": "A", "owned_ingredient_count": 1, "missing_ingredient_count": 2, "final_score": 10},
                        {"recipe_id": 2, "title": "B", "owned_ingredient_count": 3, "missing_ingredient_count": 0, "final_score": 5},
                    ],
                    "total": 2,
                },
                source="recommendation",
            )
            state = RecipeExecutionState(
                req=RecipeAgentRequest(
                    text="오늘 뭐 해먹지?", db=None, user_id=1,
                    history=[], settings_obj=None, intent="recipe.recommend",
                ),
            )
            state = agent._fill_fridge_pipeline(state)
            assert state.intermediate["ranked_recipes"][0]["title"] == "B"
            assert state.template == TEMPLATE_FRIDGE_RECOMMEND
            assert check_required_fields(state) == []
            assert not state.intermediate.get("integrity_issues")
            assert not state.intermediate.get("constraint_issues")
            result = agent._render_fridge_response(state)
            assert "완벽하게" in result.message
            assert "1. B" in result.message

            state = RecipeExecutionState(
                req=RecipeAgentRequest(
                    text="오늘 뭐 해먹지?", db=None, user_id=1,
                    history=[], settings_obj=None, intent="recipe.recommend",
                ),
            )
            state.intermediate["ranked_recipes"] = [
                {"title": "C", "owned_ingredient_count": 2, "missing_ingredient_count": 1, "final_score": 1},
            ]
            result = agent._render_fridge_response(state)
            assert "부족한 재료가 약간" in result.message

            state.intermediate["ranked_recipes"] = [
                {"title": "D", "owned_ingredient_count": 0, "missing_ingredient_count": 3, "final_score": 0},
            ]
            result = agent._render_fridge_response(state)
            assert "매칭되는 레시피를 찾지 못했어요" in result.message

            agent.recommend_recipe_tool = lambda db, user_id, settings_obj=None: ToolResult(
                ok=False, error="db down", source="recommendation",
            )
            state = RecipeExecutionState(
                req=RecipeAgentRequest(
                    text="오늘 뭐 해먹지?", db=None, user_id=1,
                    history=[], settings_obj=None, intent="recipe.recommend",
                ),
            )
            state = agent._fill_fridge_pipeline(state)
            result = agent._render_fridge_response(state)
            assert "db down" in result.message or "불러오지 못했어요" in result.message
        finally:
            agent.handle_recipe_recommend = orig_recommend
            agent.search_recipe_tool = orig_search_tool
            agent.external_search_tool = orig_external
            agent.search_ingredient_relax_tool = orig_relax
            agent.recommend_recipe_tool = orig_recommend_tool
            inv.is_inventory_empty = orig_empty

    _test_contract()
    _test_behavior()
    print("recipe_agent ok")
