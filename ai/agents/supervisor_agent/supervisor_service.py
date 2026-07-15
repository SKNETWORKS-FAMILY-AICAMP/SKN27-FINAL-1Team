import json
import os
import re
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.backend.core.config import settings as app_settings
from ai.agents.guide_agent import answer_guide_query

try:
    from tavily import TavilyClient
except ImportError:
    TavilyClient = None

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

try:
    from langfuse import propagate_attributes
    from langfuse.langchain import CallbackHandler as LangfuseCallbackHandler
except ImportError:
    propagate_attributes = None
    LangfuseCallbackHandler = None

from ai.agents.supervisor_agent.supervisor_utils import (
    _extract_keyword,
    _format_guide_tip,
    _is_cooking_time_question,
    _is_expiring_question,
    _is_login_status_question,
    _is_relevant_search_result,
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
            "intent_payload": {},
            "slots": {},
            "keyword": None,
            "response_text": None,
            "actions": [],
            "sources": []
        }
        
        # LangFuse 그래프 실행
        try:
            if (
                propagate_attributes
                and LangfuseCallbackHandler
                and os.getenv("LANGFUSE_PUBLIC_KEY")
                and os.getenv("LANGFUSE_SECRET_KEY")
            ):
                with propagate_attributes(
                    trace_name="bobbeori-supervisor-chat",
                    user_id=str(user_id or "guest"),
                    session_id=str(user_id or "guest"),
                    tags=["supervisor", "chatbot", "langgraph"],
                ):
                    final_state = supervisor_agent.invoke(
                        initial_state,
                        config={
                            "callbacks": [LangfuseCallbackHandler()],
                            "run_name": "supervisor-chat",
                        },
                    )
            else:
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

        

    def _parse_llm_route_payload(self, content: str) -> dict[str, Any]:
        """LLM이 반환한 JSON 라우팅 결과를 안전한 dict로 변환합니다."""
        raw = (content or "").strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.IGNORECASE | re.DOTALL).strip()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        if not isinstance(payload, dict):
            return {}
        slots = payload.get("slots") if isinstance(payload.get("slots"), dict) else {}
        try:
            confidence = float(payload.get("confidence", 0))
        except (TypeError, ValueError):
            confidence = 0.0
        return {
            "intent": str(payload.get("intent", "")).strip(),
            "confidence": max(0.0, min(confidence, 1.0)),
            "slots": slots,
        }

    def _route_payload(self, intent: str, confidence: float = 1.0, slots: dict[str, Any] | None = None) -> dict[str, Any]:
        """라우팅 결과를 Supervisor 공통 dict 형식으로 감쌉니다."""
        return {"intent": intent, "confidence": confidence, "slots": slots or {}}

    def _route_intent_payload_with_llm(self, text: str, history: list[Any] = None) -> dict[str, Any]:
        """룰베이스 우선 구조를 유지하며 LLM fallback 결과를 JSON dict로 반환합니다."""
        rule_intent = self._route_intent(text)
        if rule_intent != "general":
            return self._route_payload(rule_intent)

        if not app_settings.OPENAI_API_KEY or OpenAI is None:
            return self._route_payload(self._route_intent(text), confidence=0.0)

        try:
            from langchain_openai import ChatOpenAI
            from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

            llm = ChatOpenAI(model=app_settings.OPENAI_MODEL, api_key=app_settings.OPENAI_API_KEY, temperature=0.0)

            system_prompt = """
You are the Supervisor intent router for the Bobbeori food chatbot.
Return exactly one JSON object. Do not include markdown, code fences, or explanations.

Allowed intents:
- receipt.guide
- recipe.recommend
- recipe.pairing
- recipe.search
- ingredient.guide
- inventory.expiring
- inventory.list
- shopping.current
- shopping.history
- shopping.compare
- shopping.create
- shopping.purchase
- shopping.delete_item
- shopping.check_item
- alarm.notification
- alarm.calendar
- general

Response schema:
{
  "intent": "one allowed intent",
  "confidence": 0.0,
  "slots": {
    "ingredient": null,
    "keyword": null,
    "date": null,
    "quantity": null,
    "storage": null
  }
}

Rules:
- recipe.recommend: menu recommendation, fridge ingredient cooking ideas, leftover ingredient use.
- recipe.search: specific recipe, cooking method, cooking time, air fryer time.
- recipe.pairing: side dish, pairing food, food that goes well with another dish.
- ingredient.guide: storage, washing, prep, nutrition, calories, seasonal food.
- inventory.expiring: expiry, use-by date, expiring ingredients.
- inventory.list: list current fridge ingredients.
- receipt.guide: receipt OCR or purchase upload guide.
- shopping.*: shopping list lookup, history, price comparison, creation, purchase, deletion, or checking.
- alarm.notification: notification lookup or management.
- alarm.calendar: calendar schedule lookup or management.
- general: anything else.
- Use previous_intent metadata from the latest assistant message when the current message is a short follow-up.

Safety:
- For DB-changing requests such as add, consume, delete, update ingredients, return general. Rule-based routing already handles them before this LLM fallback.
- If uncertain, lower confidence below 0.5.
"""

            messages = [SystemMessage(content=system_prompt)]

            if history:
                for msg in history[-4:]:
                    if msg.role == 'user':
                        messages.append(HumanMessage(content=msg.text))
                    elif msg.role == 'bot':
                        previous_intent = getattr(msg, "intent", None)
                        content = f"{msg.text}\n[previous_intent: {previous_intent}]" if previous_intent else msg.text
                        messages.append(AIMessage(content=content))

            messages.append(HumanMessage(content=text))

            response = llm.invoke(messages)
            payload = self._parse_llm_route_payload(response.content)
            intent = payload.get("intent", "")
            valid_intents = ["receipt.guide", "recipe.recommend", "recipe.pairing", "recipe.search", "ingredient.guide", "inventory.expiring", "inventory.list", "shopping.current", "shopping.history", "shopping.compare", "shopping.create", "shopping.purchase", "shopping.delete_item", "shopping.check_item", "alarm.notification", "alarm.calendar", "general"]

            if intent in valid_intents and payload.get("confidence", 0) >= 0.5:
                return payload
            return self._route_payload(self._route_intent(text), confidence=payload.get("confidence", 0), slots=payload.get("slots", {}))
        except Exception:
            return self._route_payload(self._route_intent(text), confidence=0.0)

    def _route_intent_with_llm(self, text: str, history: list[Any] = None) -> str:
        """기존 호출부 호환을 위해 LLM 라우팅 dict에서 intent만 반환합니다."""
        return self._route_intent_payload_with_llm(text, history).get("intent", "general")

    def _route_intent(self, text: str) -> str:
        """키워드 기반으로 1차 챗봇 intent를 분류합니다."""
        normalized = text.replace(" ", "").lower()

        if any(word in normalized for word in ("영수증", "ocr", "구매내역")):
            return "receipt.guide"
            
        if _is_expiring_question(text):
            return "inventory.expiring"
        if _is_cooking_time_question(text):
            return "recipe.search"
        if any(word in normalized for word in ('이랑먹기좋은', '같이먹기좋은', '어울리는음식', '곁들일', '곁들이', '사이드메뉴', '반찬추천')):
            return "recipe.pairing"
            
        if "냉장고" in normalized and "재료" in normalized and "요리" in normalized:
            return "recipe.recommend"
        if any(word in normalized for word in ("추천", "뭐해먹", "뭐먹", "뭐하지", "뭘", "만들지", "만들요리", "만들어먹", "요리추천", "만들수", "만들수있는", "만들수있", "할수", "할수있는", "메뉴", "냉장고파먹", "쓸수", "쓸수있", "활용", "어디에쓸", "다른거", "딴거")):
            return "recipe.recommend"
        if any(word in normalized for word in ("레시피", "요리법", "요리")):
            return "recipe.search"
            
        if any(word in normalized for word in ('보관법', '보관방법', '보관', '손질', '세척', '씻', '신선', '확인', '가이드', '어떡', '어떻게하지', '먹다남은', '남은', '영양', '영양성분', '칼로리', '열량', '단백질', '탄수화물', '지방', '당류', '나트륨', '맛있게', '먹는법', '섭취', '제철')):
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
            # 섭취/먹는법 질문은 Guide Agent가 문장 전체를 식재료명으로 오해하지 않도록 식재료명만 넘깁니다.
            if any(word in normalized for word in ("맛있게", "먹는법", "먹는방법", "섭취", "활용법")):
                query = extracted
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

        if action == "lookup_seasonality":
            ingredient = data.get("ingredient") or {}
            seasonality = data.get("seasonality") or {}
            item_name = ingredient.get("name") or _extract_keyword(text) or "식재료"
            months = seasonality.get("months") or []
            if not months:
                return agent_result.get("message") or f"{item_name} 제철 정보는 아직 준비 중이에요.", sources
            month_text = ", ".join(f"{month}월" for month in months)
            return f"{item_name} 제철은 {month_text}이에요.", sources

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
        elif any(word in normalized for word in ("맛있게", "먹는법", "먹는방법", "섭취", "활용법")):
            guide_type = "intake"
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
            "intake": "섭취 팁",
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


    def _reply_recipe_pairing(self, text: str) -> str:
        """특정 음식과 함께 먹기 좋은 간단한 곁들임 메뉴를 안내합니다."""
        keyword = re.split(r"이랑|랑|와|과|하고|에", text, maxsplit=1)[0].strip()
        keyword = re.sub(r"^(남은|먹다남은)\s*", "", keyword) or "그 메뉴"
        pairings = {
            "김치볶음밥": ["계란국", "어묵국", "단무지", "오이무침", "군만두"],
            "파스타": ["마늘빵", "샐러드", "피클", "구운 채소"],
            "라면": ["김치", "단무지", "계란말이", "주먹밥"],
        }
        items = pairings.get(keyword.replace(" ", ""), ["맑은 국", "상큼한 무침", "피클류", "간단한 구이"])
        return f"{keyword}에는 " + ", ".join(items) + "처럼 맛을 정리해주는 메뉴가 잘 어울려요."


supervisor_service = ChatService()
