from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any

from .recipe_handlers import handle_recipe_pairing, handle_recipe_recommend, handle_recipe_search
from .recipe_intents import analyze_recipe_intent
from .recipe_utils import LOGIN_REQUIRED_REPLY, _requires_login

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


class LegacyRecipeEngine:
    """기존 Handler를 그대로 호출하는 레거시 실행기."""

    def run(self, req: RecipeAgentRequest) -> RecipeAgentResult:
        if req.intent == "recipe.recommend" and _requires_login(req.intent, req.text) and not req.user_id:
            return build_recipe_response(message=LOGIN_REQUIRED_REPLY, intent=req.intent)

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


def _select_engine(intent: str) -> LegacyRecipeEngine | PairingTemplateEngine:
    """intent에 따라 실행기를 선택한다."""
    if intent == "recipe.pairing":
        return PairingTemplateEngine()
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


def recommend_recipe_tool(db: Any, user_id: int, settings_obj: Any = None) -> ToolResult:
    """recommendation_service를 ToolResult로 감싼다. ponytail: 현재 미사용. Orchestrator 전환 시 활용."""
    try:
        from .recipe_handlers import recommendation_service
        from app.backend.services.recommendation_service.recommend_config import RecipeRecommendConfig
        config = RecipeRecommendConfig.fridge_consume_preset()
        if settings_obj:
            if not getattr(settings_obj, "expiringFirst", True):
                config.mode = "fridge_all"
            if not getattr(settings_obj, "excludeDislikes", True):
                config.exclude_dislikes = False
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


def _fill_search_pipeline(state: RecipeExecutionState) -> RecipeExecutionState:
    """내부 검색 단계로 SEARCH_TEMPLATE_FIELDS를 채운다. ponytail: 엔진 미연결. P6-4에서 사용."""
    from .recipe_utils import _extract_keyword, _extract_recipe_ingredient

    text = state.req.text
    keyword = _extract_recipe_ingredient(text) or _extract_keyword(text)
    state.intermediate["keyword"] = keyword
    state.steps_done.append("extract_keyword")

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
    return state


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
    engine = _select_engine(req.intent)
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
        assert isinstance(selected, LegacyRecipeEngine)

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
        assert callable(sort_candidates_tool)
        assert callable(exclude_previous_tool)
        assert callable(build_actions_tool)
        assert callable(external_search_tool)
        assert callable(handle_recipe_pairing)
        assert callable(pairing_tool)
        assert hasattr(PairingTemplateEngine(), "run")
        assert isinstance(_select_engine("recipe.pairing"), PairingTemplateEngine)
        assert isinstance(_select_engine("recipe.search"), LegacyRecipeEngine)
        assert isinstance(_select_engine("recipe.recommend"), LegacyRecipeEngine)
        assert callable(rank_search_candidates_tool)
        assert callable(_fill_search_pipeline)

    def _test_behavior():
        """기능 동작 검증 (mock 핸들러 사용)"""
        import ai.agents.recipe_agent.recipe_agent as agent

        orig_search = agent.handle_recipe_search
        orig_recommend = agent.handle_recipe_recommend

        def fake_search(db: Any, text: str) -> tuple[str, list[dict[str, Any]], list[dict[str, str]]]:
            return f"search:{text}", [{"label": "김치볶음밥", "url": "/recipes/1"}], []

        def fake_recommend(
            db: Any,
            user_id: int,
            text: str,
            history: list | None = None,
            settings_obj: Any = None,
        ) -> tuple[str, list[dict[str, Any]]]:
            return f"recommend:{text}", [{"label": "두부찌개", "url": "/recipes/2"}]

        agent.handle_recipe_search = fake_search
        agent.handle_recipe_recommend = fake_recommend
        try:
            r = agent.run_recipe_agent("김치볶음밥 레시피", db=None, intent="recipe.search")
            assert set(r) == {"response_text", "actions", "sources"}
            assert r["response_text"] == "search:김치볶음밥 레시피"
            assert r["actions"][0]["url"] == "/recipes/1"
            assert r["sources"] == []
            _check_output_contract(r)

            r = agent.run_recipe_agent("두부로 뭐 해먹지?", db=None, user_id=1, intent="recipe.recommend")
            assert set(r) == {"response_text", "actions", "sources"}
            assert r["response_text"] == "recommend:두부로 뭐 해먹지?"
            assert len(r["actions"]) == 1
            assert r["sources"] == []
            _check_output_contract(r)

            r = agent.run_recipe_agent("오늘 뭐 해먹지?", db=None, user_id=1)
            assert r["response_text"].startswith("recommend:")

            r = agent.run_recipe_agent("오늘 뭐 해먹지?", db=None, user_id=None, intent="recipe.recommend")
            assert LOGIN_REQUIRED_REPLY in r["response_text"]
            assert r["actions"] == [] and r["sources"] == []
            _check_output_contract(r)

            assert "placeholder" not in r["response_text"]

            r = agent.run_recipe_agent("김치볶음밥이랑 먹기 좋은 음식", db=None, intent="recipe.pairing")
            assert isinstance(_select_engine("recipe.pairing"), PairingTemplateEngine)
            assert "김치볶음밥" in r["response_text"]
            assert "계란국" in r["response_text"]
            assert r["actions"] == []
            assert r["sources"] == []
            _check_output_contract(r)

            orig_search_tool = agent.search_recipe_tool
            agent.search_recipe_tool = lambda db, keyword: ToolResult(
                ok=True,
                data={"items": [{"recipe_id": 1, "title": "김치볶음밥"}], "total": 1},
                source="recipe_search",
            )
            try:
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
                assert state.intermediate["keyword"]
                assert len(state.intermediate["selected_recipes"]) <= 3
                assert state.template == TEMPLATE_RECIPE_SEARCH
            finally:
                agent.search_recipe_tool = orig_search_tool

            agent.handle_recipe_search = lambda db, text: ("결과 없음", [], [])
            r = agent.run_recipe_agent("없는레시피xyz", db=None, intent="recipe.search")
            _check_output_contract(r)
            assert r["actions"] == []

            # -- P0-4: Supervisor 통합 기준선 --
            agent.handle_recipe_search = fake_search
            r = agent.run_recipe_agent(
                "김치볶음밥 레시피",
                db=None, user_id=None, history=[], settings_obj=None, intent=None,
            )
            _check_output_contract(r)

            agent.handle_recipe_recommend = fake_recommend
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
        finally:
            agent.handle_recipe_search = orig_search
            agent.handle_recipe_recommend = orig_recommend

    _test_contract()
    _test_behavior()
    print("recipe_agent ok")
