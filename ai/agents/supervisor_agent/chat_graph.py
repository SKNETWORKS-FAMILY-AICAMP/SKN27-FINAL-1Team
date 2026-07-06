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
from ai.tools.calendar_tools import CALENDAR_TOOLS
from ai.agents.supervisor_agent.chat_utils import (
    _pending_calendar_from_history,
    _pending_add_many_from_history,
    _is_quantity_only_list,
    _latest_bot_text,
    _extract_storage,
    _pending_add_storage_from_history,
    _pending_add_from_history,
    _pending_consume_from_history,
    _parse_calendar_date,
    _has_calendar_date_text,
    _calendar_datetime_from_text,
    _calendar_display,
    _storage_choice_response
)

from app.backend.schemas.chat_state import GraphState

logger = logging.getLogger(__name__)
from ai.agents.supervisor_agent.chat_utils import (
    LOGIN_REQUIRED_REPLY, GENERAL_REPLY, CANCEL_REPLY,
    CONFIRM_PREFIX, CANCEL_WORDS, INVENTORY_ACTION_WORDS,
    CALENDAR_WORDS, DELETE_WORDS, CONSUME_WORDS, INVENTORY_LIST_WORDS,
    EXPIRING_WORDS, ADD_WORDS, DEFAULT_STORAGE, STORAGE_KEYS, KOREAN_QUANTITIES,
    _normalize_text, _get_josa, _confirm_action, _inventory_refresh_action,
    _quantity_text, _extract_quantity, _extract_delete_name, _extract_consume_name,
    _extract_storage, _strip_add_name, _extract_add_items,
    _requires_login
)

def _execute_calendar_event(db, user_id: int, title: str, date_str: str) -> str:
    """Google Calendar 연동 정보를 이용해 실제 캘린더 일정을 생성합니다."""
    from app.backend.api.calendar.calendar_api import _create_event_once, _get_access_token, _get_google_integration

    async def create_event() -> None:
        integration = _get_google_integration(db, user_id)
        access_token = await _get_access_token(integration, db)
        start_at = _calendar_datetime_from_text(date_str, date_str)
        end_at = start_at + timedelta(hours=1)
        target_date = start_at.date()
        event_key = f"chat-{user_id}-{start_at.isoformat()}-{hashlib.sha1(title.encode()).hexdigest()[:8]}"
        event = {
            "summary": title,
            "description": "밥벌이 챗봇에서 등록한 일정입니다.",
            "start": {"dateTime": start_at.isoformat()},
            "end": {"dateTime": end_at.isoformat()},
            "extendedProperties": {"private": {"bobbeoriKey": event_key}},
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            await _create_event_once(client, integration.calendar_id, access_token, event_key, event, db, user_id, "chatbot")

    try:
        asyncio.run(create_event())
        return f"'{title}' 일정을 {_calendar_display(_calendar_datetime_from_text(date_str, date_str))}에 등록했어요."
    except HTTPException as exc:
        if exc.status_code == 404:
            return "Google Calendar 연동이 필요해요. 마이페이지에서 캘린더를 먼저 연결해주세요."
        return "캘린더 등록 중 문제가 생겼어요. 잠시 후 다시 시도해주세요."
    except Exception:
        return "캘린더 등록 중 문제가 생겼어요. 잠시 후 다시 시도해주세요."

def _execute_confirmed_action(state: GraphState) -> dict:
    """확인 버튼으로 돌아온 내부 명령을 실제 쓰기 작업으로 실행합니다."""
    if not state["user_id"]:
        return {"response_text": LOGIN_REQUIRED_REPLY}

    parts = state["text"].split(":")
    if len(parts) < 2:
        return {"response_text": GENERAL_REPLY}

    action = parts[1]
    from app.backend.services.inventory_service.inventory_service import inventory_service

    try:
        if action == "consume_ingredient" and len(parts) >= 4:
            reply = inventory_service.consume_ingredient_by_name(state["db"], state["user_id"], parts[2], float(parts[3]))
            return {"response_text": reply, "actions": [_inventory_refresh_action()]}

        if action == "add_ingredient" and len(parts) >= 5:
            reply = inventory_service.add_ingredient_by_name(state["db"], state["user_id"], parts[2], float(parts[3]), parts[4])
            return {"response_text": reply, "actions": [_inventory_refresh_action()]}

        if action == "add_ingredient_unchecked" and len(parts) >= 5:
            reply = inventory_service.add_ingredient_unchecked_by_name(state["db"], state["user_id"], parts[2], float(parts[3]), parts[4])
            return {"response_text": reply, "actions": [_inventory_refresh_action()]}

        if action == "add_ingredients" and len(parts) >= 3:
            added = []
            for raw_item in parts[2].split("|"):
                name, quantity, storage = raw_item.split(",", 2)
                added.append(inventory_service.add_ingredient_by_name(state["db"], state["user_id"], name, float(quantity), storage))
            return {"response_text": "\n".join(added), "actions": [_inventory_refresh_action()]}

        if action == "delete_ingredient" and len(parts) >= 3:
            reply = inventory_service.delete_ingredient_by_name(state["db"], state["user_id"], parts[2])
            return {"response_text": reply, "actions": [_inventory_refresh_action()]}
        if action == "add_calendar_event" and len(parts) >= 4:
            reply = _execute_calendar_event(state["db"], state["user_id"], parts[2], ":".join(parts[3:]))
            return {"response_text": reply}
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
    if _pending_calendar_from_history(history) and any(word in normalized for word in CALENDAR_WORDS + ADD_WORDS):
        return {"intent": "mcp.pending_calendar"}
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
    if any(word in normalized for word in CALENDAR_WORDS):
        return {"intent": "mcp.calendar"}
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

    from app.backend.services.inventory_service.inventory_service import inventory_service

    for item in items:
        resolved_name = inventory_service._resolve_known_ingredient_name(db, item["name"])
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
        
        from app.backend.services.inventory_service.expiration_ai_service import expiration_ai_service
        invalid_items = [item['name'] for item in items if not expiration_ai_service.is_valid_ingredient_name(item['name'])]
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

    if state.get("intent") == "mcp.pending_calendar":
        pending = _pending_calendar_from_history(state.get("history", []))
        if not pending:
            return {"response_text": GENERAL_REPLY}
        title, fallback = pending
        start_at = _calendar_datetime_from_text(state["text"], fallback)
        date_value = start_at.isoformat()
        text = f"'{title}' 일정을 {_calendar_display(start_at)}에 등록할까요?"
        command = f"확인:add_calendar_event:{title}:{date_value}"
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

    messages = state.get("messages") or [HumanMessage(content=state["text"])]
    if state.get("intent") == "mcp.calendar":
        sys_msg = SystemMessage(content="당신은 사용자의 일정을 관리하는 비서입니다. 사용자가 캘린더에 일정을 추가해 달라고 요청할 때, 일정의 제목과 날짜 정보가 모두 있다면 반드시 add_calendar_event 도구를 호출하세요.")
        if not any(getattr(m, "type", "") == "system" for m in messages):
            messages = [sys_msg] + messages
    llm = ChatOpenAI(model=settings.OPENAI_MODEL, api_key=settings.OPENAI_API_KEY, temperature=0.0)
    response = llm.bind_tools(CALENDAR_TOOLS).invoke(messages)

    if not response.tool_calls:
        return {"response_text": "일정 제목과 날짜를 함께 알려주세요."}

    tool_call = response.tool_calls[0]
    if tool_call["name"] == "add_calendar_event":
        args = tool_call["args"]
        title = args.get("title", "일정")
        date_str = args.get("date_str", "오늘")
        start_at = _calendar_datetime_from_text(state["text"], date_str)
        date_value = start_at.isoformat()
        text = f"'{title}' 일정을 {_calendar_display(start_at)}에 등록할까요?"
        command = f"확인:add_calendar_event:{title}:{date_value}"
        return {"response_text": text, "actions": [_confirm_action("확인", command), _confirm_action("취소", "취소")], "messages": messages + [response]}
    return {"response_text": "아직 지원하지 않는 챗봇 작업이에요.", "messages": messages + [response]}

def inventory_list_node(state: GraphState) -> dict:
    """로그인 사용자의 냉장고 재료 목록을 안내합니다."""
    if not state["user_id"]:
        return {"response_text": LOGIN_REQUIRED_REPLY}
    return {"response_text": state["service"]._reply_inventory_list(state["db"], state["user_id"])}

def inventory_expiring_node(state: GraphState) -> dict:
    """로그인 사용자의 소비기한 임박 재료를 안내합니다."""
    if not state["user_id"]:
        return {"response_text": LOGIN_REQUIRED_REPLY}
    return {"response_text": state["service"]._reply_expiring_items(state["db"], state["user_id"], state["text"])}

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

def general_node(state: GraphState) -> dict:
    """지원 범위 밖 질문에는 고정 안내문만 반환합니다."""
    return {"response_text": GENERAL_REPLY}

def route_intent(state: GraphState) -> str:
    """intent 값을 LangGraph 노드 이름으로 변환합니다."""
    intent = state.get("intent") or "general"
    if intent.startswith("mcp."):
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
