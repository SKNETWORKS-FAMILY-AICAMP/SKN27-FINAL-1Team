import json
import re

from langgraph.graph import END, StateGraph

from ai.agents.inventory_agent.inventory_utils import (
    _pending_add_many_from_history,
    _is_quantity_only_list,
    _extract_storage,
    _pending_add_storage_from_history,
    _pending_add_from_history,
    _pending_consume_from_history,
    _extract_add_items,
    _extract_quantity,
    ADD_WORDS,
    DELETE_WORDS,
    CONSUME_WORDS,
    INVENTORY_LIST_WORDS,
)

from app.backend.schemas.chat_state import GraphState
from ai.agents.recipe_agent import run_recipe_agent

from ai.agents.supervisor_agent.supervisor_utils import (
    LOGIN_REQUIRED_REPLY, GENERAL_REPLY,
    CONFIRM_PREFIX, CANCEL_WORDS,
    _is_cooking_time_question,
    _is_expiring_question,
    _normalize_text,
)
from ai.agents.shopping_agent.shopping_utils import SHOPPING_CONFIRM_ACTIONS, analyze_shopping_intent

_CONTEXT_INTENTS = {"ingredient.guide", "inventory.list", "inventory.expiring"}

# 읽기 질문은 한 곳에서 분류할 수 있도록 의도별 대표 표현을 모아둡니다.
_RECIPE_RECOMMEND_WORDS = ("추천", "뭐해먹", "뭐먹", "뭐하지", "뭘", "만들지", "만들요리", "만들어먹", "요리추천", "만들수", "만들수있는", "만들수있", "할수", "할수있는", "메뉴", "냉장고파먹", "쓸수", "쓸수있", "활용", "어디에쓸", "다른거", "딴거")
_RECIPE_SEARCH_WORDS = ("레시피", "요리법", "요리")
_GUIDE_WORDS = ("보관법", "보관방법", "보관", "손질", "세척", "씻", "신선", "확인", "가이드", "어떡", "어떻게하지", "먹다남은", "남은", "영양", "영양성분", "칼로리", "열량", "단백질", "탄수화물", "지방", "당류", "나트륨", "맛있게", "먹는법", "섭취", "제철")


def _latest_bot_intent(history) -> str | None:
    """이전 봇 응답에 저장된 마지막 intent를 반환합니다."""
    for message in reversed(history or []):
        role = message.get("role") if isinstance(message, dict) else getattr(message, "role", "")
        intent = message.get("intent") if isinstance(message, dict) else getattr(message, "intent", None)
        if role == "bot" and intent:
            return intent
    return None


def _latest_bot_slots(history) -> dict:
    """이전 봇 응답에 저장된 마지막 슬롯을 반환합니다."""
    for message in reversed(history or []):
        role = message.get("role") if isinstance(message, dict) else getattr(message, "role", "")
        slots = message.get("slots") if isinstance(message, dict) else getattr(message, "slots", None)
        if role == "bot" and isinstance(slots, dict):
            return slots
    return {}


def _latest_bot_pending_action(history) -> dict | None:
    """이전 봇 응답에 저장된 실행 대기 작업을 반환합니다."""
    for message in reversed(history or []):
        role = message.get("role") if isinstance(message, dict) else getattr(message, "role", "")
        pending = message.get("pending_action") if isinstance(message, dict) else getattr(message, "pending_action", None)
        if role == "bot" and isinstance(pending, dict):
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

def _route_result(intent: str, confidence: float = 1.0, slots: dict | None = None) -> dict:
    """라우터 결과를 공통 dict 형식으로 반환합니다."""
    payload = {"intent": intent, "confidence": confidence, "slots": slots or {}}
    return {"intent": intent, "intent_payload": payload, "slots": payload["slots"]}

def router_node(state: GraphState) -> dict:
    """사용자 메시지를 분석하여 LangGraph 분기용 intent를 반환합니다."""
    original_text = state["text"]
    history = state.get("history", [])
    has_pending = bool(
        _pending_add_many_from_history(history)
        or _pending_add_storage_from_history(history)
        or _pending_add_from_history(history)
        or _pending_consume_from_history(history)
        or _latest_bot_pending_action(history)
    )
    text = _rewrite_context_switch(original_text, has_pending)

    # 번복 뒤 새 명령은 오래된 pending 문맥을 버리고 처음부터 다시 분류합니다.
    if text != original_text:
        result = router_node({**state, "text": text, "history": []})
        result.update({"text": text, "history": []})
        return result

    normalized = _normalize_text(text)

    if normalized.startswith(CONFIRM_PREFIX):
        return _route_result("action.confirm")
    if normalized in CANCEL_WORDS:
        return _route_result("action.cancel")

    if _pending_add_many_from_history(history):
        if len(_extract_add_items(text)) > 1:
            return _route_result("inventory.pending_add_many")
        if _is_quantity_only_list(text):
            return _route_result("inventory.pending_add_many_retry")
    if _pending_add_storage_from_history(history) and _extract_storage(text):
        return _route_result("inventory.pending_add_storage")
    if _pending_add_from_history(history) and (_extract_quantity(text) or _extract_storage(text)):
        return _route_result("inventory.pending_add")
    if _pending_consume_from_history(history) and _extract_quantity(text):
        return _route_result("inventory.pending_consume")

    # 영수증/OCR 요청은 "등록" 단어가 있어도 냉장고 재료 추가로 보내지 않습니다.
    if any(word in normalized for word in ("영수증", "ocr", "구매내역")):
        return _route_result("receipt.guide")

    # 일정/알림 요청은 삭제 문장이더라도 냉장고 삭제로 보내지 않습니다.
    if any(word in normalized for word in ("알림", "알람", "리마인더", "디바이스", "푸시토큰", "읽음", "읽었")) and not any(word in normalized for word in ("일정", "캘린더")):
        return _route_result("alarm.notification")
    if any(word in normalized for word in ("일정", "캘린더")):
        return _route_result("alarm.calendar")
    # "장본거" 표현은 냉장고 보유 재료가 아니라 장보기 목록 조회로 처리합니다.
    if "장본" in normalized:
        return _route_result("shopping.current")

    shopping_intent = analyze_shopping_intent(text)
    if shopping_intent:
        return _route_result(shopping_intent)

    # 가격 질문은 장보기 문맥이 없어도 Shopping Agent의 가격 비교로 보냅니다.
    if any(word in normalized for word in ("가격", "얼마", "최저가", "싼곳", "싼데", "저렴한곳", "저렴한데")):
        return _route_result("shopping.compare")
    # 곁들임 추천은 레시피 검색이 아니라 짧은 메뉴 조합으로 응답합니다.
    if any(word in normalized for word in ('이랑먹기좋은', '같이먹기좋은', '어울리는음식', '곁들일', '곁들이', '사이드메뉴', '반찬추천')):
        return _route_result("recipe.pairing")

    if _is_expiring_question(text):
        return _route_result("inventory.expiring")
    if _is_cooking_time_question(text):
        return _route_result("recipe.search")

    # 생략된 후속 명령은 일반 냉장고 쓰기 규칙보다 직전 에이전트 문맥을 우선합니다.
    previous_intent = _latest_bot_intent(history)
    if previous_intent and _is_context_follow_up(text):
        previous_slots = _latest_bot_slots(history)
        if previous_intent.startswith("shopping."):
            return _route_result(analyze_shopping_intent(f"장보기 {text}") or previous_intent, slots=previous_slots)
        if previous_intent.startswith("alarm."):
            return _route_result(previous_intent, slots=previous_slots)
        if not any(word in normalized for word in (*DELETE_WORDS, *CONSUME_WORDS, *ADD_WORDS)) and (
            previous_intent.startswith("recipe.") or previous_intent in _CONTEXT_INTENTS
        ):
            return _route_result(previous_intent, slots=previous_slots)

    # 쓰기 작업은 LLM 의도 분류보다 먼저 고정해 할루시네이션을 막습니다.
    if any(word in normalized for word in DELETE_WORDS):
        return _route_result("inventory.delete")
    if any(word in normalized for word in CONSUME_WORDS):
        return _route_result("inventory.action")
    if any(word in normalized for word in ADD_WORDS):
        return _route_result("inventory.action")
    if any(word.replace(" ", "") in normalized for word in INVENTORY_LIST_WORDS):
        return _route_result("inventory.list")

    if "냉장고" in normalized and "재료" in normalized and "요리" in normalized:
        return _route_result("recipe.recommend")
    if any(word in normalized for word in _RECIPE_RECOMMEND_WORDS):
        return _route_result("recipe.recommend")
    if any(word in normalized for word in _RECIPE_SEARCH_WORDS):
        return _route_result("recipe.search")
    if any(word in normalized for word in _GUIDE_WORDS):
        return _route_result("ingredient.guide")

    if hasattr(state["service"], "_route_intent_payload_with_llm"):
        route_payload = state["service"]._route_intent_payload_with_llm(text, history)
    else:
        route_payload = {"intent": state["service"]._route_intent_with_llm(text, history), "slots": {}}
    return _route_result(
        route_payload.get("intent", "general"),
        route_payload.get("confidence", 0.0),
        route_payload.get("slots", {}),
    )


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


def inventory_agent_node(state: GraphState) -> dict:
    """재고 관리를 Inventory Agent로 위임합니다."""
    from ai.agents.inventory_agent.inventory_agent import run_inventory_agent
    
    intent = state.get("intent", "")
    if (intent.startswith("inventory.") or intent.startswith("action.")) and not state.get("user_id"):
        return {"response_text": LOGIN_REQUIRED_REPLY}
        
    return run_inventory_agent(
        intent=state.get("intent", ""),
        text=state["text"],
        history=state.get("history", []),
        db=state["db"],
        user_id=state.get("user_id")
    )


def guide_agent_node(state: GraphState) -> dict:
    """식재료 보관/손질 가이드 에이전트를 안내합니다."""
    # 정정 표현이 있으면 마지막에 선택한 식재료 질문만 가이드에 전달합니다.
    query = re.sub(r"^.+?(?:말고|대신)\s+", "", state["text"]).strip()
    reply, sources = state["service"]._reply_guide(query)
    return {"response_text": reply, "sources": sources}

def recipe_agent_node(state: GraphState) -> dict:
    """레시피 검색/추천 요청을 Recipe Agent로 위임합니다."""
    return run_recipe_agent(
        state["text"],
        db=state["db"],
        user_id=state.get("user_id"),
        history=state.get("history", []),
        settings_obj=state.get("settings_obj"),
        intent=state.get("intent"),
    )

def recipe_pairing_node(state: GraphState) -> dict:
    """특정 음식과 함께 먹기 좋은 메뉴를 안내합니다."""
    reply = state["service"]._reply_recipe_pairing(state["text"])
    return {"response_text": reply}

def receipt_guide_node(state: GraphState) -> dict:
    """영수증 OCR 화면 이동 액션을 안내합니다."""
    return {
        "response_text": "영수증은 파일 업로드가 필요해서 아래 버튼을 눌러 영수증 등록 화면으로 이동해주세요.",
        "actions": [{"label": "영수증 등록하러 가기", "url": "/receipt-ocr"}],
    }

def shopping_agent_node(state: GraphState) -> dict:
    """장보기 관리를 Shopping Agent로 위임합니다."""
    from ai.agents.shopping_agent.shopping_agent import run_shopping_agent

    if not state.get("user_id"):
        return {"response_text": LOGIN_REQUIRED_REPLY}

    # 가격 비교 후속 표현은 제거하고 실제 상품명만 Shopping Agent에 전달합니다.
    text = state["text"]
    compare_text = re.sub(r"\s*더\s*(?:싼|저렴한)\s*(?:곳|데)(?:은|는)?(?:\s*없어(?:요)?)?\s*\??$", "", text).strip()

    return run_shopping_agent(
        text=compare_text or text,
        intent=state.get("intent", ""),
        history=state.get("history", []),
        db=state["db"],
        user_id=state.get("user_id"),
    )

def alarm_agent_node(state: GraphState) -> dict:
    """캘린더 및 알림 관리를 Alarm Agent로 위임합니다."""
    from ai.agents.alarm_agent.alarm_agent import run as run_alarm_agent
    from ai.agents.alarm_agent import ALARM_AGENT_TOOLS
    
    intent = state.get("intent", "")
    text = state["text"]
    confirmed = (intent == "action.confirm")

    # 챗봇 프론트에서 들어온 '확인' 액션일 경우 파싱 (기존 동작 호환)
    action = None
    payload = None
    alarm_intent = None
    
    if confirmed:
        parts = text.split(":", 2)
        if len(parts) >= 2:
            action = parts[1]
            # 재고 관련 확인 액션은 Inventory Agent가 처리하므로 여기서 넘기지 않습니다.
            if action in ["consume_ingredient", "add_ingredient", "add_ingredient_unchecked", "add_ingredients", "delete_ingredient"]:
                pass
            elif action == "alarm" and len(parts) == 3:
                # Alarm Agent의 최신 action payload를 손실 없이 다시 전달합니다.
                alarm_action = json.loads(parts[2])
                alarm_intent = alarm_action.get("intent")
                action = alarm_action.get("action")
                payload = alarm_action.get("payload") or {}
            elif len(parts) >= 3 and action == "add_calendar_event":
                # 기존 레거시 포맷: 확인:add_calendar_event:제목:날짜
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
    elif intent == "alarm.notification":
        # 알림 세부 의도는 Alarm Agent의 최신 분석 로직에 맡깁니다.
        pass
    elif intent == "alarm.calendar" and any(word in text for word in ("조회", "있어", "확인", "알려")):
        # 등록된 일정 조회 문장이 등록 요청으로 오분류되지 않게 조회 의도를 고정합니다.
        alarm_intent = "calendar.list"
    # Alarm Agent 실행
    res = run_alarm_agent(
        text_or_intent=text, 
        payload=payload,
        intent=alarm_intent,
        action=action,
        confirmed=confirmed,
        tools=ALARM_AGENT_TOOLS,
        context={"user_id": state.get("user_id"), "db": state["db"]}
    )
    
    # Supervisor 규격(response_text, actions)으로 변환 (Adapter)
    response_text = _format_calendar_events(res.get("data", {})) if res.get("intent") == "calendar.list" else None
    response_text = response_text or res.get("message", "요청을 처리했습니다.")
    actions = []
    
    # Alarm Agent의 ui action을 프론트가 보낼 수 있는 message 문자열로 보존합니다.
    ui = res.get("ui", {})
    if ui and "actions" in ui:
        for a in ui["actions"]:
            label = a.get("label", "")
            val = a.get("value", {})
            if isinstance(val, dict):
                if val.get("action") == "cancel":
                    actions.append({"label": label, "data": {"message": "취소"}})
                else:
                    message = json.dumps(val, ensure_ascii=False, separators=(",", ":"))
                    actions.append({"label": label, "data": {"message": f"확인:alarm:{message}"}})
            else:
                actions.append({"label": label, "data": {"message": str(val)}})

    result = {"response_text": response_text}
    if actions:
        result["actions"] = actions
    return result

def general_node(state: GraphState) -> dict:
    """지원 범위 밖 질문에는 고정 안내문만 반환합니다."""
    return {"response_text": GENERAL_REPLY}

def route_intent(state: GraphState) -> str:
    """intent 값을 LangGraph 노드 이름으로 변환합니다."""
    intent = state.get("intent") or "general"
    if intent.startswith("alarm."):
        return "alarm_agent_node"
    if intent.startswith("shopping."):
        return "shopping_agent_node"
    if intent.startswith("inventory.") or intent.startswith("action."):
        if intent == "action.confirm":
            parts = state["text"].split(":")
            if len(parts) >= 2 and parts[1] in SHOPPING_CONFIRM_ACTIONS:
                return "shopping_agent_node"
            if len(parts) >= 2 and parts[1] not in ["consume_ingredient", "add_ingredient", "add_ingredient_unchecked", "add_ingredients", "delete_ingredient"]:
                return "alarm_agent_node"
        return "inventory_agent_node"
    routes = {
        "ingredient.guide": "guide_agent_node",
        "recipe.recommend": "recipe_agent_node",
        "recipe.search": "recipe_agent_node",
        "recipe.pairing": "recipe_pairing_node",
        "receipt.guide": "receipt_guide_node",
    }
    return routes.get(intent, "general_node")

workflow = StateGraph(GraphState)
workflow.add_node("router", router_node)
workflow.add_node("inventory_agent_node", inventory_agent_node)
workflow.add_node("alarm_agent_node", alarm_agent_node)
workflow.add_node("shopping_agent_node", shopping_agent_node)
workflow.add_node("guide_agent_node", guide_agent_node)
workflow.add_node("recipe_agent_node", recipe_agent_node)
workflow.add_node("recipe_pairing_node", recipe_pairing_node)
workflow.add_node("receipt_guide_node", receipt_guide_node)
workflow.add_node("general_node", general_node)

workflow.set_entry_point("router")
workflow.add_conditional_edges("router", route_intent)
for node_name in (
    "inventory_agent_node",
    "alarm_agent_node",
    "shopping_agent_node",
    "guide_agent_node",
    "recipe_agent_node",
    "recipe_pairing_node",
    "receipt_guide_node",
    "general_node",
):
    workflow.add_edge(node_name, END)

supervisor_agent = workflow.compile()
