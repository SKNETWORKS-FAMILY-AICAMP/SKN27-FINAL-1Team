import json
import re
from typing import Any

# 챗봇 기본 응답 문구
LOGIN_REQUIRED_REPLY = "로그인이 필요한 질문이에요. 비회원 상태에서는 보관법이나 일반 레시피 검색을 이용할 수 있어요."
GENERAL_REPLY = "음식과 관련된 대화만 지원하고 있어요! 요리 레시피, 식재료 보관법, 냉장고 재료 관리 등을 물어봐주세요!"

# 확인/취소 액션 키워드
CONFIRM_PREFIX = "확인:"
CANCEL_WORDS = ("취소", "아니", "아니요", "아니다", "아니야", "취소할게", "안넣어", "넣지마", "추가하지마")

# 규칙 기반 라우터는 의도가 명확한 표현만 처리하고, 애매한 표현은 LLM에 맡깁니다.
_CONTEXT_INTENTS = {"ingredient.guide", "inventory.list", "inventory.expiring"}
_RECIPE_RECOMMEND_PHRASES = (
    "뭐해먹", "뭐먹", "만들어먹", "요리추천", "메뉴추천", "추천메뉴", "냉장고파먹",
)
_RECIPE_SEARCH_PHRASES = ("레시피", "요리법", "요리방법")
_GUIDE_PHRASES = (
    "보관법", "보관방법", "보관해", "어떻게보관", "보관어떻게", "손질법", "손질방법",
    "손질해", "어떻게손질", "세척법", "세척방법", "세척해", "씻는법", "어떻게씻", "식재료가이드",
    "신선도", "상했", "상한", "물러", "곰팡이",
    "영양", "영양성분", "칼로리", "열량", "단백질", "탄수화물", "지방",
    "당류", "나트륨", "제철",
)
_GUIDE_CATEGORY_WORDS = (
    "채소", "과일", "버섯", "육류", "수산물", "해산물", "곡류", "유제품", "가공식품", "발효식품", "조미료",
)
_GUIDE_LIST_PHRASES = ("뭐가있", "어떤재료", "무슨재료", "종류", "목록", "리스트", "분류")

# Guide Agent action을 내부 가이드 유형과 화면 표시 이름으로 매핑합니다.
_GUIDE_ACTION_TYPES = {
    "lookup_storage": ("storage", "보관법"),
    "lookup_prep": ("prep", "손질법"),
    "lookup_washing": ("washing", "세척법"),
    "lookup_freshness": ("freshness", "신선도 확인법"),
    "lookup_intake": ("intake", "섭취 팁"),
}
_GUIDE_TYPE_LABELS = dict(_GUIDE_ACTION_TYPES.values())

# LLM fallback이 반환할 수 있는 읽기 전용 intent입니다.
_LLM_ROUTE_INTENTS = (
    "receipt.guide", "recipe.recommend", "recipe.pairing", "recipe.search",
    "ingredient.guide", "inventory.expiring", "inventory.list",
    "shopping.current", "shopping.history", "shopping.compare", "alarm.notification", "alarm.calendar",
    "multi_agent", "general",
)
# LLM 라우팅 결과를 채택할 최소 신뢰도와 허용 슬롯입니다.
_LLM_ROUTE_CONFIDENCE = 0.5
_LLM_SLOT_KEYS = {"ingredient", "keyword", "date", "quantity", "storage", "use_inventory", "guide_type"}
# 복합 요청에서 순차 실행을 허용하는 읽기 전용 intent입니다.
_MULTI_AGENT_TASK_INTENTS = {
    "receipt.guide",
    "recipe.recommend",
    "recipe.pairing",
    "recipe.search",
    "ingredient.guide",
    "inventory.expiring",
    "inventory.list",
    "shopping.current",
    "shopping.history",
    "shopping.compare",
}

# LLM fallback은 아래 허용 intent만 JSON으로 반환하도록 제한합니다.
_LLM_ROUTE_SYSTEM_PROMPT = """
You are the Supervisor intent router for the Bobbeori food chatbot.
Return exactly one JSON object. Do not include markdown, code fences, or explanations.

Allowed intents:
{allowed_intents}

Response schema:
{{
  "intent": "one allowed intent",
  "confidence": 0.0,
  "slots": {{
    "ingredient": null,
    "keyword": null,
    "date": null,
    "quantity": null,
    "storage": null
  }},
  "tasks": []
}}

Rules:
- recipe.recommend: menu recommendation, fridge ingredient cooking ideas, leftover ingredient use.
- recipe.search: specific recipe, cooking method, cooking time, air fryer time.
- recipe.pairing: side dish, pairing food, food that goes well with another dish.
- ingredient.guide: ingredient overview, storage, washing, prep, freshness, nutrition, calories, seasonal food, or ingredient category lists.
- inventory.expiring: expiry, use-by date, expiring ingredients.
- inventory.list: list current fridge ingredients.
- receipt.guide: receipt OCR or purchase upload guide.
- shopping.current/history/compare: shopping list lookup, history, or price comparison.
- alarm.notification: notification lookup or management.
- alarm.calendar: calendar schedule lookup or management.
- multi_agent: a request that needs two or more read-only intents. Put each task in tasks as {{"intent": "...", "text": "..."}}.
- general: anything else.
- Use previous_intent metadata from the latest assistant message when the current message is a short follow-up.

Safety:
- For DB-changing requests such as add, consume, delete, update ingredients, return general. Rule-based routing already handles them before this LLM fallback.
- If uncertain, lower confidence below 0.5.
""".format(allowed_intents="\n".join(f"- {intent}" for intent in _LLM_ROUTE_INTENTS))

# 알람 확인 요청 중 Inventory Agent가 소유한 액션입니다.
_INVENTORY_CONFIRM_ACTIONS = {
    "consume_ingredient",
    "add_ingredient",
    "add_ingredient_unchecked",
    "add_ingredients",
    "delete_ingredient",
}

# Supervisor가 직접 제공하는 최소 곁들임 추천 목록입니다.
_RECIPE_PAIRINGS = {
    "김치볶음밥": ["계란국", "어묵국", "단무지", "오이무침", "군만두"],
    "파스타": ["마늘빵", "샐러드", "피클", "구운 채소"],
    "라면": ["김치", "단무지", "계란말이", "주먹밥"],
}

def _normalize_text(text: str) -> str:
    """사용자 문장을 간단 비교할 수 있도록 정리합니다."""
    return text.replace(" ", "").lower()


def _is_receipt_query(text: str) -> bool:
    """영수증 또는 OCR 사용 방법을 묻는 요청인지 확인합니다."""
    normalized = _normalize_text(text)
    return any(word in normalized for word in ("영수증", "ocr", "구매내역"))


def _is_alarm_notification_query(text: str) -> bool:
    """캘린더 일정이 아닌 알림 관리 요청인지 확인합니다."""
    normalized = _normalize_text(text)
    notification_words = ("알림", "알람", "리마인더", "디바이스", "푸시토큰", "읽음", "읽었")
    return any(word in normalized for word in notification_words) and not _is_alarm_calendar_query(text)


def _is_alarm_calendar_query(text: str) -> bool:
    """캘린더 일정 관리 요청인지 확인합니다."""
    normalized = _normalize_text(text)
    return any(word in normalized for word in ("일정", "캘린더"))


def _is_shopping_price_query(text: str) -> bool:
    """상품 가격 또는 최저가를 묻는 요청인지 확인합니다."""
    normalized = _normalize_text(text)
    return any(word in normalized for word in ("가격", "얼마", "최저가", "싼곳", "싼데", "저렴한곳", "저렴한데"))


def _is_recipe_pairing_query(text: str) -> bool:
    """특정 음식과 함께 먹을 메뉴를 묻는 요청인지 확인합니다."""
    normalized = _normalize_text(text)
    phrases = ("이랑먹기좋은", "같이먹기좋은", "어울리는음식", "곁들일", "곁들이", "사이드메뉴", "반찬추천")
    return any(phrase in normalized for phrase in phrases)


def _is_recipe_recommend_query(text: str) -> bool:
    """메뉴 또는 보유 재료 활용 추천 요청인지 확인합니다."""
    normalized = _normalize_text(text)
    inventory_context = ("냉장고", "보유재료", "보유식재료", "내재료", "내식재료")
    recipe_goal = ("레시피", "요리", "메뉴", "음식")
    return (
        any(word in normalized for word in inventory_context)
        and any(word in normalized for word in recipe_goal)
    ) or any(phrase in normalized for phrase in _RECIPE_RECOMMEND_PHRASES)


def _is_recipe_search_query(text: str) -> bool:
    """특정 레시피나 요리법 검색 요청인지 확인합니다."""
    normalized = _normalize_text(text)
    return any(phrase in normalized for phrase in _RECIPE_SEARCH_PHRASES)

def _is_guide_query(text: str) -> bool:
    """명시적인 식재료 가이드 또는 분류 목록 질문인지 확인합니다."""
    normalized = _normalize_text(text)
    if any(phrase in normalized for phrase in _RECIPE_RECOMMEND_PHRASES):
        return False
    if any(phrase in normalized for phrase in _GUIDE_PHRASES):
        return True
    if any(word in normalized for word in ("냉장고", "냉동고", "냉장실", "냉동실")):
        return False
    return (
        any(category in normalized for category in _GUIDE_CATEGORY_WORDS)
        and any(phrase in normalized for phrase in _GUIDE_LIST_PHRASES)
    )

def _apply_josa(word: str, josa_type: str) -> str:
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

def _is_login_status_question(text: str) -> bool:
    """사용자가 현재 로그인 상태를 묻는 문장인지 확인합니다."""
    normalized = text.replace(" ", "").lower()
    return "로그인" in normalized and any(word in normalized for word in ("되어", "됐", "되있", "상태", "했", "했어"))

def _is_cooking_time_question(text: str) -> bool:
    """조리 시간이나 온도를 묻는 질문인지 확인합니다."""
    normalized = text.replace(" ", "").lower()
    return any(word in normalized for word in ("에어프라이", "몇분", "몇도", "온도", "조리시간", "굽는시간", "익히는시간"))

def _is_expiring_question(text: str) -> bool:
    """소비기한 임박 재료를 묻는 질문인지 먼저 확인합니다."""
    normalized = text.replace(" ", "").lower()
    return any(word in normalized for word in ("상하는", "임박", "소비기한", "유통기한", "기한", "적게남", "남은거", "먼저먹", "먹어야", "다되어", "다돼", "끝나", "d-day", "디데이"))

def _build_read_tasks(text: str) -> list[dict[str, str]]:
    """복합 조회 요청을 기존 Agent가 처리할 순차 작업 목록으로 분해합니다."""
    intents = []
    normalized = _normalize_text(text)

    if any(phrase in normalized for phrase in _GUIDE_PHRASES):
        intents.append("ingredient.guide")
    if _is_expiring_question(text):
        intents.append("inventory.expiring")
    if _is_shopping_price_query(text):
        intents.append("shopping.compare")
    if _is_recipe_pairing_query(text):
        intents.append("recipe.pairing")
    elif _is_cooking_time_question(text):
        intents.append("recipe.search")
    elif _is_recipe_recommend_query(text):
        intents.append("recipe.recommend")
    elif _is_recipe_search_query(text):
        intents.append("recipe.search")

    tasks = [{"intent": intent, "text": text} for intent in dict.fromkeys(intents)]
    if "ingredient.guide" in intents and "shopping.compare" in intents:
        price_text = re.sub(
            r"^.+?(?:보관법|보관방법|손질법|손질방법|세척법|세척방법|영양성분|칼로리|제철)"
            r"(?:이랑|랑|과|와|그리고)?s*",
            "",
            text,
        ).strip()
        if price_text.startswith(("가격", "최저가", "얼마")):
            ingredient = text.split(maxsplit=1)[0]
            price_text = f"{ingredient} {price_text}"
        for task in tasks:
            if task["intent"] == "shopping.compare":
                task["text"] = price_text or text
    return tasks


def _format_guide_tip(tip: str) -> str:
    sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?。])\s+", tip) if sentence.strip()]
    if len(sentences) <= 1:
        sentences = [sentence.strip() for sentence in re.split(r"[;；]\s*", tip) if sentence.strip()]
    if len(sentences) <= 1:
        return sentences[0] if sentences else tip.strip()
    return "\n".join(f"{index + 1}. {sentence}" for index, sentence in enumerate(sentences[:3]))

def _format_guide_message(agent_result: dict[str, Any]) -> str:
    """Guide Agent의 action과 data를 챗봇에서 읽기 좋은 문장으로 변환합니다."""
    message = agent_result.get("message") or "가이드 정보를 찾지 못했어요."
    if agent_result.get("status") != "success":
        return message

    action = agent_result.get("action") or ""
    data = agent_result.get("data") or {}
    ingredient = data.get("ingredient") or {}
    item_name = ingredient.get("name") or ingredient.get("representative_name") or "식재료"

    if action == "list_seasonal_ingredients":
        month = data.get("month")
        names = [item.get("name") for item in data.get("items", []) if item.get("name")]
        if month and names:
            suffix = " 등" if len(names) > 10 else ""
            return f"{month}월 제철 식재료는 {', '.join(names[:10])}{suffix}이에요."

    if action == "lookup_nutrition":
        nutrition = data.get("nutrition") or {}
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
        if lines:
            return f"{item_name} 영양성분이에요.\n" + "\n".join(lines[:7])

    action_type = _GUIDE_ACTION_TYPES.get(action)
    if not action_type and data.get("guide_type"):
        guide_type = data["guide_type"]
        action_type = (guide_type, _GUIDE_TYPE_LABELS.get(guide_type, "가이드"))
    if action_type:
        guide_type, label = action_type
        guide = (data.get("guides") or {}).get(guide_type) or {}
        tip = guide.get("content")
        if tip:
            return f"{item_name} {label}이에요.\n{_format_guide_tip(tip)}"

    return message


def _guide_result_to_state(agent_result: dict[str, Any]) -> dict[str, Any]:
    """Guide Agent 공통 응답을 Supervisor GraphState 형식으로 변환합니다."""
    status = agent_result.get("status") or "error"
    ui = agent_result.get("ui") or {}
    actions = []
    for action in ui.get("actions") or []:
        label = action.get("label")
        data = dict(action.get("data") or {})
        message = data.get("message") or action.get("value")
        if message:
            data["message"] = message
        for key in ("intent", "guide_type", "original_query"):
            if action.get(key) is not None:
                data[key] = action[key]
        url = action.get("url") or ""
        if label and (message or url):
            actions.append({"label": label, "url": url, "data": data})

    sources = [
        {"title": source.get("title") or "출처", "url": source.get("url") or ""}
        for source in ui.get("sources") or []
        if isinstance(source, dict)
    ]
    if not agent_result.get("ok") or status == "error":
        response_text = "가이드 정보를 조회하는 중 문제가 생겼어요. 잠시 후 다시 시도해주세요."
        actions = []
    else:
        response_text = _format_guide_message(agent_result)

    return {
        "response_text": response_text,
        "actions": actions,
        "sources": sources,
        "slots": {
            "guide_status": status,
            "guide_action": agent_result.get("action"),
        },
    }

def _message_value(message: Any, key: str, default: Any = None) -> Any:
    """딕셔너리와 메시지 객체에서 같은 방식으로 값을 읽습니다."""
    return message.get(key, default) if isinstance(message, dict) else getattr(message, key, default)


def _build_llm_route_history(history: list[Any] | None) -> list[dict[str, Any]]:
    """최근 대화를 LLM 라우팅에 전달할 공통 JSON 문맥으로 정리합니다."""
    route_history = []
    for message in (history or [])[-4:]:
        item = {
            "role": _message_value(message, "role", ""),
            "text": _message_value(message, "text", ""),
        }
        if item["role"] == "bot":
            item.update({
                "intent": _message_value(message, "intent"),
                "slots": _message_value(message, "slots", {}) or {},
                "pending_action": _message_value(message, "pending_action"),
            })
        route_history.append(item)
    return route_history


def _latest_bot_intent(history) -> str | None:
    """이전 봇 응답에 저장된 마지막 intent를 반환합니다."""
    for message in reversed(history or []):
        intent = _message_value(message, "intent")
        if _message_value(message, "role", "") == "bot" and intent:
            return intent
    return None


def _latest_bot_slots(history) -> dict:
    """이전 봇 응답에 저장된 마지막 슬롯을 반환합니다."""
    for message in reversed(history or []):
        slots = _message_value(message, "slots")
        if _message_value(message, "role", "") == "bot" and isinstance(slots, dict):
            return slots
    return {}


def _latest_bot_pending_action(history) -> dict | None:
    """이전 봇 응답에 저장된 실행 대기 작업을 반환합니다."""
    for message in reversed(history or []):
        pending = _message_value(message, "pending_action")
        if _message_value(message, "role", "") == "bot" and isinstance(pending, dict):
            return pending
    return None


def _rewrite_context_switch(text: str, has_pending: bool = False) -> str:
    """기존 작업을 번복한 문장에서 새로 실행할 명령만 남깁니다."""
    stripped = text.strip()
    if has_pending:
        switch_match = re.search(r"(?:말고|대신)\s*(.+)$", stripped)
        if switch_match:
            return switch_match.group(1).strip()
    replacement = re.sub(r"^(?:아니다|아니야|아니|잠깐|취소하고)(?:\s+|,\s*)", "", stripped).strip()
    return replacement or stripped


def _is_context_follow_up(text: str) -> bool:
    """직전 응답 없이는 의미가 부족한 짧은 후속 질문인지 확인합니다."""
    normalized = _normalize_text(text)
    return (
        bool(re.match(r"^외\d+개", normalized))
        or bool(re.fullmatch(r"(?:냉장|냉동|실온)(?:은|는|으로|에)?", normalized.rstrip("?")))
        or any(word in normalized for word in ("나머지", "그중", "그거", "그걸", "그건", "이거", "이걸", "이건", "첫번째", "두번째", "더알려", "더보여", "전부", "다말해", "다보여"))
    )


def _route_result(
    intent: str,
    confidence: float = 1.0,
    slots: dict | None = None,
    tasks: list[dict[str, str]] | None = None,
) -> dict:
    """라우터 결과를 공통 dict 형식으로 반환합니다."""
    payload = {"intent": intent, "confidence": confidence, "slots": slots or {}, "tasks": tasks or []}
    return {"intent": intent, "intent_payload": payload, "slots": payload["slots"], "tasks": payload["tasks"]}


def _format_calendar_events(data: dict) -> str | None:
    """캘린더 조회 결과를 챗봇 말풍선에 보여줄 문장으로 바꿉니다."""
    events = data.get("events") if isinstance(data, dict) else None
    if events is None:
        return None
    if not events:
        return "조회한 기간에 등록된 일정이 없어요."
    lines = ["등록된 일정이에요."]
    for event in events[:5]:
        date_key = event.get("dateKey") or "날짜 미정"
        title = event.get("title") or "제목 없는 일정"
        lines.append(f"{date_key} - {title}")
    if len(events) > 5:
        lines.append(f"외 {len(events) - 5}개가 더 있어요.")
    return "\n".join(lines)


def _extract_pending_action(final_state: dict[str, Any], actions: list[dict[str, Any]]) -> dict[str, Any] | None:
    """에이전트 결과나 확인 버튼에서 실행 대기 작업을 추출합니다."""
    pending = final_state.get("pending_action")
    if isinstance(pending, dict):
        return pending
    if pending:
        return {"action": str(pending)}
    for action in actions:
        command = (action.get("data") or {}).get("message")
        if isinstance(command, str) and command.startswith("확인:"):
            return {"command": command}
    return None


def _parse_llm_route_payload(content: str, fallback_text: str = "") -> dict[str, Any]:
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
    slots = {key: value for key, value in slots.items() if key in _LLM_SLOT_KEYS and value is not None}
    try:
        confidence = float(payload.get("confidence", 0))
    except (TypeError, ValueError):
        confidence = 0.0
    tasks = []
    for task in payload.get("tasks") or []:
        if not isinstance(task, dict):
            continue
        intent = str(task.get("intent", "")).strip()
        if intent not in _MULTI_AGENT_TASK_INTENTS:
            continue
        task_text = str(task.get("text", "")).strip() or fallback_text
        if task_text:
            tasks.append({"intent": intent, "text": task_text})
    intent = str(payload.get("intent", "")).strip()
    if intent not in _LLM_ROUTE_INTENTS:
        intent = "general"
    return {
        "intent": intent,
        "confidence": max(0.0, min(confidence, 1.0)),
        "slots": slots,
        "tasks": tasks,
    }


def _route_payload(
    intent: str,
    confidence: float = 1.0,
    slots: dict[str, Any] | None = None,
    tasks: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """LLM 라우팅 결과를 Supervisor 공통 dict 형식으로 반환합니다."""
    return {"intent": intent, "confidence": confidence, "slots": slots or {}, "tasks": tasks or []}


def _rewrite_guide_query(text: str) -> str:
    """정정 표현이 포함된 가이드 질문에서 마지막 식재료 질문만 남깁니다."""
    return re.sub(r"^.+?(?:말고|대신)\s+", "", text).strip()


def _strip_shopping_compare_suffix(text: str) -> str:
    """가격 비교 후속 표현을 제거하고 실제 상품명만 반환합니다."""
    return re.sub(
        r"\s*더\s*(?:싼|저렴한)\s*(?:곳|데)(?:은|는)?(?:\s*없어(?:요)?)?\s*\??$",
        "",
        text,
    ).strip()

def _auth_status_response(user_id: int | None) -> dict[str, Any]:
    """현재 로그인 상태를 챗봇 공통 응답으로 반환합니다."""
    reply = "현재 로그인된 상태예요." if user_id else "현재 비로그인 상태예요. 보관법이나 일반 레시피 검색은 이용할 수 있어요."
    return {
        "intent": "auth.status",
        "reply": reply,
        "actions": [],
        "sources": [],
        "slots": {},
        "pending_action": None,
    }


def _build_chat_state(
    *,
    db: Any,
    user_id: int | None,
    text: str,
    history: list[Any] | None,
    user_settings: Any,
    service: Any,
) -> dict[str, Any]:
    """LangGraph 실행에 필요한 초기 Supervisor 상태를 구성합니다."""
    return {
        "user_id": user_id,
        "text": text,
        "history": history or [],
        "settings_obj": user_settings,
        "db": db,
        "service": service,
        "intent": None,
        "intent_payload": {},
        "slots": {},
        "tasks": [],
        "pending_action": None,
        "keyword": None,
        "response_text": None,
        "actions": [],
        "sources": [],
    }


def _chat_response_from_state(final_state: dict[str, Any]) -> dict[str, Any]:
    """LangGraph 최종 상태를 채팅 API 응답 형식으로 변환합니다."""
    actions = final_state.get("actions") or []
    return {
        "intent": final_state.get("intent", "general"),
        "reply": final_state.get("response_text", ""),
        "actions": actions,
        "sources": final_state.get("sources") or [],
        "slots": final_state.get("slots") or {},
        "pending_action": _extract_pending_action(final_state, actions),
    }


def _chat_error_response() -> dict[str, Any]:
    """Supervisor 실행 실패 시 사용할 공통 채팅 응답을 반환합니다."""
    return {
        "intent": "error",
        "reply": "요청을 처리하는 중 문제가 생겼어요. 잠시 후 다시 시도해주세요.",
        "actions": [],
        "sources": [],
        "slots": {},
        "pending_action": None,
    }


def _reply_recipe_pairing(text: str) -> str:
    """특정 음식과 함께 먹기 좋은 간단한 곁들임 메뉴를 안내합니다."""
    keyword = re.split(r"이랑|랑|와|과|하고|에", text, maxsplit=1)[0].strip()
    keyword = re.sub(r"^(남은|먹다남은)\s*", "", keyword) or "그 메뉴"
    items = _RECIPE_PAIRINGS.get(keyword.replace(" ", ""), ["맑은 국", "상큼한 무침", "피클류", "간단한 구이"])
    return f"{keyword}에는 " + ", ".join(items) + "처럼 맛을 정리해주는 메뉴가 잘 어울려요."


def _parse_alarm_request(text: str, intent: str) -> dict[str, Any]:
    """Supervisor 확인 문자열을 Alarm Agent 실행 인자로 변환합니다."""
    confirmed = intent == "action.confirm"
    action = None
    payload = None
    alarm_intent = None

    if confirmed:
        parts = text.split(":", 2)
        if len(parts) >= 2:
            action = parts[1]
            if action in _INVENTORY_CONFIRM_ACTIONS:
                pass
            elif action == "alarm" and len(parts) == 3:
                alarm_action = json.loads(parts[2])
                alarm_intent = alarm_action.get("intent")
                action = alarm_action.get("action")
                payload = alarm_action.get("payload") or {}
            elif len(parts) >= 3 and action == "add_calendar_event":
                legacy_parts = text.split(":")
                action = "create_event"
                alarm_intent = "calendar.create"
                payload = {"title": legacy_parts[2], "date_text": ":".join(legacy_parts[3:])}
            elif len(parts) >= 3 and action == "delete_event":
                alarm_intent = "calendar.delete"
                payload = {"event_key": parts[2]}
            elif action == "sync_daily_events":
                alarm_intent = "calendar.sync_daily"
                payload = {}
    elif intent == "alarm.calendar" and any(word in text for word in ("조회", "있어", "확인", "알려")):
        alarm_intent = "calendar.list"

    return {
        "confirmed": confirmed,
        "action": action,
        "payload": payload,
        "intent": alarm_intent,
    }


def _alarm_result_to_state(agent_result: dict[str, Any]) -> dict[str, Any]:
    """Alarm Agent 공통 응답을 Supervisor GraphState 형식으로 변환합니다."""
    response_text = _format_calendar_events(agent_result.get("data", {})) if agent_result.get("intent") == "calendar.list" else None
    response_text = response_text or agent_result.get("message", "요청을 처리했습니다.")
    actions = []

    for action in (agent_result.get("ui") or {}).get("actions") or []:
        label = action.get("label", "")
        value = action.get("value", {})
        if isinstance(value, dict):
            if value.get("action") == "cancel":
                message = "취소"
            else:
                payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
                message = f"확인:alarm:{payload}"
        else:
            message = str(value)
        actions.append({"label": label, "data": {"message": message}})

    result = {"response_text": response_text}
    if actions:
        result["actions"] = actions
    return result

def _merge_agent_results(*results: dict[str, Any]) -> dict[str, Any]:
    """여러 Agent 응답을 중복 없이 하나의 GraphState 응답으로 합칩니다."""
    response_text = "\n\n".join(
        result.get("response_text", "").strip()
        for result in results
        if result.get("response_text", "").strip()
    )
    actions = list({
        json.dumps(action, ensure_ascii=False, sort_keys=True, default=str): action
        for result in results
        for action in result.get("actions") or []
    }.values())
    sources = list({
        json.dumps(source, ensure_ascii=False, sort_keys=True, default=str): source
        for result in results
        for source in result.get("sources") or []
    }.values())
    slots = {}
    for result in results:
        slots.update(result.get("slots") or {})

    merged = {"response_text": response_text}
    if actions:
        merged["actions"] = actions
    if sources:
        merged["sources"] = sources
    if slots:
        merged["slots"] = slots
    return merged
