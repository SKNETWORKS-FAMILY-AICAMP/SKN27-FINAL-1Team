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


def _select_engine(intent: str) -> LegacyRecipeEngine:
    """intent에 따라 실행기를 선택한다. ponytail: 현재 모든 intent가 Legacy를 반환. 신규 Orchestrator 추가 시 여기에 분기."""
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
            assert "김치볶음밥" in r["response_text"]
            assert "계란국" in r["response_text"]
            assert r["actions"] == []
            assert r["sources"] == []
            _check_output_contract(r)

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
