import re
from datetime import date
from typing import Any
from urllib.parse import quote

from sqlalchemy.orm import Session

from app.backend.core.config import settings as app_settings
from app.backend.services.guide_service.guide_service import guide_service
from ai.agents.guide_agent import answer_guide_query
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

from ai.agents.supervisor_agent.supervisor_utils import (
    _extract_keyword,
    _extract_recipe_ingredient,
    _normalize_recipe_keyword,
    _recipe_actions,
    _rank_recipe_items,
    _apply_josa,
    _is_guide_result_match,
    _keyword_tokens,
    _format_guide_tip
)

from ai.agents.supervisor_agent.supervisor_utils import (
    _is_login_status_question,
    _requires_login,
    _is_cooking_time_question,
    _is_expiring_question,
    _is_relevant_search_result
)

class ChatService:
    """사용자 자연어 메시지를 intent로 분류하고 기존 서비스를 호출합니다."""

    EMPTY_INVENTORY_REPLY = '냉장고가 비어 있어요. 재료를 등록하면 소비 임박 재료와 추천 메뉴를 알려드릴게요.'

    def handle_message(self, db: Session, user_id: int, message: str, history: list[Any] = None, user_settings: Any = None) -> dict[str, Any]:
        """LangGraph를 활용하여 메시지를 처리하고 챗봇 응답 딕셔너리를 반환합니다."""
        text = message.strip()
        
        # 로그인 상태 체크 (기존 로직 유지)
        if _is_login_status_question(text):
            reply = "현재 로그인된 상태예요." if user_id else "현재 비로그인 상태예요. 보관법이나 일반 레시피 검색은 이용할 수 있어요."
            return {"intent": "auth.status", "reply": reply, "actions": [], "sources": []}
            
        # 초기 상태(GraphState) 구성
        from ai.agents.supervisor_agent.supervisor_agent import supervisor_agent
        initial_state = {
            "user_id": user_id,
            "text": text,
            "history": history or [],
            "settings_obj": user_settings,
            "db": db,
            "service": self,
            "intent": None,
            "keyword": None,
            "response_text": None,
            "actions": [],
            "sources": []
        }
        
        # 그래프 실행
        try:
            final_state = supervisor_agent.invoke(initial_state)
            intent = final_state.get("intent", "general")
            reply = final_state.get("response_text", "")
            actions = final_state.get("actions") or []
            sources = final_state.get("sources") or []
        except Exception as e:
            print(f"[ChatService] graph failed: {type(e).__name__}: {e}")
            intent = "error"
            reply = "요청을 처리하는 중 문제가 생겼어요. 잠시 후 다시 시도해주세요."
            actions = []
            sources = []
            
        # LLM 단답형 요약 (사용자 설정)
        if user_settings and getattr(user_settings, 'shortAnswer', False) and len(reply) > 50:
            if OpenAI is not None and app_settings.OPENAI_API_KEY:
                client_ai = OpenAI(api_key=app_settings.OPENAI_API_KEY)
                try:
                    res = client_ai.chat.completions.create(
                        model=app_settings.OPENAI_MODEL,
                        messages=[
                            {"role": "system", "content": "다음 챗봇 응답을 핵심만 남겨서 1~2문장의 아주 짧은 대화체로 요약해. 존댓말을 사용해."},
                            {"role": "user", "content": reply}
                        ],
                        temperature=0.3
                    )
                    reply = res.choices[0].message.content.strip()
                except Exception:
                    pass

        return {"intent": intent, "reply": reply, "actions": actions, "sources": sources}

        
    def _route_intent_with_llm(self, text: str, history: list[Any] = None) -> str:
        """LangChain LLM을 활용하여 대화 문맥(history)과 현재 메시지로 의도를 파악합니다."""
        if _is_expiring_question(text):
            return "inventory.expiring"
        if _is_cooking_time_question(text):
            return "recipe.search"

        normalized = text.replace(" ", "").lower()
        guide_words = ('보관', '세척', '씻', '손질', '신선', '가이드', '어떡', '남은', '영양', '영양성분', '칼로리', '열량', '단백질', '탄수화물', '지방', '당류', '나트륨', '제철')
        if any(word in normalized for word in guide_words):
            return "ingredient.guide"

        rule_intent = self._route_intent(text)
        if rule_intent != "general":
            return rule_intent

        if not app_settings.OPENAI_API_KEY or OpenAI is None:
            return self._route_intent(text)

        try:
            from langchain_openai import ChatOpenAI
            from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
            
            llm = ChatOpenAI(model=app_settings.OPENAI_MODEL, api_key=app_settings.OPENAI_API_KEY, temperature=0.0)
            
            system_prompt = """
당신은 챗봇의 의도 분류기(Intent Classifier)입니다.
사용자의 메시지와 이전 대화 맥락을 보고 다음 중 가장 적합한 의도(Intent) 1개만 정확하게 출력하세요. 다른 설명은 절대 붙이지 마세요.

[분류 가능 의도 목록]
- receipt.guide: 영수증, OCR, 구매내역 등록 관련
- recipe.recommend: "치킨 추천해줘", "두부로 뭐해먹지", "그거 말고 다른거", "이 재료들로 할 수 있는 요리" 등 요리/레시피 추천
- recipe.search: "김치볶음밥 레시피", "파스타 요리법" 등 특정 요리 검색
- ingredient.guide: "치킨 보관법", "남은 재료 어떡해", "두부 손질" 등 식재료 관리/보관
- inventory.expiring: "상하는 거 뭐 있어", "소비기한 임박", "d-day" 등 임박 재료 확인
- inventory.list: "냉장고에 뭐 있지?", "내 재료 목록" 등 보유 식재료 단순 확인 (주의: 식재료 '추가'나 '삭제' 요청은 제외)
- general: 식재료 추가/수정/삭제 요청(예: "마늘 추가해줘", "감자 지워줘") 및 위 어느 것에도 해당하지 않는 일상 대화

[매우 중요한 주의사항]
사용자가 "그거 말고", "다른 거", "딴거", "사이드 메뉴는?", "더 알려줘" 와 같이 지시대명사나 후속 질문을 던질 경우, 반드시 직전 대화의 챗봇 응답이 어떤 의도였는지 파악하세요. 직전에 레시피를 추천했다면 반드시 'recipe.recommend'를 출력해야 합니다. 'general'로 분류하지 마세요!
            """
            
            messages = [SystemMessage(content=system_prompt)]
            
            if history:
                for msg in history[-4:]: # 최근 4개 메시지만 참조
                    if msg.role == 'user':
                        messages.append(HumanMessage(content=msg.text))
                    elif msg.role == 'bot':
                        messages.append(AIMessage(content=msg.text))
                        
            messages.append(HumanMessage(content=text))
            
            response = llm.invoke(messages)
            intent = response.content.strip()
            valid_intents = ["receipt.guide", "recipe.recommend", "recipe.search", "ingredient.guide", "inventory.expiring", "inventory.list", "general"]
            
            if intent in valid_intents:
                return intent
            return self._route_intent(text)
        except Exception:
            return self._route_intent(text)

    def _route_intent(self, text: str) -> str:
        """키워드 기반으로 1차 챗봇 intent를 분류합니다."""
        normalized = text.replace(" ", "").lower()

        if any(word in normalized for word in ("영수증", "ocr", "구매내역")):
            return "receipt.guide"
            
        if _is_expiring_question(text):
            return "inventory.expiring"
        if _is_cooking_time_question(text):
            return "recipe.search"
            
        if "냉장고" in normalized and "재료" in normalized and "요리" in normalized:
            return "recipe.recommend"
        if any(word in normalized for word in ("추천", "뭐해먹", "뭐먹", "뭐하지", "뭘", "만들지", "만들요리", "만들어먹", "요리추천", "만들수", "만들수있는", "만들수있", "할수", "할수있는", "메뉴", "냉장고파먹", "쓸수", "쓸수있", "활용", "어디에쓸", "다른거", "딴거")):
            return "recipe.recommend"
        if any(word in normalized for word in ("레시피", "요리법", "요리")):
            return "recipe.search"
            
        if any(word in normalized for word in ('보관법', '보관방법', '보관', '손질', '세척', '씻', '신선', '확인', '가이드', '어떡', '어떻게하지', '먹다남은', '남은', '영양', '영양성분', '칼로리', '열량', '단백질', '탄수화물', '지방', '당류', '나트륨', '제철')):
            return "ingredient.guide"
        if any(word in normalized for word in ("상하는", "임박", "소비기한", "유통기한", "기한", "먼저먹", "먹어야", "다되어", "다돼", "끝나", "d-day", "디데이")):
            return "inventory.expiring"
        if any(word in normalized for word in ("뭐있", "뭐가있", "냉장고목록", "재료목록", "내재료")):
            return "inventory.list"
            
        return "general"

    def _reply_guide(self, text: str) -> tuple[str, list[dict[str, str]]]:
        """Guide Agent 공통 응답을 챗봇 말풍선 형식으로 변환합니다."""
        normalized = text.replace(" ", "").lower()
        query = text
        if "제철" in normalized and not re.search(r"\d{1,2}\s*월", text):
            query = f"{date.today().month}월 {text}"
        elif "제철" not in normalized:
            # 제철음식 검색이 아닌 일반 가이드 검색의 경우 핵심 식재료명만 추출
            extracted = _extract_keyword(text)
            if not extracted:
                return "질문하신 내용에서 명확한 식재료 이름을 찾지 못했어요. '당근 보관법'처럼 식재료를 명시해서 다시 물어봐 주시겠어요?", []
            # extracted는 검증용으로만 쓰고, 실제 검색어는 원문(query)을 그대로 넘겨야 
            # 가이드 에이전트가 "세척법", "손질법" 등의 의도를 파악할 수 있음

        agent_result = answer_guide_query(query)
        sources = agent_result.get("ui", {}).get("sources", [])
        for source in sources:
            if source.get("url") is None:
                source["url"] = ""

        if not agent_result.get("ok"):
            return agent_result.get("message") or "가이드 정보를 찾지 못했어요.", sources

        action = agent_result.get("action")
        data = agent_result.get("data", {})

        if action == "list_seasonal_ingredients":
            month = data.get("month") or date.today().month
            names = [item.get("name") for item in data.get("items", []) if item.get("name")]
            if not names:
                return f"{month}월 제철 식재료는 아직 찾지 못했어요.", sources
            preview = ", ".join(names[:10])
            suffix = " 등" if len(names) > 10 else ""
            return f"{month}월 제철 식재료는 {preview}{suffix}이에요.", sources

        if action == "lookup_nutrition":
            nutrition = data.get("nutrition") or {}
            ingredient = data.get("ingredient") or {}
            item_name = ingredient.get("name") or nutrition.get("representative_name") or nutrition.get("food_name") or _extract_keyword(text)
            lines = []
            base = nutrition.get("nutrition_base_amount") or nutrition.get("base_amount")
            if base:
                lines.append(f"기준량: {base}")
            for key, label, unit in (
                ("energy_kcal", "열량", "kcal"),
                ("protein_g", "단백질", "g"),
                ("carbohydrate_g", "탄수화물", "g"),
                ("fat_g", "지방", "g"),
                ("sugar_g", "당류", "g"),
                ("sodium_mg", "나트륨", "mg"),
            ):
                value = nutrition.get(key)
                if value is not None:
                    lines.append(f"{label}: {value}{unit}")
            if not lines:
                return agent_result.get("message") or f"{item_name}의 영양성분 정보는 아직 준비 중이에요.", sources
            return f"{item_name} 영양성분이에요.\n" + "\n".join(lines[:7]), sources
        # 일반 가이드 질문은 보관법을 기본값으로 두고, 명시 키워드만 다른 유형으로 보냅니다.
        guide_type = "storage"
        if "손질" in normalized:
            guide_type = "prep"
        elif "세척" in normalized or "씻" in normalized:
            guide_type = "washing"
        elif "신선" in normalized or "상한" in normalized:
            guide_type = "freshness"
        guide = (data.get("guides") or {}).get(guide_type) or {}
        tip = guide.get("content")
        ingredient = data.get("ingredient") or {}
        item_name = ingredient.get("name") or _extract_keyword(text)
        if not tip:
            return agent_result.get("message") or f"{item_name} 가이드 정보는 아직 준비 중이에요.", sources

        labels = {
            "storage": "보관법",
            "prep": "손질방법",
            "washing": "세척방법",
            "freshness": "신선도 확인법",
        }
        formatted_tip = _format_guide_tip(tip)
        return f"{item_name} {labels.get(guide_type, '가이드')}이에요.\n{formatted_tip}", sources

    def _reply_external_guide(self, keyword: str, category_label: str = "보관법") -> tuple[str, list[dict[str, str]]]:
        """내부 가이드가 없을 때 Tavily 검색 결과를 짧게 요약합니다."""
        if not app_settings.TAVILY_API_KEY or TavilyClient is None:
            return f"{keyword} 정보는 아직 우리 가이드에 없어요. 웹 검색 답변은 Tavily 설정 후 사용할 수 있어요.", []

        client = TavilyClient(api_key=app_settings.TAVILY_API_KEY)
        try:
            result = client.search(query=f"{keyword} {category_label}", search_depth="basic", max_results=5)
        except Exception:
            return f"{keyword} 정보는 웹 검색을 시도했지만 지금은 연결이 불안정해요. 잠시 후 다시 시도해주세요.", []
        results = [item for item in result.get("results", []) if _is_relevant_search_result(keyword, item)][:3]
        sources = [
            {"title": item.get("title") or item.get("url", "출처"), "url": item.get("url", "")}
            for item in results
            if item.get("url")
        ]
        content = "\n".join(item.get("content", "") for item in results if item.get("content"))[:1200]
        if not content:
            return f"{keyword} 정보를 웹에서 찾지 못했어요.", sources

        if app_settings.OPENAI_API_KEY and OpenAI is not None:
            try:
                client_ai = OpenAI(api_key=app_settings.OPENAI_API_KEY)
                response = client_ai.chat.completions.create(
                    model=app_settings.OPENAI_MODEL,
                    messages=[
                        {"role": "system", "content": f"검색 결과 안에서만 한국어로 식재료 {category_label}을(를) 요약해. 바로 따라할 수 있는 짧은 문장 3개 이내로 쓰고, 각 문장은 줄바꿈으로 구분해. 추측은 하지 마."},
                        {"role": "user", "content": f"질문 키워드: {keyword}\n검색 결과:\n{content}"},
                    ],
                    temperature=0.2,
                )
                summary = response.choices[0].message.content.strip()
            except Exception:
                summary = content.split(".")[0].strip() + "."
        else:
            summary = content.split(".")[0].strip() + "."

        return summary, sources

    def _reply_recipe_search(self, db: Session, text: str) -> tuple[str, list[dict[str, Any]], list[dict[str, str]]]:
        """레시피명 또는 재료명 검색 결과를 안내합니다."""
        keyword = _extract_recipe_ingredient(text) or _extract_keyword(text)
        if _is_cooking_time_question(text):
            reply, sources = self._reply_external_recipe(keyword, text)
            return reply, [], sources

        try:
            # 재료명 질문은 주재료 검색을 먼저 적용해 엉뚱한 제목검색 결과를 줄입니다.
            result = recipe_search_service.search_recipes(db=db, ingredient=keyword, main_ingredient_only=True, page=1, page_size=10)
            items: list[dict[str, Any]] = result["items"]
            if not items:
                result = recipe_search_service.search_recipes(db=db, query=keyword, page=1, page_size=10)
                items = result["items"]
        except Exception:
            reply, sources = self._reply_external_recipe(keyword)
            return reply, [], sources

        if not items:
            reply, sources = self._reply_external_recipe(keyword)
            return reply, [], sources

        items = _rank_recipe_items(keyword, items)
        titles = [item["title"] for item in items[:3]]
        reply = f"{keyword} 관련 레시피예요.\n" + "\n".join(f"{index + 1}. {title}" for index, title in enumerate(titles))
        return reply, _recipe_actions(items), []

    def _reply_external_recipe(self, keyword: str, query_text: str | None = None) -> tuple[str, list[dict[str, str]]]:
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
                        {"role": "system", "content": "당신은 요리와 냉장고 관리를 도와주는 친절한 비서 챗봇 '밥벌이'입니다. 검색 결과를 바탕으로 사용자의 질문에 다정하게 대답하세요. 특정 요리의 레시피를 묻는다면 핵심 조리 흐름을 3문장 이내로 요약해주고, 메뉴 추천을 원한다면 상황에 어울리는 요리 2~3가지를 다정하게 추천해주세요."},
                        {"role": "user", "content": f"질문/키워드: {query_text or keyword}\n검색 결과:\n{content}\n\n위 내용을 바탕으로 친절하게 답변해줘."},
                    ],
                    temperature=0.2,
                )
                summary = response.choices[0].message.content.strip()
            except Exception:
                summary = content.split(".")[0].strip() + "."
        else:
            summary = content.split(".")[0].strip() + "."

        return summary, sources

    def _reply_recipe_recommend(self, db: Session, user_id: int, text: str, history: list[Any] = None, settings_obj: Any = None) -> tuple[str, list[dict[str, Any]]]:
        """냉장고 재료 기반 또는 특정 재료 기반 레시피 추천 결과를 안내합니다."""
        keyword = _extract_recipe_ingredient(text)
        
        # 만약 "그거 말고 다른거"처럼 키워드가 없다면 history에서 이전 키워드 유추
        if not keyword and history:
            try:
                from langchain_openai import ChatOpenAI
                from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
                llm = ChatOpenAI(model=app_settings.OPENAI_MODEL, api_key=app_settings.OPENAI_API_KEY, temperature=0.0)
                messages = [SystemMessage(content="사용자 대화 맥락을 보고, 요리 추천을 위해 검색할 '핵심 식재료' 또는 '요리 상황/컨셉(예: 비올때, 매운거, 다이어트 등)' 키워드 1개만 단답형으로 출력해. 사용자가 '그거 말고 딴거'처럼 지시대명사를 쓰면 이전 맥락의 키워드를 찾아서 반환해. 절대 부연설명 없이 단어 1개만 출력해. 도저히 찾을 수 없으면 'None' 반환.")]
                for msg in history[-4:]:
                    messages.append(HumanMessage(content=msg.text) if msg.role == 'user' else AIMessage(content=msg.text))
                messages.append(HumanMessage(content=text))
                res = llm.invoke(messages).content.strip()
                if res != "None" and res not in ("다른거", "딴거", "그거", "저거", "이거", "다른 거", "딴 거", "내", "나", "제"):
                    keyword = res
            except Exception:
                pass
        if keyword:
            past_bot_texts = " ".join([msg.text for msg in history if msg.role == "bot"]) if history else ""
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
                    result = recipe_search_service.search_recipes(db=db, ingredient=keyword, main_ingredient_only=True, page=1, page_size=10)
                    raw_items = _rank_recipe_items(keyword, result["items"])
                
                # 이미 추천한 레시피는 제외
                new_items = [item for item in raw_items if item["title"] not in past_bot_texts]
                if not new_items:
                    new_items = raw_items
                items = new_items[:3]
            except Exception:
                reply, _sources = self._reply_external_recipe(keyword)
                return reply, []

            list_action = {
                "label": f"{keyword} 레시피 더 보기",
                "url": f"/recipes?ingredient={quote(keyword)}",
                "data": {"ingredient": keyword},
            }
            if not items:
                reply, _sources = self._reply_external_recipe(keyword)
                return reply, []

            titles = [item["title"] for item in items]
            actions = _recipe_actions(items) + [list_action]
            prefix = f"{_apply_josa(keyword, '이가')} 주재료인 30분 이내 초급 레시피는 " if is_easy_result else f"{_apply_josa(keyword, '이가')} 주재료인 레시피는 "
            return prefix + "\n" + "\n".join(f"{index + 1}. {title}" for index, title in enumerate(titles)), actions
        from ai.agents.inventory_agent.inventory_agent import is_inventory_empty
        if is_inventory_empty(db=db, user_id=user_id):
            return self.EMPTY_INVENTORY_REPLY, []

        try:
            config = RecipeRecommendConfig.fridge_consume_preset()
            if settings_obj:
                if not getattr(settings_obj, 'expiringFirst', True):
                    config.mode = "fridge_all"
                if not getattr(settings_obj, 'excludeDislikes', True):
                    config.exclude_dislikes = False

            result = recommendation_service.recommend_recipes(db, user_id, config)
        except Exception:
            return "냉장고 기반 추천을 불러오지 못했어요. 재료명을 넣어서 다시 물어봐주세요.", []

        raw_items = result.get("items", [])
        sorted_items = sorted(
            raw_items,
            key=lambda x: (
                -x.get("final_score", 0),
                x.get("missing_ingredient_count", 0),
                -x.get("owned_ingredient_count", 0),
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
            prefix = "소비임박 재료를 우선으로 활용할 수 있는 레시피예요. 부족한 재료는 약간 있을 수 있어요.\n"

        titles = [item["title"] for item in items]
        return prefix + "\n".join(f"{index + 1}. {title}" for index, title in enumerate(titles)), _recipe_actions(items)

supervisor_service = ChatService()
