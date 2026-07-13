from __future__ import annotations

from typing import Any
from urllib.parse import quote

from sqlalchemy.orm import Session

from app.backend.core.config import settings as app_settings
from app.backend.services.recommendation_service.recipe_search_service import recipe_search_service
from app.backend.services.recommendation_service.recommend_config import RecipeRecommendConfig
from app.backend.services.recommendation_service.recommendation_service import recommendation_service

try:
    from tavily import TavilyClient
except ImportError:
    TavilyClient = None

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

from ai.agents.inventory_agent.inventory_agent import EMPTY_INVENTORY_REPLY, is_inventory_empty
from ai.agents.recipe_agent.recipe_utils import (
    _apply_josa,
    _extract_keyword,
    _extract_recipe_ingredient,
    _is_cooking_time_question,
    _is_relevant_search_result,
    _rank_recipe_items,
    _recipe_actions,
)


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


def handle_recipe_search(db: Session, text: str) -> tuple[str, list[dict[str, Any]], list[dict[str, str]]]:
    """레시피명 또는 재료명 검색 결과를 안내합니다."""
    keyword = _extract_recipe_ingredient(text) or _extract_keyword(text)
    if _is_cooking_time_question(text):
        reply, sources = reply_external_recipe(keyword, text)
        return reply, [], sources

    try:
        result = recipe_search_service.search_recipes(
            db=db, ingredient=keyword, main_ingredient_only=True, page=1, page_size=10,
        )
        items: list[dict[str, Any]] = result["items"]
        if not items:
            result = recipe_search_service.search_recipes(db=db, query=keyword, page=1, page_size=10)
            items = result["items"]
    except Exception:
        reply, sources = reply_external_recipe(keyword)
        return reply, [], sources

    if not items:
        reply, sources = reply_external_recipe(keyword)
        return reply, [], sources

    items = _rank_recipe_items(keyword, items)
    titles = [item["title"] for item in items[:3]]
    reply = f"{keyword} 관련 레시피예요.\n" + "\n".join(f"{index + 1}. {title}" for index, title in enumerate(titles))
    return reply, _recipe_actions(items), []


def handle_recipe_recommend(
    db: Session,
    user_id: int,
    text: str,
    history: list | None = None,
    settings_obj: Any = None,
) -> tuple[str, list[dict[str, Any]]]:
    """냉장고 재료 기반 또는 특정 재료 기반 레시피 추천 결과를 안내합니다."""
    keyword = _extract_recipe_ingredient(text)
    history = history or []

    if not keyword and history:
        try:
            from langchain_openai import ChatOpenAI
            from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

            llm = ChatOpenAI(model=app_settings.OPENAI_MODEL, api_key=app_settings.OPENAI_API_KEY, temperature=0.0)
            messages = [
                SystemMessage(
                    content=(
                        "사용자 대화 맥락을 보고, 요리 추천을 위해 검색할 '핵심 식재료' 또는 "
                        "'요리 상황/컨셉(예: 비올때, 매운거, 다이어트 등)' 키워드 1개만 단답형으로 출력해. "
                        "사용자가 '그거 말고 딴거'처럼 지시대명사를 쓰면 이전 맥락의 키워드를 찾아서 반환해. "
                        "절대 부연설명 없이 단어 1개만 출력해. 도저히 찾을 수 없으면 'None' 반환."
                    )
                )
            ]
            for msg in history[-4:]:
                messages.append(HumanMessage(content=msg.text) if msg.role == "user" else AIMessage(content=msg.text))
            messages.append(HumanMessage(content=text))
            res = llm.invoke(messages).content.strip()
            if res != "None" and res not in ("다른거", "딴거", "그거", "저거", "이거", "다른 거", "딴 거", "내", "나", "제"):
                keyword = res
        except Exception:
            pass

    if keyword:
        past_bot_texts = " ".join([msg.text for msg in history if msg.role == "bot"])
        try:
            result = recipe_search_service.search_recipes(
                db=db,
                ingredient=keyword,
                difficulty="초급",
                cooking_time_label="30분이내",
                main_ingredient_only=True,
                page=1,
                page_size=10,
            )
            raw_items: list[dict[str, Any]] = _rank_recipe_items(keyword, result["items"])
            is_easy_result = bool(raw_items)
            if not raw_items:
                result = recipe_search_service.search_recipes(
                    db=db, ingredient=keyword, main_ingredient_only=True, page=1, page_size=10,
                )
                raw_items = _rank_recipe_items(keyword, result["items"])

            new_items = [item for item in raw_items if item["title"] not in past_bot_texts]
            if not new_items:
                new_items = raw_items
            items = new_items[:3]
        except Exception:
            reply, _sources = reply_external_recipe(keyword)
            return reply, []

        list_action = {
            "label": f"{keyword} 레시피 더 보기",
            "url": f"/recipes?ingredient={quote(keyword)}",
            "data": {"ingredient": keyword},
        }
        if not items:
            reply, _sources = reply_external_recipe(keyword)
            return reply, []

        titles = [item["title"] for item in items]
        actions = _recipe_actions(items) + [list_action]
        prefix = (
            f"{_apply_josa(keyword, '이가')} 주재료인 30분 이내 초급 레시피는 "
            if is_easy_result
            else f"{_apply_josa(keyword, '이가')} 주재료인 레시피는 "
        )
        return prefix + "\n" + "\n".join(f"{index + 1}. {title}" for index, title in enumerate(titles)), actions

    if is_inventory_empty(db=db, user_id=user_id):
        return EMPTY_INVENTORY_REPLY, []

    try:
        config = RecipeRecommendConfig.fridge_consume_preset()
        if settings_obj:
            if not getattr(settings_obj, "expiringFirst", True):
                config.mode = "fridge_all"
            if not getattr(settings_obj, "excludeDislikes", True):
                config.exclude_dislikes = False

        result = recommendation_service.recommend_recipes(db, user_id, config)
    except Exception:
        return "냉장고 기반 추천을 불러오지 못했어요. 재료명을 넣어서 다시 물어봐주세요.", []

    raw_items = result.get("items", [])
    sorted_items = sorted(
        raw_items,
        key=lambda x: (
            -x.get("owned_ingredient_count", 0),
            x.get("missing_ingredient_count", 0),
            -x.get("final_score", 0),
        ),
    )

    items_perfect = [item for item in sorted_items if item.get("missing_ingredient_count", 0) == 0]
    if items_perfect:
        items = items_perfect[:3]
        prefix = "현재 냉장고 재료만으로 완벽하게 만들 수 있는 레시피예요.\n"
    else:
        items = sorted_items[:3]
        if not items or items[0].get("owned_ingredient_count", 0) == 0:
            return "현재 냉장고 재료와 매칭되는 레시피를 찾지 못했어요. 재료를 더 추가해 보세요.", []
        prefix = "부족한 재료가 약간 있지만, 냉장고 재료를 최대한 활용할 수 있는 레시피예요.\n"

    titles = [item["title"] for item in items]
    return prefix + "\n".join(f"{index + 1}. {title}" for index, title in enumerate(titles)), _recipe_actions(items)


if __name__ == "__main__":
    import ai.agents.recipe_agent.recipe_handlers as handlers

    original_external = handlers.reply_external_recipe
    original_search = recipe_search_service.search_recipes
    original_empty = handlers.is_inventory_empty

    called: dict[str, Any] = {"external": False, "query": ""}

    def fake_external(keyword: str, query_text: str | None = None) -> tuple[str, list[dict[str, str]]]:
        called["external"] = True
        called["query"] = query_text or ""
        return f"{keyword} 웹 검색", []

    handlers.reply_external_recipe = fake_external
    try:
        reply, actions, sources = handlers.handle_recipe_search(None, "감자튀김 에어프라이기 시간")
        assert called["external"]
        assert called["query"] == "감자튀김 에어프라이기 시간"
        assert reply == "감자튀김 웹 검색"
        assert actions == []
        assert sources == []
    finally:
        handlers.reply_external_recipe = original_external

    def fake_search_recipes(**kwargs: Any) -> dict[str, Any]:
        return {
            "items": [
                {"recipe_id": 1, "title": "김치볶음밥", "difficulty": "초급", "cooking_time_min": 15},
            ]
        }

    recipe_search_service.search_recipes = fake_search_recipes
    handlers.reply_external_recipe = original_external
    try:
        reply, actions, sources = handlers.handle_recipe_search(None, "김치볶음밥 레시피")
        assert "김치볶음밥" in reply
        assert actions[0]["url"] == "/recipes/1"
        assert sources == []
    finally:
        recipe_search_service.search_recipes = original_search

    recipe_search_service.search_recipes = fake_search_recipes
    try:
        reply, actions = handlers.handle_recipe_recommend(None, 1, "두부로 뭐 해먹지?", history=[])
        assert "김치볶음밥" in reply
        assert len(actions) >= 1
    finally:
        recipe_search_service.search_recipes = original_search

    handlers.is_inventory_empty = lambda **kwargs: True
    try:
        reply, actions = handlers.handle_recipe_recommend(None, 1, "오늘 뭐 해먹지?", history=[])
        assert reply == EMPTY_INVENTORY_REPLY
        assert actions == []
    finally:
        handlers.is_inventory_empty = original_empty

    print("recipe_handlers ok")
