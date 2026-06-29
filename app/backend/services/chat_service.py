import re
from typing import Any
from urllib.parse import quote

from sqlalchemy.orm import Session

from app.backend.core.config import settings
from app.backend.services.guide_service.guide_service import guide_service
from app.backend.services.inventory_service.inventory_service import inventory_service
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


class ChatService:
    """사용자 자연어 메시지를 intent로 분류하고 기존 서비스를 호출합니다."""

    def handle_message(self, db: Session, user_id: int, message: str) -> dict[str, Any]:
        """메시지를 처리하고 챗봇 응답 딕셔너리를 반환합니다."""
        text = message.strip()
        intent = self._route_intent(text)
        actions: list[dict[str, Any]] = []
        sources: list[dict[str, str]] = []

        try:
            if intent == "inventory.list":
                reply = self._reply_inventory_list(db, user_id)
            elif intent == "inventory.expiring":
                reply = self._reply_expiring_items(db, user_id, text)
            elif intent == "ingredient.guide":
                reply, sources = self._reply_guide(text)
            elif intent == "recipe.recommend":
                reply, actions = self._reply_recipe_recommend(db, user_id, text)
            elif intent == "recipe.search":
                reply, actions, sources = self._reply_recipe_search(db, text)
            elif intent == "receipt.guide":
                reply = "영수증은 파일 업로드가 필요해서 상단 메뉴의 영수증 OCR 화면에서 등록해주세요."
            else:
                reply = "냉장고 재료 조회, 소비기한 임박 재료, 보관법, 레시피 추천을 물어볼 수 있어요."
        except Exception:
            reply = "요청을 처리하는 중 문제가 생겼어요. 잠시 후 다시 시도해주세요."
            actions = []
            sources = []

        return {"intent": intent, "reply": reply, "actions": actions, "sources": sources}

    def _route_intent(self, text: str) -> str:
        """키워드 기반으로 1차 챗봇 intent를 분류합니다."""
        normalized = text.replace(" ", "").lower()

        if any(word in normalized for word in ("영수증", "ocr", "구매내역")):
            return "receipt.guide"
        if any(word in normalized for word in ("보관법", "보관방법", "보관", "손질", "신선", "가이드", "어떡", "어떻게하지", "먹다남은", "남은")):
            return "ingredient.guide"
        if any(word in normalized for word in ("상하는", "임박", "소비기한", "유통기한", "기한", "먼저먹", "먹어야", "다되어", "다돼", "끝나", "d-day", "디데이")):
            return "inventory.expiring"
        if any(word in normalized for word in ("뭐있", "뭐가있", "냉장고목록", "재료목록", "내재료")):
            return "inventory.list"
        if any(word in normalized for word in ("추천", "뭐해먹", "뭐먹", "뭐하지", "뭘", "만들지", "만들수", "만들수있는", "만들수있", "할수", "할수있는", "메뉴", "냉장고파먹")):
            return "recipe.recommend"
        if "레시피" in normalized or "요리" in normalized:
            return "recipe.search"
        return "general"

    def _extract_keyword(self, text: str) -> str:
        """조사와 기능 키워드를 덜어내고 검색에 쓸 핵심 단어를 추립니다."""
        cleaned = re.sub(
            r"(먹다\s*남은|먹다남은|남은|먹다|어떡하지|어떡해|어떻게하지|보관법|보관방법|보관해|보관|어떻게|손질법|가이드|레시피|요리|추천|알려줘|찾아줘|해줘|은|는|이|가|을|를|으로|로|에|의|좀|해먹을|만들)",
            " ",
            text,
        )
        words = [word.strip() for word in cleaned.split() if word.strip()]
        return words[0] if words else text.strip()

    def _extract_recipe_ingredient(self, text: str) -> str:
        """'두부로 뭐 만들 수 있어?' 같은 문장에서 재료명을 추출합니다."""
        match = re.search(r"([가-힣A-Za-z0-9]+)(?:으로|로).*(?:뭐|뭘|무엇|메뉴|레시피|요리|만들|추천)", text)
        if not match:
            match = re.search(r"(?:남은\s*)?([가-힣A-Za-z0-9]+)\s*(?:빨리|먼저|써야|처리).*(?:뭐|뭘|무엇|메뉴|레시피|요리|추천|하지)", text)
        if not match:
            return ""

        keyword = match.group(1).strip()
        if keyword in ("걸", "있는", "이걸", "이것", "그걸", "그것", "재료", "냉장고"):
            return ""
        return self._normalize_recipe_keyword(keyword)

    def _normalize_recipe_keyword(self, keyword: str) -> str:
        """짧은 구어체 재료명을 레시피 검색에 더 잘 맞는 대표명으로 바꿉니다."""
        aliases = {"파": "대파"}
        return aliases.get(keyword, keyword)

    def _recipe_actions(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """레시피 응답을 상세 이동 버튼 액션으로 변환합니다."""
        actions: list[dict[str, Any]] = []
        for item in items[:3]:
            recipe_id = item.get("recipe_id")
            title = item.get("title")
            if not recipe_id or not title:
                continue
            actions.append({"label": title, "url": f"/recipes/{recipe_id}", "data": {"recipe_id": recipe_id, "title": title}})
        return actions

    def _reply_inventory_list(self, db: Session, user_id: int) -> str:
        """냉장고 보유 재료를 짧게 요약합니다."""
        items = inventory_service.get_ingredients(db=db, user_id=user_id)
        if not items:
            return "현재 냉장고에 등록된 재료가 없어요."

        names = [item["name"] for item in items[:8]]
        suffix = "" if len(items) <= 8 else f" 외 {len(items) - 8}개"
        return f"현재 냉장고에는 {', '.join(names)}{suffix}가 있어요."

    def _extract_expiry_keyword(self, text: str) -> str:
        """특정 재료의 소비기한 질문이면 재료명을 추출합니다."""
        match = re.search(r"([가-힣A-Za-z0-9]+)\s*(?:유통기한|소비기한|기한)", text)
        if not match:
            return ""
        keyword = match.group(1).strip()
        if keyword in ("재료", "냉장고", "오늘"):
            return ""
        return keyword

    def _reply_expiring_items(self, db: Session, user_id: int, text: str = "") -> str:
        """소비기한이 가까운 재료 또는 특정 재료의 D-day를 안내합니다."""
        items = inventory_service.get_ingredients(db=db, user_id=user_id)
        keyword = self._extract_expiry_keyword(text)
        if keyword:
            matched = [item for item in items if keyword in item.get("name", "")]
            if not matched:
                return f"냉장고에 등록된 {keyword} 재료를 찾지 못했어요."
            summary = [f"{item['name']} {self._format_d_day(item['d_day'])}" for item in matched if item.get("d_day") is not None]
            return f"{keyword} 소비기한은 " + ", ".join(summary) + "예요."

        expiring = sorted(
            [item for item in items if item.get("d_day") is not None and item["d_day"] <= 3],
            key=lambda item: item["d_day"],
        )
        if not expiring:
            return "D-3 이내로 임박한 재료는 없어요."

        summary = [f"{item['name']} {self._format_d_day(item['d_day'])}" for item in expiring[:5]]
        return "소비기한이 가까운 재료는 " + ", ".join(summary) + "예요."

    def _format_d_day(self, d_day: int) -> str:
        """프론트와 같은 기준으로 D-day 문구를 표시합니다."""
        if d_day > 0:
            return f"D-{d_day}"
        if d_day == 0:
            return "D-Day"
        return f"D+{abs(d_day)} 지남"

    def _reply_guide(self, text: str) -> tuple[str, list[dict[str, str]]]:
        """식재료 가이드 검색 결과를 이용해 보관 정보를 안내합니다."""
        keyword = self._extract_keyword(text)
        try:
            guides = guide_service.search_guides(keyword=keyword, page=1, page_size=1)
            if not guides["items"]:
                return self._reply_external_guide(keyword)

            item = guides["items"][0]
            detail = guide_service.get_guide_detail(item["code"]) or {}
            tip = detail.get("storage_tips") or detail.get("horticultural_storage_tips")
        except Exception:
            return self._reply_external_guide(keyword)

        if not tip:
            return f"{item['name']} 가이드는 찾았지만 보관법 정보가 비어 있어요.", []
        return f"{item['name']} 보관법이에요.\n{self._format_guide_tip(tip)}", []

    def _is_relevant_search_result(self, keyword: str, item: dict[str, Any]) -> bool:
        """검색 결과가 질문 핵심어를 실제로 포함하는지 확인합니다."""
        stopwords = {"먹다남은", "남은", "보관", "보관법", "알려줘", "식재료", "레시피"}
        tokens = [
            token
            for token in re.findall(r"[가-힣A-Za-z0-9]+", keyword.lower())
            if len(token) > 1 and token not in stopwords
        ]
        haystack = f"{item.get('title', '')} {item.get('content', '')} {item.get('url', '')}".lower()
        return not tokens or any(token in haystack for token in tokens)

    def _reply_external_guide(self, keyword: str) -> tuple[str, list[dict[str, str]]]:
        """내부 가이드가 없을 때 Tavily 검색 결과를 짧게 요약합니다."""
        if not settings.TAVILY_API_KEY or TavilyClient is None:
            return f"{keyword} 정보는 아직 우리 가이드에 없어요. 웹 검색 답변은 Tavily 설정 후 사용할 수 있어요.", []

        client = TavilyClient(api_key=settings.TAVILY_API_KEY)
        try:
            result = client.search(query=f"{keyword} 보관법", search_depth="basic", max_results=5)
        except Exception:
            return f"{keyword} 정보는 웹 검색을 시도했지만 지금은 연결이 불안정해요. 잠시 후 다시 시도해주세요.", []
        results = [item for item in result.get("results", []) if self._is_relevant_search_result(keyword, item)][:3]
        sources = [
            {"title": item.get("title") or item.get("url", "출처"), "url": item.get("url", "")}
            for item in results
            if item.get("url")
        ]
        content = "\n".join(item.get("content", "") for item in results if item.get("content"))[:1200]
        if not content:
            return f"{keyword} 정보를 웹에서 찾지 못했어요.", sources

        if settings.OPENAI_API_KEY and OpenAI is not None:
            client_ai = OpenAI(api_key=settings.OPENAI_API_KEY)
            response = client_ai.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "검색 결과 안에서만 한국어로 3문장 이하로 식재료 보관법을 요약해."},
                    {"role": "user", "content": content},
                ],
                temperature=0.2,
            )
            summary = response.choices[0].message.content.strip()
        else:
            summary = content.split(".")[0].strip() + "."

        return f"우리 가이드에는 아직 없어서 웹 검색 기준으로 안내할게요.\n\n{summary}", sources

    def _format_guide_tip(self, tip: str) -> str:
        """긴 보관법 문장을 챗봇에서 읽기 쉬운 줄 단위로 나눕니다."""
        sentences = [sentence.strip() for sentence in re.split(r"(?<=\.)\s+", tip) if sentence.strip()]
        return "\n".join(sentences[:3])

    def _reply_recipe_search(self, db: Session, text: str) -> tuple[str, list[dict[str, Any]], list[dict[str, str]]]:
        """레시피명 또는 재료명 검색 결과를 안내합니다."""
        keyword = self._extract_recipe_ingredient(text) or self._extract_keyword(text)
        try:
            result = recipe_search_service.search_recipes(db=db, query=keyword, page=1, page_size=3)
            items: list[dict[str, Any]] = result["items"]
            if not items:
                result = recipe_search_service.search_recipes(db=db, ingredient=keyword, main_ingredient_only=True, page=1, page_size=3)
                items = result["items"]
        except Exception:
            reply, sources = self._reply_external_recipe(keyword)
            return reply, [], sources

        if not items:
            reply, sources = self._reply_external_recipe(keyword)
            return reply, [], sources

        titles = [item["title"] for item in items]
        return ", ".join(titles) + " 레시피를 아래에서 확인해보세요.", self._recipe_actions(items), []
    def _reply_external_recipe(self, keyword: str) -> tuple[str, list[dict[str, str]]]:
        """내부 레시피가 없을 때 Tavily 검색 결과로 짧게 안내합니다."""
        if not settings.TAVILY_API_KEY or TavilyClient is None:
            return f"{keyword} 관련 레시피는 아직 우리 DB에 없어요. 웹 검색 답변은 Tavily 설정 후 사용할 수 있어요.", []

        client = TavilyClient(api_key=settings.TAVILY_API_KEY)
        try:
            result = client.search(query=f"{keyword} 레시피", search_depth="basic", max_results=3)
        except Exception:
            return f"{keyword} 레시피는 웹 검색을 시도했지만 지금은 연결이 불안정해요. 잠시 후 다시 시도해주세요.", []
        results = [item for item in result.get("results", []) if self._is_relevant_search_result(keyword, item)][:3]
        sources = [
            {"title": item.get("title") or item.get("url", "출처"), "url": item.get("url", "")}
            for item in results
            if item.get("url")
        ]
        content = "\n".join(item.get("content", "") for item in results if item.get("content"))[:1200]
        if not content:
            return f"{keyword} 레시피를 웹에서도 찾지 못했어요.", sources

        if settings.OPENAI_API_KEY and OpenAI is not None:
            client_ai = OpenAI(api_key=settings.OPENAI_API_KEY)
            response = client_ai.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "검색 결과 안에서만 한국어로 3문장 이하의 간단한 레시피 안내를 작성해."},
                    {"role": "user", "content": content},
                ],
                temperature=0.2,
            )
            summary = response.choices[0].message.content.strip()
        else:
            summary = content.split(".")[0].strip() + "."

        return f"우리 DB에는 아직 없어서 웹 검색 기준으로 안내할게요.\n{summary}", sources

    def _reply_recipe_recommend(self, db: Session, user_id: int, text: str) -> tuple[str, list[dict[str, Any]]]:
        """냉장고 재료 기반 또는 특정 재료 기반 레시피 추천 결과를 안내합니다."""
        keyword = self._extract_recipe_ingredient(text)
        if keyword:
            try:
                result = recipe_search_service.search_recipes(
                    db=db,
                    ingredient=keyword,
                    difficulty="초급",
                    cooking_time_label="30분이내",
                    main_ingredient_only=True,
                    page=1,
                    page_size=3,
                )
                items: list[dict[str, Any]] = result["items"]
                is_easy_result = bool(items)
                if not items:
                    result = recipe_search_service.search_recipes(db=db, ingredient=keyword, main_ingredient_only=True, page=1, page_size=3)
                    items = result["items"]
            except Exception:
                reply, _sources = self._reply_external_recipe(keyword)
                return reply, []

            list_action = {
                "label": f"{keyword} 레시피 더 보기",
                "url": f"/recipes?ingredient={quote(keyword)}",
                "data": {"ingredient": keyword},
            }
            if not items:
                return f"{keyword}가 주재료인 레시피를 찾지 못했어요.", [list_action]

            titles = [item["title"] for item in items]
            actions = self._recipe_actions(items) + [list_action]
            prefix = f"{keyword}가 주재료인 30분 이내 초급 레시피는 " if is_easy_result else f"{keyword}가 주재료인 레시피는 "
            return prefix + ", ".join(titles) + "예요.", actions

        try:
            result = recommendation_service.recommend_recipes(
                db,
                user_id,
                RecipeRecommendConfig.fridge_consume_preset(),
            )
        except Exception:
            return "냉장고 기반 추천을 불러오지 못했어요. 재료명을 넣어서 다시 물어봐주세요.", []

        items = [item for item in result.get("items", []) if item.get("missing_ingredient_count", 0) == 0]
        if not items:
            return "현재 냉장고 재료만으로 완성 가능한 레시피를 찾지 못했어요. 부족 재료를 허용하면 더 넓게 추천할 수 있어요.", []

        titles = [item["title"] for item in items[:3]]
        return "현재 냉장고 재료만으로는 " + ", ".join(titles) + "를 만들 수 있어요.", self._recipe_actions(items)


chat_service = ChatService()
