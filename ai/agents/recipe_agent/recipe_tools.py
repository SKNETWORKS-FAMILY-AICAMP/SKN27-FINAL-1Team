from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.backend.core.config import settings as app_settings

try:
    from tavily import TavilyClient
except ImportError:
    TavilyClient = None

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

from .recipe_config import CONSTRAINT_EASY_30, CONSTRAINT_INGREDIENT_ONLY, PAIRING_MENU
from .recipe_utils import _is_relevant_search_result, _rank_recipe_items, _recipe_actions


@dataclass
class ToolResult:
    """Tool 실행 공통 결과."""
    ok: bool
    data: Any = None
    error: str | None = None
    source: str | None = None


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


def handle_recipe_pairing(text: str) -> tuple[str, list[dict[str, Any]]]:
    """특정 음식과 함께 먹기 좋은 간단한 곁들임 메뉴를 안내합니다."""
    keyword = re.split(r"이랑|랑|와|과|하고|에", text, maxsplit=1)[0].strip()
    keyword = re.sub(r"^(남은|먹다남은)\s*", "", keyword) or "그 메뉴"
    items = PAIRING_MENU.get(keyword.replace(" ", ""), ["맑은 국", "상큼한 무침", "피클류", "간단한 구이"])
    reply = f"{keyword}에는 " + ", ".join(items) + "처럼 맛을 정리해주는 메뉴가 잘 어울려요."
    return reply, []


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
        from app.backend.services.recommendation_service.recommendation_service import recommendation_service

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
        actions = _recipe_actions(items)
        return ToolResult(ok=True, data={"actions": actions, "total": len(actions)}, source="build_actions")
    except Exception as e:
        return ToolResult(ok=False, error=str(e), source="build_actions")


def external_search_tool(keyword: str, query_text: str | None = None) -> ToolResult:
    """외부 소스(Tavily)로 레시피를 검색하고 요약한다."""
    try:
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
        ranked = _rank_recipe_items(keyword, items)
        return ToolResult(ok=True, data={"items": ranked, "total": len(ranked)}, source="rank_search")
    except Exception as e:
        return ToolResult(ok=False, error=str(e), source="rank_search")


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
