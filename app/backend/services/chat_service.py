import re
from typing import Any
from urllib.parse import quote

from sqlalchemy.orm import Session

from app.backend.core.config import settings as app_settings
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

    def handle_message(self, db: Session, user_id: int, message: str, history: list[Any] = None, user_settings: Any = None) -> dict[str, Any]:
        """LangGraph를 활용하여 메시지를 처리하고 챗봇 응답 딕셔너리를 반환합니다."""
        text = message.strip()
        
        # 로그인 상태 체크 (기존 로직 유지)
        if self._is_login_status_question(text):
            reply = "현재 로그인된 상태예요." if user_id else "현재 비로그인 상태예요. 보관법이나 일반 레시피 검색은 이용할 수 있어요."
            return {"intent": "auth.status", "reply": reply, "actions": [], "sources": []}
            
        from langchain_core.messages import HumanMessage, AIMessage
        
        # 멀티턴 대응: 이전 대화 기록을 LangChain Messages 형식으로 변환
        langchain_messages = []
        if history:
            for msg in history[-4:]: # 최근 4개 메시지
                if msg.role == 'user':
                    langchain_messages.append(HumanMessage(content=msg.text))
                elif msg.role == 'bot':
                    langchain_messages.append(AIMessage(content=msg.text))
        langchain_messages.append(HumanMessage(content=text))
        
        # 초기 상태(GraphState) 구성
        from app.backend.services.chat_graph import chat_graph
        initial_state = {
            "user_id": user_id,
            "text": text,
            "history": history or [],
            "settings_obj": user_settings,
            "db": db,
            "service": self,
            "intent": None,
            "keyword": None,
            "messages": langchain_messages,
            "response_text": None,
            "actions": [],
            "sources": []
        }
        
        # 그래프 실행
        try:
            final_state = chat_graph.invoke(initial_state)
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

    def _is_login_status_question(self, text: str) -> bool:
        """사용자가 현재 로그인 상태를 묻는 문장인지 확인합니다."""
        normalized = text.replace(" ", "").lower()
        return "로그인" in normalized and any(word in normalized for word in ("되어", "됐", "되있", "상태", "했", "했어"))

    def _requires_login(self, intent: str, text: str) -> bool:
        """개인 냉장고 데이터가 필요한 챗봇 의도인지 확인합니다."""
        normalized = text.replace(" ", "").lower()
        personal_recipe_words = ("내식재료", "내재료", "보유식재료", "보유재료", "냉장고재료", "있는걸로", "이걸로")
        if intent in ("inventory.list", "inventory.expiring"):
            return True
        if intent == "recipe.recommend" and any(word in normalized for word in personal_recipe_words):
            return True
        if intent == "recipe.recommend" and not self._extract_recipe_ingredient(text):
            return True
        return False

    def _is_cooking_time_question(self, text: str) -> bool:
        """조리 시간이나 온도를 묻는 질문인지 확인합니다."""
        normalized = text.replace(" ", "").lower()
        return any(word in normalized for word in ("에어프라이", "몇분", "몇도", "온도", "조리시간", "굽는시간", "익히는시간"))

    def _route_intent_with_llm(self, text: str, history: list[Any] = None) -> str:
        """LangChain LLM을 활용하여 대화 문맥(history)과 현재 메시지로 의도를 파악합니다."""
        if self._is_cooking_time_question(text):
            return "recipe.search"

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
- inventory.list: "냉장고에 뭐 있지?", "내 재료 목록" 등 보유 식재료 단순 확인
- general: 위 어느 것에도 해당하지 않는 단순 인사나 일상 대화

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
            
        if self._is_cooking_time_question(text):
            return "recipe.search"
            
        if any(word in normalized for word in ("추천", "뭐해먹", "뭐먹", "뭐하지", "뭘", "만들지", "만들수", "만들수있는", "만들수있", "할수", "할수있는", "메뉴", "냉장고파먹", "쓸수", "쓸수있", "활용", "어디에쓸", "다른거", "딴거")):
            return "recipe.recommend"
        if any(word in normalized for word in ("레시피", "요리법", "요리")):
            return "recipe.search"
            
        if any(word in normalized for word in ("보관법", "보관방법", "보관", "손질", "세척", "씻", "신선", "확인", "가이드", "어떡", "어떻게하지", "먹다남은", "남은")):
            return "ingredient.guide"
        if any(word in normalized for word in ("상하는", "임박", "소비기한", "유통기한", "기한", "먼저먹", "먹어야", "다되어", "다돼", "끝나", "d-day", "디데이")):
            return "inventory.expiring"
        if any(word in normalized for word in ("뭐있", "뭐가있", "냉장고목록", "재료목록", "내재료")):
            return "inventory.list"
            
        return "general"

    def _extract_keyword(self, text: str) -> str:
        """조사와 기능 키워드를 덜어내고 검색에 쓸 핵심 단어를 추립니다."""
        cleaned = re.sub(
            r"(먹다\s*남은|먹다남은|남은|먹다|어떡하지|어떡해|어떻게하지|보관법|보관방법|보관해|보관|세척법|세척방법|세척|씻|손질법|손질방법|손질|신선도|확인법|확인|어떻게|가이드|레시피|요리|추천|알려줘|찾아줘|해줘|좀|해먹을|만들)",
            " ",
            text,
        )
        words = [word.strip() for word in cleaned.split() if word.strip() and word.strip() not in ("내", "제", "나", "어떤", "무슨", "이", "그", "저", "이런", "그런", "저런", "수", "있어", "있어?", "있나요", "있나요?")]
        return words[0] if words else text.strip()

    def _extract_recipe_ingredient(self, text: str) -> str:
        """'두부로 뭐 만들 수 있어?' 같은 문장에서 재료명을 추출합니다."""
        match = re.search(r"(?:남은\s*)?([가-힣A-Za-z0-9]+?)(?:으로|로).*(?:뭐|뭘|무엇|메뉴|레시피|요리|만들|추천)", text)
        if not match:
            match = re.search(r"(?:남은\s*)?([가-힣A-Za-z0-9]+?)\s*(?:빨리|먼저|써야|처리).*(?:뭐|뭘|무엇|메뉴|레시피|요리|추천|하지)", text)
        if not match:
            match = re.search(r"^\s*(?:먹다\s*남은|먹다남은|남은)?\s*([가-힣A-Za-z0-9]+?)\s*(?:어디에\s*)?(?:쓸\s*수|쓸수|활용|처리)", text)
        if not match:
            return ""

        keyword = match.group(1).strip()
        if keyword in ("걸", "있는", "이걸", "이것", "그걸", "그것", "재료", "식재료", "보유재료", "냉장고", "내", "제", "나", "내식재료", "제식재료", "남은거"):
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

    def _rank_recipe_items(self, keyword: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """질문한 재료가 제목에 직접 드러나고 조리가 쉬운 레시피를 먼저 보여줍니다."""
        normalized_keyword = keyword.replace(" ", "")

        def score(item: dict[str, Any]) -> tuple[int, int, int]:
            title = (item.get("title") or "").replace(" ", "")
            difficulty = item.get("difficulty") or ""
            cooking_time = item.get("cooking_time_min") or 9999
            return (
                0 if normalized_keyword and normalized_keyword in title else 1,
                0 if difficulty == "초급" else 1,
                int(cooking_time),
            )

        return sorted(items, key=score)

    def _apply_josa(self, word: str, josa_type: str) -> str:
        """단어의 마지막 글자 받침 유무에 따라 알맞은 조사를 붙여 반환합니다."""
        if not word: return ""
        last_char = word[-1]
        if not ('가' <= last_char <= '힣'):
            return word + ("가" if josa_type == "이가" else "는" if josa_type == "은는" else "를")
        
        has_jongseong = (ord(last_char) - 44032) % 28 > 0
        
        if josa_type == "이가":
            return word + ("이" if has_jongseong else "가")
        elif josa_type == "은는":
            return word + ("은" if has_jongseong else "는")
        elif josa_type == "을를":
            return word + ("을" if has_jongseong else "를")
        elif josa_type == "과와":
            return word + ("과" if has_jongseong else "와")
        return word

    def _reply_inventory_list(self, db: Session, user_id: int) -> str:
        """냉장고 보유 재료를 짧게 요약합니다."""
        items = inventory_service.get_ingredients(db=db, user_id=user_id)
        if not items:
            return "현재 냉장고에 등록된 재료가 없어요."

        names = [item["name"] for item in items[:8]]
        suffix = "" if len(items) <= 8 else f" 외 {len(items) - 8}개"
        target_word = suffix if suffix else names[-1]
        return f"현재 냉장고에는 {', '.join(names[:-1]) + ', ' if len(names) > 1 else ''}{self._apply_josa(target_word, '이가')} 있어요."

    def _extract_expiry_keyword(self, text: str) -> str:
        """특정 재료의 소비기한 질문이면 재료명을 추출합니다."""
        match = re.search(r"([가-힣A-Za-z0-9]+)\s*(?:유통기한|소비기한|기한)", text)
        if not match:
            match = re.search(r"^\s*(?:먹다\s*남은|먹다남은|남은)?\s*([가-힣A-Za-z0-9]+?)\s*(?:어디에\s*)?(?:쓸\s*수|쓸수|활용|처리)", text)
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
        return "소비기한이 가까운 재료는\n" + ", ".join(summary) + "예요."

    def _format_d_day(self, d_day: int) -> str:
        """프론트와 같은 기준으로 D-day 문구를 표시합니다."""
        if d_day > 0:
            return f"D-{d_day}"
        if d_day == 0:
            return "D-Day"
        return f"D+{abs(d_day)} 지남"

    def _is_guide_result_match(self, keyword: str, guide_name: str) -> bool:
        """가이드 검색 결과가 질문한 식재료와 같은 대상인지 확인합니다."""
        normalized_keyword = keyword.replace(" ", "").lower()
        normalized_name = guide_name.replace(" ", "").lower()
        aliases = {"파": {"대파", "쪽파", "실파"}, "계란": {"달걀"}, "달걀": {"계란"}}
        if normalized_keyword == normalized_name or normalized_name in aliases.get(normalized_keyword, set()):
            return True
        if len(normalized_keyword) <= 1:
            return False
        misleading_suffixes = ("소스", "가루", "분말", "즙", "청", "오일", "잼", "스톡")
        if normalized_name.startswith(normalized_keyword) and normalized_name.endswith(misleading_suffixes):
            return False
        if normalized_name.startswith(normalized_keyword) and any(suffix in normalized_name for suffix in misleading_suffixes):
            return False
        return normalized_keyword in normalized_name or normalized_name in normalized_keyword

    def _keyword_tokens(self, keyword: str) -> list[str]:
        """검색 검증에 쓸 핵심 단어만 추립니다."""
        stopwords = {"먹다남은", "남은", "먹다", "보관", "보관법", "보관방법", "세척", "세척법", "세척방법", "손질", "손질법", "손질방법", "신선도", "확인법", "알려줘", "식재료", "레시피", "어떡하지", "어떡해"}
        return [
            token
            for token in re.findall(r"[가-힣A-Za-z0-9]+", keyword.lower())
            if len(token) > 1 and token not in stopwords
        ]

    def _reply_guide(self, text: str) -> tuple[str, list[dict[str, str]]]:
        """식재료 가이드 검색 결과를 이용해 보관/손질/세척/신선도 정보를 안내합니다."""
        keyword = self._extract_keyword(text)
        
        # 질문 종류 파악
        category = "storage"
        normalized = text.replace(" ", "").lower()
        if "손질" in normalized:
            category = "prep"
        elif "세척" in normalized or "씻" in normalized:
            category = "washing"
        elif "신선" in normalized or "상하는" in normalized or "상한" in normalized:
            category = "freshness"
            
        try:
            guides = guide_service.search_guides(keyword=keyword, page=1, page_size=1)
            if not guides["items"]:
                return self._reply_external_guide(keyword)

            item = guides["items"][0]
            if not self._is_guide_result_match(keyword, item["name"]):
                return self._reply_external_guide(keyword)
                
            detail = guide_service.get_guide_detail(item["code"]) or {}
            
            if category == "prep":
                tip = detail.get("prep_tips")
                label = "손질방법"
            elif category == "washing":
                tip = detail.get("washing_tips")
                label = "세척방법"
            elif category == "freshness":
                tip = detail.get("freshness_tips")
                label = "신선도 확인법"
            else:
                tip = detail.get("storage_tips") or detail.get("horticultural_storage_tips")
                label = "보관법"
                
        except Exception:
            return self._reply_external_guide(keyword, "보관법")

        if not tip:
            return f"알고 계신 {item['name']} 가이드는 찾았지만, 아쉽게도 {label}에 대한 구체적인 정보가 비어 있어요. 😅", []

        formatted_tip = self._format_guide_tip(tip)
        if len(formatted_tip) < 45:
            extra_reply, extra_sources = self._reply_external_guide(keyword, label)
            extra_tip = extra_reply.split("\n\n", 1)[-1] if "\n\n" in extra_reply else ""
            if extra_tip and "찾지 못했어요" not in extra_reply and "연결이 불안정" not in extra_reply:
                return f"{item['name']} {label}이에요.\n{formatted_tip}\n\n추가로 참고하면 좋아요.\n{extra_tip}", extra_sources

        return f"{item['name']} {label}이에요.\n{formatted_tip}", []

    def _is_relevant_search_result(self, keyword: str, item: dict[str, Any]) -> bool:
        """검색 결과 제목/본문이 질문 핵심어와 맞는지 확인합니다."""
        tokens = self._keyword_tokens(keyword)
        if not tokens:
            return False

        haystack = f"{item.get('title', '')} {item.get('content', '')}".lower()
        words = self._keyword_tokens(haystack)
        primary = tokens[0]
        return any(self._is_guide_result_match(primary, word) for word in words)

    def _reply_external_guide(self, keyword: str, category_label: str = "보관법") -> tuple[str, list[dict[str, str]]]:
        """내부 가이드가 없을 때 Tavily 검색 결과를 짧게 요약합니다."""
        if not app_settings.TAVILY_API_KEY or TavilyClient is None:
            return f"{keyword} 정보는 아직 우리 가이드에 없어요. 웹 검색 답변은 Tavily 설정 후 사용할 수 있어요.", []

        client = TavilyClient(api_key=app_settings.TAVILY_API_KEY)
        try:
            result = client.search(query=f"{keyword} {category_label}", search_depth="basic", max_results=5)
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

    def _format_guide_tip(self, tip: str) -> str:
        """긴 보관법 문장을 챗봇에서 읽기 쉬운 번호 문장으로 나눕니다."""
        sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?。])\s+", tip) if sentence.strip()]
        if len(sentences) <= 1:
            sentences = [sentence.strip() for sentence in re.split(r"[;；]\s*", tip) if sentence.strip()]
        if len(sentences) <= 1:
            return sentences[0] if sentences else tip.strip()
        return "\n".join(f"{index + 1}. {sentence}" for index, sentence in enumerate(sentences[:3]))

    def _reply_recipe_search(self, db: Session, text: str) -> tuple[str, list[dict[str, Any]], list[dict[str, str]]]:
        """레시피명 또는 재료명 검색 결과를 안내합니다."""
        keyword = self._extract_recipe_ingredient(text) or self._extract_keyword(text)
        if self._is_cooking_time_question(text):
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

        items = self._rank_recipe_items(keyword, items)
        titles = [item["title"] for item in items[:3]]
        reply = f"{keyword} 관련 레시피예요.\n" + "\n".join(f"{index + 1}. {title}" for index, title in enumerate(titles))
        return reply, self._recipe_actions(items), []

    def _reply_external_recipe(self, keyword: str, query_text: str | None = None) -> tuple[str, list[dict[str, str]]]:
        """내부 레시피가 없을 때 Tavily 검색 결과로 짧게 안내합니다."""
        if not app_settings.TAVILY_API_KEY or TavilyClient is None:
            return f"{keyword} 관련 레시피는 아직 우리 DB에 없어요. 웹 검색 답변은 Tavily 설정 후 사용할 수 있어요.", []

        client = TavilyClient(api_key=app_settings.TAVILY_API_KEY)
        try:
            result = client.search(query=query_text or f"{keyword} 레시피", search_depth="basic", max_results=3)
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

        if app_settings.OPENAI_API_KEY and OpenAI is not None:
            try:
                client_ai = OpenAI(api_key=app_settings.OPENAI_API_KEY)
                response = client_ai.chat.completions.create(
                    model=app_settings.OPENAI_MODEL,
                    messages=[
                        {"role": "system", "content": "검색 결과 안에서만 한국어로 답해. 조리 시간이나 온도 질문이면 시간과 온도를 먼저 말하고, 레시피 질문이면 핵심 조리 흐름을 3문장 이내로 안내해. 추측은 하지 마."},
                        {"role": "user", "content": f"질문: {query_text or keyword}\n검색 결과:\n{content}"},
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
        keyword = self._extract_recipe_ingredient(text)
        
        # 만약 "그거 말고 다른거"처럼 키워드가 없다면 history에서 이전 키워드 유추
        if not keyword and history:
            try:
                from langchain_openai import ChatOpenAI
                from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
                llm = ChatOpenAI(model=app_settings.OPENAI_MODEL, api_key=app_settings.OPENAI_API_KEY, temperature=0.0)
                messages = [SystemMessage(content="사용자 대화 맥락을 보고, 사용자가 현재 요리를 추천받고 싶어하는 '핵심 식재료 이름(예: 치킨, 소고기, 양파)' 1개만 단답형으로 출력해. 사용자가 '그거 말고 딴거'처럼 지시대명사를 쓰면 이전 맥락의 주재료를 찾아서 반환해. 절대 부연설명 없이 단어 1개만 출력해. 도저히 찾을 수 없으면 'None' 반환.")]
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
                raw_items: list[dict[str, Any]] = self._rank_recipe_items(keyword, result["items"])
                is_easy_result = bool(raw_items)
                if not raw_items:
                    result = recipe_search_service.search_recipes(db=db, ingredient=keyword, main_ingredient_only=True, page=1, page_size=10)
                    raw_items = self._rank_recipe_items(keyword, result["items"])
                
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
                return reply, [list_action]

            titles = [item["title"] for item in items]
            actions = self._recipe_actions(items) + [list_action]
            prefix = f"{self._apply_josa(keyword, '이가')} 주재료인 30분 이내 초급 레시피는 " if is_easy_result else f"{self._apply_josa(keyword, '이가')} 주재료인 레시피는 "
            return prefix + "\n" + "\n".join(f"{index + 1}. {title}" for index, title in enumerate(titles)), actions

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

        items = [item for item in result.get("items", []) if item.get("missing_ingredient_count", 0) == 0]
        if not items:
            return "현재 냉장고 재료만으로 완성 가능한 레시피를 찾지 못했어요. 부족 재료를 허용하면 더 넓게 추천할 수 있어요.", []

        titles = [item["title"] for item in items[:3]]
        return "현재 냉장고 재료만으로 만들 수 있는 레시피예요.\n" + "\n".join(f"{index + 1}. {title}" for index, title in enumerate(titles)), self._recipe_actions(items)


chat_service = ChatService()
