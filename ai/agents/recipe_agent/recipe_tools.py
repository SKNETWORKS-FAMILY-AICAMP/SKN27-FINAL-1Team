from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from app.backend.core.config import settings as app_settings
from langchain_core.tools import BaseTool, tool

try:
    from tavily import TavilyClient
except ImportError:
    TavilyClient = None

from .recipe_config import (
    CONSTRAINT_EASY_30,
    CONSTRAINT_INGREDIENT_ONLY,
    LOGIN_REQUIRED_REPLY,
    MAX_DISPLAY_RECIPES,
)
from .recipe_state import (
    RecommendByIngredientInput,
    RecipeToolContext,
    SearchExternalInput,
    SearchRecipesInput,
)
from .recipe_utils import (
    build_recipe_actions,
    build_tool_payload_json,
    exclude_previously_shown_recipes,
    is_relevant_external_result,
    rank_recipe_search_results,
    sort_fridge_recommendations,
)

logger = logging.getLogger(__name__)


@dataclass
class ToolResult:
    """Tool 실행 공통 결과."""

    ok: bool
    data: Any = None
    error: str | None = None
    source: str | None = None


def search_external_recipes(keyword: str, query_text: str | None = None) -> ToolResult:
    """필터링된 Tavily 결과를 main Agent가 요약할 수 있도록 반환한다."""
    if not app_settings.TAVILY_API_KEY or TavilyClient is None:
        return ToolResult(ok=False, error="웹 검색은 Tavily 설정 후 사용할 수 있어요.", source="tavily")

    client = TavilyClient(api_key=app_settings.TAVILY_API_KEY)
    try:
        result = client.search(query=query_text or f"{keyword} 레시피", search_depth="basic", max_results=3)
    except Exception:
        logger.exception("Tavily 레시피 검색에 실패했습니다.")
        return ToolResult(ok=False, error="웹 검색 연결이 불안정해요. 잠시 후 다시 시도해주세요.", source="tavily")

    results = [
        {
            "title": item.get("title") or "",
            "url": item.get("url") or "",
            "content": (item.get("content") or "")[:600],
        }
        for item in result.get("results", [])
        if is_relevant_external_result(keyword, item)
    ][:3]
    sources = [
        {"title": item.get("title") or item.get("url", "출처"), "url": item.get("url", "")}
        for item in results
        if item.get("url")
    ]
    return ToolResult(
        ok=True,
        data={"keyword": keyword, "query_text": query_text or keyword, "results": results, "sources": sources},
        source="tavily",
    )


def search_internal_recipes(db: Any, keyword: str) -> ToolResult:
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
    except Exception:
        logger.exception("내부 레시피 검색에 실패했습니다.")
        return ToolResult(ok=False, error="레시피 검색에 실패했어요. 잠시 후 다시 시도해주세요.", source="recipe_search")


def recommend_fridge_recipes(db: Any, user_id: int) -> ToolResult:
    """냉장고 소비 정책으로 추천 서비스를 호출한다.

    알레르기·기피 재료 제외와 유통기한 우선순위는 추천 서비스의 고정 정책이며,
    챗봇 도구 입력으로 변경하지 않는다.
    """
    try:
        from app.backend.services.recommendation_service.recommend_config import RecipeRecommendConfig
        from app.backend.services.recommendation_service.recommendation_service import recommendation_service

        config = RecipeRecommendConfig.fridge_consume_preset()
        result = recommendation_service.recommend_recipes(db, user_id, config)
        items = result.get("items", [])
        return ToolResult(ok=True, data={"items": items, "total": len(items)}, source="recommendation")
    except Exception:
        logger.exception("냉장고 기반 레시피 추천에 실패했습니다.")
        return ToolResult(ok=False, error="냉장고 기반 추천을 불러오지 못했어요. 잠시 후 다시 시도해주세요.", source="recommendation")


def search_recipes_by_ingredient_with_fallback(db: Any, ingredient: str) -> ToolResult:
    """쉬운 메뉴를 우선 찾고, 결과가 없을 때만 주재료 조건으로 완화한다."""
    try:
        from app.backend.services.recommendation_service.recipe_search_service import recipe_search_service

        result = recipe_search_service.search_recipes(
            db=db, ingredient=ingredient, difficulty="초급", cooking_time_label="30분이내",
            main_ingredient_only=True, page=1, page_size=10,
        )
        items = rank_recipe_search_results(ingredient, result["items"])
        constraints = dict(CONSTRAINT_EASY_30)
        if not items:
            result = recipe_search_service.search_recipes(
                db=db, ingredient=ingredient, main_ingredient_only=True, page=1, page_size=10,
            )
            items = rank_recipe_search_results(ingredient, result["items"])
            constraints = dict(CONSTRAINT_INGREDIENT_ONLY)
        return ToolResult(
            ok=True,
            data={"items": items, "total": len(items), "constraints": constraints},
            source="ingredient_relax",
        )
    except Exception:
        logger.exception("재료 기반 레시피 검색에 실패했습니다.")
        return ToolResult(ok=False, error="재료 기반 추천에 실패했어요. 잠시 후 다시 시도해주세요.", source="ingredient_relax")


def build_recipe_tools(context: RecipeToolContext) -> list[BaseTool]:
    """실행 의존성을 감춘 LangChain recipe tools를 생성한다."""

    # =========================================================================
    # Tool: search_recipes
    # 내부 DB 검색 결과를 공통 payload와 화면 액션으로 변환한다.
    # =========================================================================
    @tool("search_recipes", args_schema=SearchRecipesInput)
    def search_recipes(keyword: str) -> str:
        """요리명이나 키워드로 내부 DB의 레시피를 검색합니다."""
        keyword = keyword.strip()
        if not keyword:
            return build_tool_payload_json(
                tool_name="search_recipes",
                status="empty",
                message="검색할 요리명이나 키워드를 확인하지 못했어요.",
            )
        result = search_internal_recipes(context.db, keyword)
        if not result.ok:
            return build_tool_payload_json(
                tool_name="search_recipes",
                status="error",
                message=result.error or "레시피 검색에 실패했어요.",
            )
        items = rank_recipe_search_results(keyword, (result.data or {}).get("items", []))[:MAX_DISPLAY_RECIPES]
        if not items:
            return build_tool_payload_json(
                tool_name="search_recipes",
                status="empty",
                message=f"{keyword} 관련 레시피를 내부 DB에서 찾지 못했어요.",
                data={"keyword": keyword},
            )
        return build_tool_payload_json(
            tool_name="search_recipes",
            status="success",
            message="내부 DB에서 레시피를 찾았어요.",
            actions=build_recipe_actions(items),
            data={"keyword": keyword, "items": items, "total": len(items)},
        )

    # =========================================================================
    # Tool: recommend_by_ingredient
    # 조건 완화 검색 후 이전 추천을 제외하고 화면 액션을 구성한다.
    # =========================================================================
    @tool("recommend_by_ingredient", args_schema=RecommendByIngredientInput)
    def recommend_by_ingredient(ingredient: str) -> str:
        """특정 주재료로 만들 수 있는 쉬운 레시피를 추천합니다."""
        ingredient = ingredient.strip()
        if not ingredient:
            return build_tool_payload_json(
                tool_name="recommend_by_ingredient",
                status="empty",
                message="추천할 재료명을 확인하지 못했어요.",
            )
        result = search_recipes_by_ingredient_with_fallback(context.db, ingredient)
        if not result.ok:
            return build_tool_payload_json(
                tool_name="recommend_by_ingredient",
                status="error",
                message=result.error or "재료 기반 추천에 실패했어요.",
            )
        data = result.data or {}
        items = exclude_previously_shown_recipes(data.get("items") or [], context.history)[:MAX_DISPLAY_RECIPES]
        if not items:
            return build_tool_payload_json(
                tool_name="recommend_by_ingredient",
                status="empty",
                message=f"{ingredient} 관련 레시피를 내부 DB에서 찾지 못했어요.",
                data={"ingredient": ingredient},
            )
        constraints = data.get("constraints") or {}
        actions = build_recipe_actions(items)
        actions.append(
            {
                "label": f"{ingredient} 레시피 더 보기",
                "url": f"/recipes?ingredient={quote(ingredient)}",
                "data": {"ingredient": ingredient},
            }
        )
        return build_tool_payload_json(
            tool_name="recommend_by_ingredient",
            status="success",
            message="재료 기반 레시피를 찾았어요.",
            actions=actions,
            data={"ingredient": ingredient, "items": items, "total": len(items), "constraints": constraints},
        )

    # =========================================================================
    # Tool: recommend_from_fridge
    # 냉장고 상태를 확인하고 재료 활용도가 높은 추천을 화면 액션으로 구성한다.
    # =========================================================================
    @tool("recommend_from_fridge")
    def recommend_from_fridge() -> str:
        """로그인 사용자의 냉장고 재료를 최대한 활용하는 레시피를 추천합니다."""
        if not context.user_id:
            return build_tool_payload_json(
                tool_name="recommend_from_fridge",
                status="error",
                message=LOGIN_REQUIRED_REPLY,
            )

        from ai.agents.inventory_agent.inventory_agent import EMPTY_INVENTORY_REPLY, is_inventory_empty

        if is_inventory_empty(db=context.db, user_id=context.user_id):
            return build_tool_payload_json(
                tool_name="recommend_from_fridge",
                status="empty",
                message=EMPTY_INVENTORY_REPLY,
            )

        result = recommend_fridge_recipes(context.db, context.user_id)
        if not result.ok:
            return build_tool_payload_json(
                tool_name="recommend_from_fridge",
                status="error",
                message=result.error or "냉장고 기반 추천을 불러오지 못했어요.",
            )
        ranked = sort_fridge_recommendations((result.data or {}).get("items", []))
        perfect = [item for item in ranked if item.get("missing_ingredient_count", 0) == 0]
        if perfect:
            items = perfect[:MAX_DISPLAY_RECIPES]
            match_type = "perfect"
        else:
            items = ranked[:MAX_DISPLAY_RECIPES]
            if not items or items[0].get("owned_ingredient_count", 0) == 0:
                return build_tool_payload_json(
                    tool_name="recommend_from_fridge",
                    status="empty",
                    message="현재 냉장고 재료와 매칭되는 레시피를 찾지 못했어요. 재료를 더 추가해 보세요.",
                )
            match_type = "partial"
        return build_tool_payload_json(
            tool_name="recommend_from_fridge",
            status="success",
            message="냉장고 재료 기반 레시피를 찾았어요.",
            actions=build_recipe_actions(items),
            data={"items": items, "total": len(items), "match_type": match_type},
        )

    # =========================================================================
    # Tool: search_external
    # 외부 검색 결과와 출처를 공통 payload로 변환한다.
    # =========================================================================
    @tool("search_external", args_schema=SearchExternalInput)
    def search_external(keyword: str, query_text: str) -> str:
        """조리 시간·온도를 찾거나 내부 DB 결과가 없을 때 웹에서 레시피를 검색합니다."""
        result = search_external_recipes(keyword, query_text=query_text)
        if not result.ok:
            return build_tool_payload_json(
                tool_name="search_external",
                status="error",
                message=result.error or "웹 검색에 실패했어요.",
            )
        data = result.data or {}
        results = data.get("results") or []
        return build_tool_payload_json(
            tool_name="search_external",
            status="success" if results else "empty",
            message="웹 검색 결과를 찾았어요." if results else f"{keyword} 관련 레시피를 웹에서 찾지 못했어요.",
            sources=data.get("sources") or [],
            data=data,
        )

    # =========================================================================
    # Recipe Agent에 노출하는 tool 목록
    # =========================================================================
    return [
        search_recipes,
        recommend_by_ingredient,
        recommend_from_fridge,
        search_external,
    ]
