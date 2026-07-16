from __future__ import annotations

import re
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

from ai.agents.recipe_agent.recipe_utils import _is_relevant_search_result


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
    # ponytail: 정적 dict — LLM 기반 pairing은 Backlog
    pairings = {
        "김치볶음밥": ["계란국", "어묵국", "단무지", "오이무침", "군만두"],
        "파스타": ["마늘빵", "샐러드", "피클", "구운 채소"],
        "라면": ["김치", "단무지", "계란말이", "주먹밥"],
    }
    items = pairings.get(keyword.replace(" ", ""), ["맑은 국", "상큼한 무침", "피클류", "간단한 구이"])
    reply = f"{keyword}에는 " + ", ".join(items) + "처럼 맛을 정리해주는 메뉴가 잘 어울려요."
    return reply, []
