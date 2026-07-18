from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from app.backend.core.config import settings as app_settings
from langchain_core.tools import BaseTool, tool

try:
    from tavily import TavilyClient
except ImportError:
    TavilyClient = None

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

from .recipe_config import (
    CONSTRAINT_EASY_30,
    CONSTRAINT_INGREDIENT_ONLY,
    ENABLE_LLM_PAIRING,
    MAX_DISPLAY_RECIPES,
    PAIRING_MENU,
    RECIPE_PAIRING_PROMPT,
)
from .recipe_state import (
    RecipeToolPayload,
    RecommendByIngredientInput,
    RecipeToolContext,
    SearchExternalInput,
    SearchRecipesInput,
    SuggestPairingInput,
)
from .recipe_utils import (
    LOGIN_REQUIRED_REPLY,
    _apply_josa,
    _exclude_previous_items,
    _is_relevant_search_result,
    _rank_recipe_items,
    _recipe_actions,
    _sort_fridge_candidates,
)


@dataclass
class ToolResult:
    """Tool 실행 공통 결과."""
    ok: bool
    data: Any = None
    error: str | None = None
    source: str | None = None


# =============================================================================
# search_external 지역 함수
# - reply_external_recipe: Tavily 검색 및 검색 결과 요약
# =============================================================================
def reply_external_recipe(keyword: str, query_text: str | None = None) -> tuple[str, list[dict[str, str]]]:
    """내부 레시피가 없을 때 Tavily 검색 결과로 짧게 안내합니다."""
    if not app_settings.TAVILY_API_KEY or TavilyClient is None:
        return f"{keyword} 관련 레시피는 아직 우리 DB에 없어요. 웹 검색 답변은 Tavily 설정 후 사용할 수 있어요.", []

    client = TavilyClient(api_key=app_settings.TAVILY_API_KEY)
    try:
        result = client.search(query=query_text or f"{keyword} 레시피", search_depth="basic", max_results=3)
    except Exception:
        return f"{keyword} 레시피는 웹 검색을 시도했지만 지금은 연결이 불안정해요. 잠시 후 다시 시도해주세요.", []
    results = [item for item in result.get("results", []) if _is_relevant_search_result(keyword, item)][:3]
    sources = [
        {"title": item.get("title") or item.get("url", "출처"), "url": item.get("url", "")}
        for item in results
        if item.get("url")
    ]
    content = "\n".join(item.get("content", "") for item in results if item.get("content"))[:1200]
    if not content:
        return f"{keyword} 레시피를 웹에서도 찾지 못했어요.", sources

    if app_settings.OPENAI_API_KEY and OpenAI is not None:
        try:
            client_ai = OpenAI(api_key=app_settings.OPENAI_API_KEY)
            response = client_ai.chat.completions.create(
                model=app_settings.OPENAI_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "당신은 요리와 냉장고 관리를 도와주는 친절한 비서 챗봇 '밥벌이'입니다. "
                            "검색 결과를 바탕으로 사용자의 질문에 다정하게 대답하세요. "
                            "특정 요리의 레시피를 묻는다면 핵심 조리 흐름을 3문장 이내로 요약해주고, "
                            "메뉴 추천을 원한다면 상황에 어울리는 요리 2~3가지를 다정하게 추천해주세요."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"질문/키워드: {query_text or keyword}\n검색 결과:\n{content}\n\n위 내용을 바탕으로 친절하게 답변해줘.",
                    },
                ],
                temperature=0.2,
            )
            summary = response.choices[0].message.content.strip()
        except Exception:
            summary = content.split(".")[0].strip() + "."
    else:
        summary = content.split(".")[0].strip() + "."

    return summary, sources


# =============================================================================
# suggest_pairing 지역 함수
# - handle_recipe_pairing: 정적 메뉴 → LLM → 기본 메뉴 순서로 곁들임 선택
# - _pairing_with_llm: 정적 메뉴에 없는 주요리의 LLM 곁들임 조회
# =============================================================================
def handle_recipe_pairing(text: str) -> tuple[str, list[dict[str, Any]]]:
    """특정 음식과 함께 먹기 좋은 간단한 곁들임 메뉴를 안내합니다."""
    keyword = re.split(r"이랑|랑|와|과|하고|에", text, maxsplit=1)[0].strip()
    keyword = re.sub(r"^(남은|먹다남은)\s*", "", keyword) or "그 메뉴"
    normalized = keyword.replace(" ", "")
    items = PAIRING_MENU.get(normalized)
    if not items:
        items = _pairing_with_llm(keyword)
    if not items:
        items = ["맑은 국", "상큼한 무침", "피클류", "간단한 구이"]
    reply = f"{keyword}에는 " + ", ".join(items) + "같은 메뉴가 잘 어울려요."
    return reply, []


def _pairing_with_llm(keyword: str) -> list[str]:
    if not ENABLE_LLM_PAIRING or not app_settings.OPENAI_API_KEY or OpenAI is None:
        return []
    try:
        client_ai = OpenAI(api_key=app_settings.OPENAI_API_KEY)
        response = client_ai.chat.completions.create(
            model=app_settings.OPENAI_MODEL,
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": RECIPE_PAIRING_PROMPT},
                {"role": "user", "content": json.dumps({"main_dish": keyword}, ensure_ascii=False)},
            ],
        )
        content = response.choices[0].message.content if response.choices else ""
        data = json.loads(content or "{}")
        raw_items = data.get("items") or []
        if not isinstance(raw_items, list):
            return []
        items = [str(item).strip() for item in raw_items if str(item).strip()]
        return items[:4]
    except Exception:
        return []


# =============================================================================
# search_recipes 지역 함수
# - search_recipe_tool: 재료 검색 후 결과가 없으면 요리명 검색
# =============================================================================
def search_recipe_tool(db: Any, keyword: str) -> ToolResult:
    """recipe_search_service를 ToolResult로 감싼다."""
    try:
        from app.backend.services.recommendation_service.recipe_search_service import recipe_search_service
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


# =============================================================================
# recommend_from_fridge 지역 함수
# - _build_recommend_config: 사용자 추천 설정 변환
# - recommend_recipe_tool: 냉장고 기반 추천 서비스 호출
# =============================================================================
def _build_recommend_config(settings_obj: Any = None) -> tuple[Any, bool]:
    """settings_obj → (RecipeRecommendConfig, exclude_dislikes)."""
    from dataclasses import replace

    from app.backend.services.recommendation_service.recommend_config import RecipeRecommendConfig

    config = RecipeRecommendConfig.fridge_consume_preset()
    exclude_dislikes = True
    if settings_obj:
        if not getattr(settings_obj, "expiringFirst", True):
            config = replace(config, mode="fridge_all")  # type: ignore[arg-type]
        if not getattr(settings_obj, "excludeDislikes", True):
            exclude_dislikes = False
    return config, exclude_dislikes


def recommend_recipe_tool(db: Any, user_id: int, settings_obj: Any = None) -> ToolResult:
    """recommendation_service를 ToolResult로 감싼다."""
    try:
        from app.backend.services.recommendation_service.recommendation_service import recommendation_service

        config, _exclude_dislikes = _build_recommend_config(settings_obj)
        result = recommendation_service.recommend_recipes(db, user_id, config)
        items = result.get("items", [])
        return ToolResult(ok=True, data={"items": items, "total": len(items)}, source="recommendation")
    except Exception as e:
        return ToolResult(ok=False, error=str(e), source="recommendation")


# =============================================================================
# recommend_by_ingredient 지역 함수
# - search_ingredient_relax_tool: 초급·30분 조건 검색 후 주재료 검색으로 완화
# =============================================================================
def search_ingredient_relax_tool(db: Any, ingredient: str) -> ToolResult:
    """주재료+초급+30분 → 주재료만 순으로 검색한다. ponytail: Legacy 완화 순서 고정."""
    try:
        from app.backend.services.recommendation_service.recipe_search_service import recipe_search_service

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


# =============================================================================
# 모든 recipe tool 공용 지역 함수
# - _payload: ToolResult를 모델이 읽는 RecipeToolPayload JSON으로 변환
# - _numbered_list: 추천 레시피 제목을 번호 목록으로 변환
# =============================================================================
def _payload(
    *,
    tool_name: str,
    status: str,
    message: str,
    actions: list[dict[str, Any]] | None = None,
    sources: list[dict[str, str]] | None = None,
    data: dict[str, Any] | None = None,
) -> str:
    return RecipeToolPayload(
        tool=tool_name,
        status=status,
        message=message,
        actions=actions or [],
        sources=sources or [],
        data=data or {},
    ).model_dump_json()


def _numbered_list(items: list[dict[str, Any]]) -> str:
    return "\n".join(f"{index + 1}. {item.get('title') or ''}" for index, item in enumerate(items))


def build_recipe_tools(context: RecipeToolContext) -> list[BaseTool]:
    """실행 의존성을 감춘 LangChain recipe tools를 생성한다."""

    # =========================================================================
    # Tool: search_recipes
    # 지역 함수: search_recipe_tool, _rank_recipe_items, _recipe_actions
    # 공용 함수: _payload, _numbered_list
    # =========================================================================
    @tool("search_recipes", args_schema=SearchRecipesInput)
    def search_recipes(keyword: str) -> str:
        """요리명이나 키워드로 내부 DB의 레시피를 검색합니다."""
        result = search_recipe_tool(context.db, keyword)
        if not result.ok:
            return _payload(
                tool_name="search_recipes",
                status="error",
                message=result.error or "레시피 검색에 실패했어요.",
            )
        items = _rank_recipe_items(keyword, (result.data or {}).get("items", []))[:MAX_DISPLAY_RECIPES]
        if not items:
            return _payload(
                tool_name="search_recipes",
                status="empty",
                message=f"{keyword} 관련 레시피를 내부 DB에서 찾지 못했어요.",
                data={"keyword": keyword},
            )
        return _payload(
            tool_name="search_recipes",
            status="success",
            message=f"{keyword} 관련 레시피예요.\n{_numbered_list(items)}",
            actions=_recipe_actions(items),
            data={"keyword": keyword, "total": len(items)},
        )

    # =========================================================================
    # Tool: recommend_by_ingredient
    # 지역 함수: search_ingredient_relax_tool, _exclude_previous_items,
    #            _apply_josa, _recipe_actions
    # 공용 함수: _payload, _numbered_list
    # =========================================================================
    @tool("recommend_by_ingredient", args_schema=RecommendByIngredientInput)
    def recommend_by_ingredient(ingredient: str) -> str:
        """특정 주재료로 만들 수 있는 쉬운 레시피를 추천합니다."""
        ingredient = ingredient.strip()
        if not ingredient:
            return _payload(
                tool_name="recommend_by_ingredient",
                status="empty",
                message="추천할 재료명을 확인하지 못했어요.",
            )
        result = search_ingredient_relax_tool(context.db, ingredient)
        if not result.ok:
            return _payload(
                tool_name="recommend_by_ingredient",
                status="error",
                message=result.error or "재료 기반 추천에 실패했어요.",
            )
        data = result.data or {}
        items = _exclude_previous_items(data.get("items") or [], context.history)[:MAX_DISPLAY_RECIPES]
        if not items:
            return _payload(
                tool_name="recommend_by_ingredient",
                status="empty",
                message=f"{ingredient} 관련 레시피를 내부 DB에서 찾지 못했어요.",
                data={"ingredient": ingredient},
            )
        constraints = data.get("constraints") or {}
        prefix = (
            f"{_apply_josa(ingredient, '이가')} 주재료인 30분 이내 초급 레시피예요.\n"
            if constraints == CONSTRAINT_EASY_30
            else f"{_apply_josa(ingredient, '이가')} 주재료인 레시피예요.\n"
        )
        actions = _recipe_actions(items)
        actions.append(
            {
                "label": f"{ingredient} 레시피 더 보기",
                "url": f"/recipes?ingredient={quote(ingredient)}",
                "data": {"ingredient": ingredient},
            }
        )
        return _payload(
            tool_name="recommend_by_ingredient",
            status="success",
            message=prefix + _numbered_list(items),
            actions=actions,
            data={"ingredient": ingredient, "total": len(items), "constraints": constraints},
        )

    # =========================================================================
    # Tool: recommend_from_fridge
    # 지역 함수: _build_recommend_config, recommend_recipe_tool,
    #            is_inventory_empty, _sort_fridge_candidates, _recipe_actions
    # 공용 함수: _payload, _numbered_list
    # =========================================================================
    @tool("recommend_from_fridge")
    def recommend_from_fridge() -> str:
        """로그인 사용자의 냉장고 재료를 최대한 활용하는 레시피를 추천합니다."""
        if not context.user_id:
            return _payload(
                tool_name="recommend_from_fridge",
                status="error",
                message=LOGIN_REQUIRED_REPLY,
            )

        from ai.agents.inventory_agent.inventory_agent import EMPTY_INVENTORY_REPLY, is_inventory_empty

        if is_inventory_empty(db=context.db, user_id=context.user_id):
            return _payload(
                tool_name="recommend_from_fridge",
                status="empty",
                message=EMPTY_INVENTORY_REPLY,
            )

        result = recommend_recipe_tool(context.db, context.user_id, context.settings_obj)
        if not result.ok:
            return _payload(
                tool_name="recommend_from_fridge",
                status="error",
                message=result.error or "냉장고 기반 추천을 불러오지 못했어요.",
            )
        ranked = _sort_fridge_candidates((result.data or {}).get("items", []))
        perfect = [item for item in ranked if item.get("missing_ingredient_count", 0) == 0]
        if perfect:
            items = perfect[:MAX_DISPLAY_RECIPES]
            prefix = "현재 냉장고 재료만으로 완벽하게 만들 수 있는 레시피예요.\n"
        else:
            items = ranked[:MAX_DISPLAY_RECIPES]
            if not items or items[0].get("owned_ingredient_count", 0) == 0:
                return _payload(
                    tool_name="recommend_from_fridge",
                    status="empty",
                    message="현재 냉장고 재료와 매칭되는 레시피를 찾지 못했어요. 재료를 더 추가해 보세요.",
                )
            prefix = "부족한 재료가 약간 있지만, 냉장고 재료를 최대한 활용할 수 있는 레시피예요.\n"
        return _payload(
            tool_name="recommend_from_fridge",
            status="success",
            message=prefix + _numbered_list(items),
            actions=_recipe_actions(items),
            data={"total": len(items)},
        )

    # =========================================================================
    # Tool: search_external
    # 지역 함수: reply_external_recipe
    # 공용 함수: _payload
    # =========================================================================
    @tool("search_external", args_schema=SearchExternalInput)
    def search_external(keyword: str, query_text: str) -> str:
        """조리 시간·온도를 찾거나 내부 DB 결과가 없을 때 웹에서 레시피를 검색합니다."""
        try:
            summary, sources = reply_external_recipe(keyword, query_text=query_text)
        except Exception as exc:
            return _payload(tool_name="search_external", status="error", message=str(exc))
        return _payload(
            tool_name="search_external",
            status="success" if summary.strip() else "empty",
            message=summary or f"{keyword} 관련 레시피를 웹에서 찾지 못했어요.",
            sources=sources,
            data={"keyword": keyword},
        )

    # =========================================================================
    # Tool: suggest_pairing
    # 지역 함수: handle_recipe_pairing, _pairing_with_llm
    # 공용 함수: _payload
    # =========================================================================
    @tool("suggest_pairing", args_schema=SuggestPairingInput)
    def suggest_pairing(text: str) -> str:
        """주요리와 함께 먹기 좋은 곁들임 메뉴를 추천합니다."""
        try:
            message, actions = handle_recipe_pairing(text)
        except Exception as exc:
            return _payload(tool_name="suggest_pairing", status="error", message=str(exc))
        return _payload(
            tool_name="suggest_pairing",
            status="success" if message.strip() else "empty",
            message=message or "어울리는 곁들임을 찾지 못했어요.",
            actions=actions,
        )

    # =========================================================================
    # Recipe Agent에 노출하는 tool 목록
    # =========================================================================
    return [
        search_recipes,
        recommend_by_ingredient,
        recommend_from_fridge,
        search_external,
        suggest_pairing,
    ]
