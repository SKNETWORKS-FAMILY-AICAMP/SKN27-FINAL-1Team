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
    CANCEL_WORDS,
    CONFIRM_PREFIX,
    GENERAL_REPLY,
    LOGIN_REQUIRED_REPLY,
    _CONTEXT_INTENTS,
    _alarm_result_to_state,
    _build_read_tasks,
    _is_alarm_calendar_query,
    _is_alarm_notification_query,
    _is_guide_query,
    _is_receipt_query,
    _is_recipe_pairing_query,
    _is_recipe_recommend_query,
    _is_recipe_search_query,
    _is_shopping_price_explanation,
    _is_shopping_show_all_request,
    _is_shopping_price_query,
    _is_context_follow_up,
    _is_cooking_time_question,
    _is_expiring_question,
    _latest_bot_intent,
    _latest_bot_pending_action,
    _latest_bot_slots,
    _merge_agent_results,
    _normalize_shopping_create_query,
    _normalize_text,
    _parse_alarm_request,
    _reply_recipe_pairing,
    _rewrite_context_switch,
    _rewrite_guide_query,
    _strip_shopping_compare_suffix,
    _route_result,
)
from ai.agents.shopping_agent.shopping_utils import SHOPPING_CONFIRM_ACTIONS, analyze_shopping_intent


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
    if _is_receipt_query(text):
        return _route_result("receipt.guide")

    # 일정/알림 요청은 삭제 문장이더라도 냉장고 삭제로 보내지 않습니다.
    if _is_alarm_notification_query(text):
        return _route_result("alarm.notification")
    if _is_alarm_calendar_query(text):
        return _route_result("alarm.calendar")

    if _is_shopping_price_explanation(text):
        return _route_result("shopping.price_help")

    # 읽기 전용 복합 요청은 기존 Agent 작업 목록으로 분해해 순차 실행합니다.
    read_tasks = _build_read_tasks(text)
    if len(read_tasks) >= 2:
        return _route_result("multi_agent", tasks=read_tasks)

    # 가격 질문은 Guide와 일반 LLM보다 Shopping Agent를 우선합니다.
    if _is_shopping_price_query(text):
        return _route_result("shopping.compare")

    # 가이드 질문을 Shopping의 부분 문자열 매칭과 냉장고 목록보다 먼저 처리합니다.
    if _is_guide_query(text):
        return _route_result("ingredient.guide")
    # "장본거" 표현은 냉장고 보유 재료가 아니라 장보기 목록 조회로 처리합니다.
    if "장본" in normalized:
        return _route_result("shopping.current")

    shopping_intent = analyze_shopping_intent(text)
    if shopping_intent:
        return _route_result(shopping_intent)
    # 곁들임 추천은 레시피 검색이 아니라 짧은 메뉴 조합으로 응답합니다.
    if _is_recipe_pairing_query(text):
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
    if _is_recipe_recommend_query(text):
        return _route_result("recipe.recommend")
    if any(word.replace(" ", "") in normalized for word in INVENTORY_LIST_WORDS):
        return _route_result("inventory.list")
    if _is_recipe_search_query(text):
        return _route_result("recipe.search")

    route_payload = state["service"]._route_intent_payload_with_llm(text, history)
    return _route_result(
        route_payload.get("intent", "general"),
        route_payload.get("confidence", 0.0),
        route_payload.get("slots", {}),
        route_payload.get("tasks", []),
    )


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
    """식재료 가이드 요청을 Guide Agent에 전달합니다."""
    # 정정 표현이 있으면 마지막에 선택한 식재료 질문만 가이드에 전달합니다.
    query = _rewrite_guide_query(state["text"])
    return state["service"]._reply_guide(query)

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
    return {"response_text": _reply_recipe_pairing(state["text"])}

def receipt_guide_node(state: GraphState) -> dict:
    """영수증 OCR 화면 이동 액션을 안내합니다."""
    return {
        "response_text": "영수증은 파일 업로드가 필요해서 아래 버튼을 눌러 영수증 등록 화면으로 이동해주세요.",
        "actions": [{"label": "영수증 등록하러 가기", "url": "/receipt-ocr"}],
    }

def shopping_agent_node(state: GraphState) -> dict:
    """장보기 관리를 Shopping Agent로 위임합니다."""
    from ai.agents.shopping_agent.shopping_agent import run_shopping_agent

    if state.get("intent") == "shopping.price_help":
        return {
            "response_text": "가격 정보 없음은 상품 검색 결과에서 판매가를 확인하지 못했다는 뜻이에요. 상품명이나 용량을 더 구체적으로 입력하면 검색 정확도가 좋아질 수 있어요."
        }
    if not state.get("user_id"):
        return {"response_text": LOGIN_REQUIRED_REPLY}

    # 나머지/전체 조회 후속 요청은 기존 Shopping 조회 결과를 모두 펼쳐 보여줍니다.
    if state.get("intent") == "shopping.current" and _is_shopping_show_all_request(state["text"]):
        from app.backend.services.shopping_service import shopping_service
        from ai.agents.shopping_agent.shopping_utils import shopping_list_action, summarize_shopping_list

        shopping_list = shopping_service.get_current(db=state["db"], user_id=state["user_id"])
        max_items = len((shopping_list or {}).get("items", [])) or 5
        return {
            "response_text": summarize_shopping_list(shopping_list, max_items=max_items),
            "actions": [shopping_list_action(shopping_list.get("id") if shopping_list else None)],
        }

    # 가격 비교 후속 표현은 제거하고 실제 상품명만 Shopping Agent에 전달합니다.
    text = state["text"]
    if state.get("intent") == "shopping.create":
        text = _normalize_shopping_create_query(text)
    compare_text = _strip_shopping_compare_suffix(text)

    return run_shopping_agent(
        text=compare_text or text,
        intent=state.get("intent", ""),
        history=state.get("history", []),
        db=state["db"],
        user_id=state.get("user_id"),
    )

def alarm_agent_node(state: GraphState) -> dict:
    """캘린더 및 알림 관리를 Alarm Agent로 위임합니다."""
    from ai.agents.alarm_agent import ALARM_AGENT_TOOLS
    from ai.agents.alarm_agent.alarm_agent import run as run_alarm_agent

    request = _parse_alarm_request(state["text"], state.get("intent", ""))
    agent_result = run_alarm_agent(
        text_or_intent=state["text"],
        payload=request["payload"],
        intent=request["intent"],
        action=request["action"],
        confirmed=request["confirmed"],
        tools=ALARM_AGENT_TOOLS,
        context={"user_id": state.get("user_id"), "db": state["db"]},
    )
    return _alarm_result_to_state(agent_result)

def general_node(state: GraphState) -> dict:
    """지원 범위 밖 질문에는 고정 안내문만 반환합니다."""
    return {"response_text": GENERAL_REPLY}

def multi_agent_node(state: GraphState) -> dict:
    """작업 목록을 순차 실행하고 일부 Agent 실패가 전체 응답을 막지 않게 합니다."""
    handlers = {
        "inventory_agent_node": inventory_agent_node,
        "guide_agent_node": guide_agent_node,
        "recipe_agent_node": recipe_agent_node,
        "recipe_pairing_node": recipe_pairing_node,
        "receipt_guide_node": receipt_guide_node,
        "shopping_agent_node": shopping_agent_node,
    }
    results = []
    completed_intents = []
    failed_intents = []

    for task in state.get("tasks") or []:
        intent = task.get("intent", "")
        task_state = {
            **state,
            "intent": intent,
            "text": task.get("text") or state["text"],
            "tasks": [],
        }
        # 임박 재료 조회 뒤 레시피 추천은 같은 냉장고 기준으로 이어서 처리합니다.
        if intent == "recipe.recommend" and "inventory.expiring" in completed_intents:
            task_state["text"] = "냉장고 재료로 요리 추천해줘"
        handler = handlers.get(route_intent(task_state))
        if not handler:
            failed_intents.append(intent)
            continue
        try:
            results.append(handler(task_state))
            completed_intents.append(intent)
        except Exception as exc:
            print(f"[Supervisor] {intent} task failed: {type(exc).__name__}: {exc}")
            failed_intents.append(intent)

    if failed_intents:
        results.append({"response_text": "일부 요청은 처리하지 못했어요. 잠시 후 다시 시도해주세요."})
    if not results:
        return general_node(state)

    result = _merge_agent_results(*results)
    result["slots"] = {
        **(result.get("slots") or {}),
        "completed_intents": completed_intents,
        "failed_intents": failed_intents,
    }
    return result


def route_intent(state: GraphState) -> str:
    """intent 값을 LangGraph 노드 이름으로 변환합니다."""
    intent = state.get("intent") or "general"
    if intent == "multi_agent":
        return "multi_agent_node"
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
workflow.add_node("multi_agent_node", multi_agent_node)
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
    "multi_agent_node",
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
