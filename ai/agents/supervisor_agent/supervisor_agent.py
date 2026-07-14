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
    EXPIRING_WORDS
)

from app.backend.schemas.chat_state import GraphState
from ai.agents.recipe_agent import run_recipe_agent

from ai.agents.supervisor_agent.supervisor_utils import (
    LOGIN_REQUIRED_REPLY, GENERAL_REPLY,
    CONFIRM_PREFIX, CANCEL_WORDS,
    _normalize_text
)
from ai.agents.shopping_agent.shopping_utils import SHOPPING_CONFIRM_ACTIONS, analyze_shopping_intent

def _route_result(intent: str, confidence: float = 1.0, slots: dict | None = None) -> dict:
    """라우터 결과를 공통 dict 형식으로 반환합니다."""
    payload = {"intent": intent, "confidence": confidence, "slots": slots or {}}
    return {"intent": intent, "intent_payload": payload, "slots": payload["slots"]}

def router_node(state: GraphState) -> dict:
    """사용자 메시지를 분석하여 LangGraph 분기용 intent를 반환합니다."""
    text = state["text"]
    normalized = _normalize_text(text)
    history = state.get("history", [])

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
    shopping_intent = analyze_shopping_intent(text)
    if shopping_intent:
        return _route_result(shopping_intent)

    # 곁들임 추천은 레시피 검색이 아니라 짧은 메뉴 조합으로 응답합니다.
    if any(word in normalized for word in ('이랑먹기좋은', '같이먹기좋은', '어울리는음식', '곁들일', '곁들이', '사이드메뉴', '반찬추천')):
        return _route_result("recipe.pairing")

    # 쓰기 작업은 LLM 의도 분류보다 먼저 고정해 할루시네이션을 막습니다.
    if any(word in normalized for word in DELETE_WORDS):
        return _route_result("inventory.delete")
    if any(word in normalized for word in EXPIRING_WORDS):
        return _route_result("inventory.expiring")
    if any(word in normalized for word in CONSUME_WORDS):
        return _route_result("inventory.action")
    if any(word in normalized for word in ADD_WORDS):
        return _route_result("inventory.action")
    if any(word.replace(" ", "") in normalized for word in INVENTORY_LIST_WORDS):
        return _route_result("inventory.list")

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
    reply, sources = state["service"]._reply_guide(state["text"])
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

    return run_shopping_agent(
        text=state["text"],
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
        parts = text.split(":")
        if len(parts) >= 2:
            action = parts[1]
            # 재고 관련 확인 액션은 Inventory Agent가 처리하므로 여기서 넘기지 않습니다.
            if action in ["consume_ingredient", "add_ingredient", "add_ingredient_unchecked", "add_ingredients", "delete_ingredient"]:
                pass 
            elif len(parts) >= 4 and action == "add_calendar_event":
                # 기존 레거시 포맷: 확인:add_calendar_event:제목:날짜
                action = "create_event"
                alarm_intent = "calendar.create"
                payload = {"title": parts[2], "date_text": ":".join(parts[3:])}
            elif len(parts) >= 3 and action == "delete_event":
                alarm_intent = "calendar.delete"
                payload = {"event_key": parts[2]}
            elif action == "sync_daily_events":
                alarm_intent = "calendar.sync_daily"
                payload = {}
    elif intent == "alarm.notification":
        # 미확인 알림 필터는 알람 에이전트에 아직 전용 도구가 없어 성공 응답처럼 보이지 않게 막습니다.
        if any(word in text for word in ('읽지 않은', '안 읽은', '안읽은', '미확인', '미열람')):
            return {"response_text": "읽지 않은 알림만 따로 조회하는 기능은 아직 준비 중이에요. 현재는 전체 알림 목록 조회만 가능해요."}
        if any(word in text for word in ('읽음', '읽었')):
            alarm_intent = "alarm.read"
        elif any(word in text for word in ('디바이스', '기기', '푸시토큰')) and any(word in text for word in ('등록', '추가', '설정')):
            alarm_intent = "alarm.register_device"
        elif any(word in text for word in ('조회', '있어', '확인', '알려')) and not any(word in text for word in ('등록', '추가', '생성', '예약', '설정', '삭제', '지워', '취소', '없애')):
            alarm_intent = "alarm.list"
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
    
    # Alarm agent의 ui 형식을 챗봇 규격으로 변환
    ui = res.get("ui", {})
    if ui and "actions" in ui:
        for a in ui["actions"]:
            label = a.get("label", "")
            val = a.get("value", {})
            if isinstance(val, dict):
                # 프론트엔드가 요구하는 텍스트 문자열 형태로 직렬화
                # 취소 버튼
                if val.get("action") == "cancel":
                    actions.append({"label": label, "data": {"message": "취소"}})
                # 확인 버튼 (create_event)
                elif val.get("action") == "create_event":
                    p = val.get("payload", {})
                    t = p.get("title", "")
                    d = p.get("date_text", "")
                    actions.append({"label": label, "data": {"message": f"확인:add_calendar_event:{t}:{d}"}})
                elif val.get("action") == "delete_event":
                    p = val.get("payload", {})
                    event_key = p.get("event_key", "")
                    actions.append({"label": label, "data": {"message": f"확인:delete_event:{event_key}"}})
                elif val.get("action") == "sync_daily_events":
                    actions.append({"label": label, "data": {"message": "확인:sync_daily_events"}})
                else:
                    # 기타 알람 액션
                    a_name = val.get("action", "")
                    actions.append({"label": label, "data": {"message": f"확인:{a_name}"}})
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
