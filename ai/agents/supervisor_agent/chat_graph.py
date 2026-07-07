import asyncio
import hashlib
import logging
import re
from datetime import date, datetime, time, timedelta, timezone

import httpx
from fastapi import HTTPException
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

from app.backend.core.config import settings
from ai.agents.supervisor_agent.chat_utils import (
    _pending_add_many_from_history,
    _is_quantity_only_list,
    _latest_bot_text,
    _extract_storage,
    _pending_add_storage_from_history,
    _pending_add_from_history,
    _pending_consume_from_history,
    _storage_choice_response
)

from app.backend.schemas.chat_state import GraphState

logger = logging.getLogger(__name__)
from ai.agents.supervisor_agent.chat_utils import (
    LOGIN_REQUIRED_REPLY, GENERAL_REPLY, CANCEL_REPLY,
    CONFIRM_PREFIX, CANCEL_WORDS, INVENTORY_ACTION_WORDS,
    DELETE_WORDS, CONSUME_WORDS, INVENTORY_LIST_WORDS,
    EXPIRING_WORDS, ADD_WORDS, DEFAULT_STORAGE, STORAGE_KEYS, KOREAN_QUANTITIES,
    _normalize_text, _get_josa, _confirm_action, _inventory_refresh_action,
    _quantity_text, _extract_quantity, _extract_delete_name, _extract_consume_name,
    _extract_storage, _strip_add_name, _extract_add_items,
    _requires_login
)

# 캘린더 실행 로직은 alarm_agent 로 이관되어 제거되었습니다.

def _execute_confirmed_action(state: GraphState) -> dict:
    """확인 버튼으로 돌아온 내부 명령을 실제 쓰기 작업으로 실행합니다."""
    if not state["user_id"]:
        return {"response_text": LOGIN_REQUIRED_REPLY}

    parts = state["text"].split(":")
    if len(parts) < 2:
        return {"response_text": GENERAL_REPLY}

    action = parts[1]
    try:
        # 재고 관리 작업 (Inventory Agent로 위임)
        if action in ["consume_ingredient", "add_ingredient", "add_ingredient_unchecked", "add_ingredients", "delete_ingredient"]:
            from ai.agents.inventory_agent.inventory_agent import execute_inventory_action
            return execute_inventory_action(action, parts, state["db"], state["user_id"])
            
    except Exception:
        state["db"].rollback()
        logger.exception("챗봇 확인 작업 실행 실패: %s", action)
        return {"response_text": "요청을 처리하는 중 문제가 생겼어요. 잠시 후 다시 시도해주세요."}
    return {"response_text": "확인할 작업을 찾지 못했어요. 다시 요청해주세요."}

def router_node(state: GraphState) -> dict:
    """사용자 메시지를 분석하여 LangGraph 분기용 intent를 반환합니다."""
    text = state["text"]
    normalized = _normalize_text(text)
    history = state.get("history", [])

    if normalized.startswith(CONFIRM_PREFIX):
        return {"intent": "mcp.confirm"}
    if normalized in CANCEL_WORDS:
        return {"intent": "mcp.cancel"}

    if _pending_add_many_from_history(history):
        if len(_extract_add_items(text)) > 1:
            return {"intent": "mcp.pending_add_many"}
        if _is_quantity_only_list(text):
            return {"intent": "mcp.pending_add_many_retry"}
    if _pending_add_storage_from_history(history) and _extract_storage(text):
        return {"intent": "mcp.pending_add_storage"}
    if _pending_add_from_history(history) and (_extract_quantity(text) or _extract_storage(text)):
        return {"intent": "mcp.pending_add"}
    if _pending_consume_from_history(history) and _extract_quantity(text):
        return {"intent": "mcp.pending_consume"}

    # 쓰기 작업은 LLM 의도 분류보다 먼저 고정해 할루시네이션을 막습니다.
    if any(word in normalized for word in DELETE_WORDS):
        return {"intent": "mcp.delete"}
    if any(word in normalized for word in CONSUME_WORDS):
        return {"intent": "mcp.inventory"}
    if any(word in normalized for word in ("일정", "캘린더", "알림")):
        return {"intent": "alarm.calendar"}
    if any(word in normalized for word in ADD_WORDS):
        return {"intent": "mcp.inventory"}
    if any(word in normalized for word in EXPIRING_WORDS):
        return {"intent": "inventory.expiring"}
    if any(word.replace(" ", "") in normalized for word in INVENTORY_LIST_WORDS):
        return {"intent": "inventory.list"}

    return {"intent": state["service"]._route_intent_with_llm(text, history)}

def _unknown_add_response(state: GraphState, items: list[dict]) -> dict | None:
    """마스터에 없는 이름은 사용자 확인 후 추가하도록 안내합니다."""
    db = state.get("db")
    if not db:
        return None

    from ai.agents.inventory_agent.inventory_agent import resolve_ingredient_name

    for item in items:
        resolved_name = resolve_ingredient_name(db, item["name"])
        if resolved_name:
            item["name"] = resolved_name
            continue
        # 부정 표현이 섞인 문장은 임의 식재료로 추가하지 않습니다.
        if _normalize_text(item["name"]) in {"안녕", "하이", "hello", "hi"} or any(token in {"안튀김", "안구이", "안볶음", "안삶음", "안찜", "안조림"} for token in item["name"].split()):
            return {"response_text": "올바른 식재료명을 입력해주세요."}
        if item.get("quantity") is None:
            item["quantity"] = 1.0
        if not item.get("storage"):
            return _storage_choice_response(item["name"], item["quantity"], unchecked=True)
        text = f"{item['name']} {_quantity_text(item['quantity'])}개를 {item['storage']}에 추가할까요?"
        command = f"확인:add_ingredient_unchecked:{item['name']}:{item['quantity']}:{item['storage']}"
        return {"response_text": text, "actions": [_confirm_action("확인", command), _confirm_action("취소", "취소")]}
    return None

def _handle_inventory_action(state: GraphState) -> dict:
    """식재료 추가/소비는 LLM 대신 규칙 기반으로 처리합니다."""
    text = state["text"]
    normalized = _normalize_text(text)

    if any(word in normalized for word in ADD_WORDS):
        items = _extract_add_items(text)
        
        from ai.agents.inventory_agent.inventory_agent import is_valid_ingredient
        invalid_items = [item['name'] for item in items if not is_valid_ingredient(item['name'])]
        if invalid_items:
            name = invalid_items[0]
            josa = _get_josa(name, "은", "는")
            return {"response_text": f"'{name}'{josa} 올바른 식재료 이름이 아닙니다. 식용 가능한 재료만 추가할 수 있어요."}

        unknown_response = _unknown_add_response(state, items)
        if unknown_response:
            return unknown_response
        if len(items) > 1:
            if any(item["quantity"] is None for item in items):
                return {"response_text": "각 식재료의 수량을 알려주시면 추가해드릴게요."}
            payload = "|".join(f"{item['name']},{item['quantity']},{item['storage'] or DEFAULT_STORAGE}" for item in items)
            summary = ", ".join(f"{item['name']} {_quantity_text(item['quantity'])}개" for item in items)
            return {"response_text": f"{summary}를 냉장고에 추가할까요?", "actions": [_confirm_action("확인", f"확인:add_ingredients:{payload}"), _confirm_action("취소", "취소")]}
        if len(items) == 1:
            item = items[0]
            if item["quantity"] is None:
                return {"response_text": f"{item['name']}를 몇 개 추가하시겠어요?"}
            if not item["storage"]:
                return _storage_choice_response(item["name"], item["quantity"])
            text = f"{item['name']} {_quantity_text(item['quantity'])}개를 {item['storage']}에 추가할까요?"
            command = f"확인:add_ingredient:{item['name']}:{item['quantity']}:{item['storage']}"
            return {"response_text": text, "actions": [_confirm_action("확인", command), _confirm_action("취소", "취소")]}
        return {"response_text": "어떤 식재료를 추가할까요? 식재료명과 수량을 함께 알려주세요."}

    if any(word in normalized for word in CONSUME_WORDS):
        name = _extract_consume_name(text)
        if not name:
            return {"response_text": "어떤 식재료를 소비 처리할까요?"}
        quantity = _extract_quantity(text)
        if quantity is None:
            return {"response_text": f"{name}를 몇 개 소비할까요?"}
        command = f"확인:consume_ingredient:{name}:{quantity}"
        return {"response_text": f"{name} {_quantity_text(quantity)}개를 소비 처리할까요?", "actions": [_confirm_action("확인", command), _confirm_action("취소", "취소")]}

    return {"response_text": GENERAL_REPLY}

def mcp_agent_node(state: GraphState) -> dict:
    """LLM tool call을 받아 쓰기 작업은 확인 버튼을 거친 뒤 실행하도록 안내합니다."""
    if state.get("intent") == "mcp.cancel":
        return {"response_text": CANCEL_REPLY}
    if state.get("intent") == "mcp.confirm":
        return _execute_confirmed_action(state)
    if state.get("intent") == "mcp.delete":
        name = _extract_delete_name(state["text"])
        if not name:
            return {"response_text": GENERAL_REPLY}
        text = f"{name} 폐기 처리할까요?"
        command = f"확인:delete_ingredient:{name}"
        return {"response_text": text, "actions": [_confirm_action("확인", command), _confirm_action("취소", "취소")]}



    if state.get("intent") == "mcp.pending_consume":
        name = _pending_consume_from_history(state.get("history", [])) or ""
        quantity = _extract_quantity(state["text"]) or 1
        text = f"{name} {_quantity_text(quantity)}개를 소비 처리할까요?"
        command = f"확인:consume_ingredient:{name}:{quantity}"
        return {"response_text": text, "actions": [_confirm_action("확인", command), _confirm_action("취소", "취소")]}

    if state.get("intent") == "mcp.pending_add_storage":
        pending = _pending_add_storage_from_history(state.get("history", []))
        storage = _extract_storage(state["text"]) or DEFAULT_STORAGE
        if not pending:
            return {"response_text": GENERAL_REPLY}
        name, quantity = pending
        text = f"{name} {_quantity_text(quantity)}개를 {storage}에 추가할까요?"
        command = f"확인:add_ingredient:{name}:{quantity}:{storage}"
        return {"response_text": text, "actions": [_confirm_action("확인", command), _confirm_action("취소", "취소")]}

    if state.get("intent") == "mcp.pending_add":
        name = _pending_add_from_history(state.get("history", [])) or ""
        quantity = _extract_quantity(state["text"]) or 1
        storage = _extract_storage(state["text"])
        if not storage:
            return _storage_choice_response(name, quantity)
        text = f"{name} {_quantity_text(quantity)}개를 {storage}에 추가할까요?"
        command = f"확인:add_ingredient:{name}:{quantity}:{storage}"
        return {"response_text": text, "actions": [_confirm_action("확인", command), _confirm_action("취소", "취소")]}

    if state.get("intent") == "mcp.pending_add_many_retry":
        return {"response_text": "식재료와 갯수를 함께 말해주세요. 예: 파스타면1, 토마토소스1, 냉동 새우1"}

    if state.get("intent") == "mcp.pending_add_many":
        items = _extract_add_items(state["text"])
        payload = "|".join(f"{item['name']},{item['quantity'] or 1},{item['storage'] or DEFAULT_STORAGE}" for item in items)
        summary = ", ".join(f"{item['name']} {_quantity_text(item['quantity'] or 1)}개" for item in items)
        text = f"{summary}를 냉장고에 추가할까요?"
        return {"response_text": text, "actions": [_confirm_action("확인", f"확인:add_ingredients:{payload}"), _confirm_action("취소", "취소")]}

    if not state["user_id"]:
        return {"response_text": LOGIN_REQUIRED_REPLY}

    if state.get("intent") == "mcp.inventory":
        return _handle_inventory_action(state)

    return {"response_text": "아직 지원하지 않는 챗봇 작업이에요."}

def inventory_list_node(state: GraphState) -> dict:
    """로그인 사용자의 냉장고 재료 목록을 안내합니다."""
    if not state["user_id"]:
        return {"response_text": LOGIN_REQUIRED_REPLY}
    from ai.agents.inventory_agent.inventory_agent import get_inventory_list
    return {"response_text": get_inventory_list(state["db"], state["user_id"])}

def inventory_expiring_node(state: GraphState) -> dict:
    """로그인 사용자의 소비기한 임박 재료를 안내합니다."""
    if not state["user_id"]:
        return {"response_text": LOGIN_REQUIRED_REPLY}
    from ai.agents.inventory_agent.inventory_agent import get_expiring_inventory
    return {"response_text": get_expiring_inventory(state["db"], state["user_id"], state["text"])}

def ingredient_guide_node(state: GraphState) -> dict:
    """식재료 보관/손질 가이드를 안내합니다."""
    reply, sources = state["service"]._reply_guide(state["text"])
    return {"response_text": reply, "sources": sources}

def recipe_recommend_node(state: GraphState) -> dict:
    """냉장고 기반 또는 재료 기반 레시피 추천을 안내합니다."""
    svc = state["service"]
    if _requires_login("recipe.recommend", state["text"]) and not state["user_id"]:
        return {"response_text": LOGIN_REQUIRED_REPLY}
    reply, actions = svc._reply_recipe_recommend(state["db"], state["user_id"], state["text"], state.get("history", []), state.get("settings_obj"))
    return {"response_text": reply, "actions": actions}

def recipe_search_node(state: GraphState) -> dict:
    """레시피 검색 결과를 안내합니다."""
    reply, actions, sources = state["service"]._reply_recipe_search(state["db"], state["text"])
    return {"response_text": reply, "actions": actions, "sources": sources}

def receipt_guide_node(state: GraphState) -> dict:
    """영수증 OCR 화면 이동 액션을 안내합니다."""
    return {
        "response_text": "영수증은 파일 업로드가 필요해서 아래 버튼을 눌러 영수증 등록 화면으로 이동해주세요.",
        "actions": [{"label": "영수증 등록하러 가기", "url": "/receipt-ocr"}],
    }

def alarm_agent_node(state: GraphState) -> dict:
    """캘린더 및 알림 관리를 Alarm Agent로 위임합니다."""
    from ai.agents.alarm_agent.alarm_agent import run as run_alarm_agent
    
    intent = state.get("intent", "")
    text = state["text"]
    confirmed = (intent == "mcp.confirm")
    
    # 챗봇 프론트에서 들어온 '확인' 액션일 경우 파싱 (기존 동작 호환)
    action = None
    payload = None
    if confirmed:
        parts = text.split(":")
        if len(parts) >= 2:
            action = parts[1]
            # mcp_agent_node 로 가야하는 재고 관련 action 이면 여기서 처리 안함
            if action in ["consume_ingredient", "add_ingredient", "add_ingredient_unchecked", "add_ingredients", "delete_ingredient"]:
                pass # 이 경우는 사실 mcp_agent_node로 라우팅됨
            elif len(parts) >= 4 and action == "add_calendar_event":
                # 기존 레거시 포맷: 확인:add_calendar_event:제목:날짜
                action = "create_event"
                payload = {"title": parts[2], "date_text": ":".join(parts[3:])}

    # Alarm Agent 실행
    res = run_alarm_agent(
        text_or_intent=text, 
        payload=payload,
        action=action,
        confirmed=confirmed
    )
    
    # Supervisor 규격(response_text, actions)으로 변환 (Adapter)
    response_text = res.get("message", "요청을 처리했습니다.")
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
                    actions.append({"label": label, "data": "취소"})
                # 확인 버튼 (create_event)
                elif val.get("action") == "create_event":
                    p = val.get("payload", {})
                    t = p.get("title", "")
                    d = p.get("date_text", "")
                    actions.append({"label": label, "data": f"확인:add_calendar_event:{t}:{d}"})
                else:
                    # 기타 알람 액션
                    a_name = val.get("action", "")
                    actions.append({"label": label, "data": f"확인:{a_name}"})
            else:
                actions.append({"label": label, "data": str(val)})
                
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
    if intent.startswith("alarm.") or intent == "mcp.calendar":
        return "alarm_agent_node"
    if intent.startswith("mcp."):
        # 확인(mcp.confirm)인 경우, 만약 알람 액션이면 alarm_agent_node로 뺀다.
        if intent == "mcp.confirm":
            parts = state["text"].split(":")
            if len(parts) >= 2 and parts[1] not in ["consume_ingredient", "add_ingredient", "add_ingredient_unchecked", "add_ingredients", "delete_ingredient"]:
                return "alarm_agent_node"
        return "mcp_agent_node"
    routes = {
        "inventory.list": "inventory_list_node",
        "inventory.expiring": "inventory_expiring_node",
        "ingredient.guide": "ingredient_guide_node",
        "recipe.recommend": "recipe_recommend_node",
        "recipe.search": "recipe_search_node",
        "receipt.guide": "receipt_guide_node",
    }
    return routes.get(intent, "general_node")

workflow = StateGraph(GraphState)
workflow.add_node("router", router_node)
workflow.add_node("mcp_agent_node", mcp_agent_node)
workflow.add_node("alarm_agent_node", alarm_agent_node)
workflow.add_node("inventory_list_node", inventory_list_node)
workflow.add_node("inventory_expiring_node", inventory_expiring_node)
workflow.add_node("ingredient_guide_node", ingredient_guide_node)
workflow.add_node("recipe_recommend_node", recipe_recommend_node)
workflow.add_node("recipe_search_node", recipe_search_node)
workflow.add_node("receipt_guide_node", receipt_guide_node)
workflow.add_node("general_node", general_node)

workflow.set_entry_point("router")
workflow.add_conditional_edges("router", route_intent)
for node_name in (
    "mcp_agent_node",
    "alarm_agent_node",
    "inventory_list_node",
    "inventory_expiring_node",
    "ingredient_guide_node",
    "recipe_recommend_node",
    "recipe_search_node",
    "receipt_guide_node",
    "general_node",
):
    workflow.add_edge(node_name, END)

chat_graph = workflow.compile()
