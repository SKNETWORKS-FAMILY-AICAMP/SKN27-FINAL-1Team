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
    FoodKnowledgeGraphSearchInput,
    IngredientGraphSearchInput,
    RecommendByIngredientInput,
    RecipeToolContext,
    SearchExternalInput,
    SearchRecipesInput,
    SimilarRecipeGraphSearchInput,
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


def _load_recipe_items_by_ids(db: Any, recipe_ids: list[int]) -> list[dict[str, Any]]:
    """GraphDB 순위를 유지하면서 PostgreSQL 표시 데이터를 조회한다."""
    if not recipe_ids:
        return []
    from app.backend.db.models import Recipe
    from app.backend.services.recommendation_service.recipe_query import recipe_to_list_item

    recipes = db.query(Recipe).filter(Recipe.id.in_(recipe_ids)).all()
    by_id = {int(recipe.id): recipe for recipe in recipes}
    return [recipe_to_list_item(by_id[recipe_id]) for recipe_id in recipe_ids if recipe_id in by_id]


def search_recipe_graph(query_name: str, parameters: dict[str, Any]) -> ToolResult:
    """화이트리스트 Cypher를 실행하고 숫자형 recipe_id를 반환한다."""
    try:
        from app.backend.db.neo4j_session import graph_session
        from app.backend.services.recommendation_service.recipe_graph_queries import run_recipe_graph_query

        with graph_session() as session:
            recipe_ids = run_recipe_graph_query(session, query_name, parameters)
        return ToolResult(ok=True, data={"recipe_ids": recipe_ids}, source="neo4j")
    except Exception:
        logger.exception("레시피 GraphDB 검색에 실패했습니다: %s", query_name)
        return ToolResult(ok=False, error="비슷한 레시피를 찾지 못했어요. 잠시 후 다시 시도해주세요.", source="neo4j")


def build_recipe_tools(context: RecipeToolContext) -> list[BaseTool]:
    """실행 의존성을 감춘 LangChain recipe tools를 생성한다."""

    # 같은 Agent 실행에서 확보한 내부 결과 수를 Tool들이 공유한다.
    # 충분한 내부 결과가 있으면 불필요한 외부 검색을 실행하지 않는다.
    internal_result_count = 0

    def graph_payload(tool_name: str, result: ToolResult, message: str) -> str:
        nonlocal internal_result_count
        if not result.ok:
            return build_tool_payload_json(tool_name=tool_name, status="error", message=result.error or message)
        recipe_ids = list((result.data or {}).get("recipe_ids") or [])
        items = exclude_previously_shown_recipes(
            _load_recipe_items_by_ids(context.db, recipe_ids), context.history
        )[:MAX_DISPLAY_RECIPES]
        if not items:
            return build_tool_payload_json(
                tool_name=tool_name,
                status="empty",
                message="조건에 맞는 레시피를 찾지 못했어요.",
                data={"recipe_ids": recipe_ids},
            )
        selected_ids = [int(item["recipe_id"]) for item in items]
        internal_result_count = max(internal_result_count, len(items))
        return build_tool_payload_json(
            tool_name=tool_name,
            status="success",
            metadata_policy="actions",
            message=message,
            actions=build_recipe_actions(items),
            data={"recipe_ids": selected_ids, "items": items, "total": len(items)},
        )

    @tool("search_recipes_by_ingredients", args_schema=IngredientGraphSearchInput)
    def search_recipes_by_ingredients(ingredient_names: list[str], limit: int = 10) -> str:
        """여러 보유 식재료의 별칭과 필요 재료 관계를 따라 충족률이 높은 레시피를 찾습니다."""
        names = list(dict.fromkeys(name.strip() for name in ingredient_names if name.strip()))
        if not names:
            return build_tool_payload_json(
                tool_name="search_recipes_by_ingredients", status="empty", message="식재료명을 확인하지 못했어요."
            )
        result = search_recipe_graph("ingredient_coverage", {"ingredientNames": names, "limit": limit})
        return graph_payload("search_recipes_by_ingredients", result, "보유 재료 활용도가 높은 레시피를 찾았어요.")

    @tool("search_recipes_by_food_knowledge", args_schema=FoodKnowledgeGraphSearchInput)
    def search_recipes_by_food_knowledge(
        search_type: str,
        month: int | None = None,
        guide_type: str | None = None,
        keyword: str | None = None,
        category_names: list[str] | None = None,
        minimum_category_count: int = 1,
        minimum_covered_ingredients: int = 3,
        limit: int = 10,
    ) -> str:
        """제철·식재료 가이드·식품 분류·영양 연결을 이용해 레시피를 찾습니다."""
        if search_type == "seasonal":
            query_name, parameters = "seasonal", {"month": month, "limit": limit}
        elif search_type == "guide":
            query_name, parameters = "guide", {"guideType": guide_type, "keyword": keyword, "limit": limit}
        elif search_type == "taxonomy":
            query_name, parameters = "taxonomy", {
                "categoryNames": category_names,
                "minimumCategoryCount": minimum_category_count,
                "limit": limit,
            }
        else:
            query_name, parameters = "nutrition", {
                "minimumCoveredIngredients": minimum_covered_ingredients,
                "limit": limit,
            }
        result = search_recipe_graph(query_name, parameters)
        return graph_payload("search_recipes_by_food_knowledge", result, "식재료 지식 조건에 맞는 레시피를 찾았어요.")

    @tool("find_similar_recipes", args_schema=SimilarRecipeGraphSearchInput)
    def find_similar_recipes(
        recipe_id: int,
        method: str = "ingredient_jaccard",
        limit: int = 10,
    ) -> str:
        """기준 레시피와 재료 구성이 비슷하거나 그래프 구조가 가까운 레시피를 찾습니다."""
        parameters = {"recipeId": recipe_id, "limit": limit}
        if method == "graph_embedding":
            parameters["candidateCount"] = min(175, max(limit + 1, limit * 3))
        result = search_recipe_graph(method, parameters)
        return graph_payload("find_similar_recipes", result, "기준 레시피와 유사한 레시피를 찾았어요.")

    # =========================================================================
    # Tool: search_recipes
    # 내부 DB 검색 결과를 공통 payload와 화면 액션으로 변환한다.
    # =========================================================================
    @tool("search_recipes", args_schema=SearchRecipesInput)
    def search_recipes(keyword: str) -> str:
        """요리명이나 키워드로 서비스에 있는 레시피를 검색합니다."""
        nonlocal internal_result_count

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
                message=f"{keyword} 관련 레시피를 찾지 못했어요.",
                data={"keyword": keyword},
            )
        internal_result_count = max(internal_result_count, len(items))
        return build_tool_payload_json(
            tool_name="search_recipes",
            status="success",
            metadata_policy="actions",
            message="관련 레시피를 찾았어요.",
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
        nonlocal internal_result_count

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
                message=f"{ingredient} 관련 레시피를 찾지 못했어요.",
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
        internal_result_count = max(internal_result_count, len(items))
        return build_tool_payload_json(
            tool_name="recommend_by_ingredient",
            status="success",
            metadata_policy="actions",
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
        nonlocal internal_result_count

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
                    message="보유 재료와 겹치는 추천을 못 찾았어요. 재료명으로 검색해볼까요?",
                )
            match_type = "partial"
        internal_result_count = max(internal_result_count, len(items))
        return build_tool_payload_json(
            tool_name="recommend_from_fridge",
            status="success",
            metadata_policy="actions",
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
        """조리 시간·온도를 찾거나 서비스 레시피가 없을 때 웹에서 레시피를 검색합니다."""
        if internal_result_count >= MAX_DISPLAY_RECIPES:
            return build_tool_payload_json(
                tool_name="search_external",
                status="empty",
                message="이미 충분한 레시피를 찾아 웹 검색을 생략했어요.",
            )

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
            metadata_policy="sources" if results else "none",
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
        search_recipes_by_ingredients,
        search_recipes_by_food_knowledge,
        find_similar_recipes,
        search_external,
    ]
