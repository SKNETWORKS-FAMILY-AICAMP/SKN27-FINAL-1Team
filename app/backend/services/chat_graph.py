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
from ai.tools.inventory_tools import INVENTORY_TOOLS
from app.backend.schemas.chat_state import GraphState

logger = logging.getLogger(__name__)
# 챗봇 기본 응답 문구
LOGIN_REQUIRED_REPLY = "\ub85c\uadf8\uc778\uc774 \ud544\uc694\ud55c \uc9c8\ubb38\uc774\uc5d0\uc694. \ube44\ud68c\uc6d0 \uc0c1\ud0dc\uc5d0\uc11c\ub294 \ubcf4\uad00\ubc95\uc774\ub098 \uc77c\ubc18 \ub808\uc2dc\ud53c \uac80\uc0c9\uc744 \uc774\uc6a9\ud560 \uc218 \uc788\uc5b4\uc694."
GENERAL_REPLY = "\uc694\ub9ac\uc640 \uc2dd\uc7ac\ub8cc \uad00\ub828 \uc9c8\ubb38\uc744 \ubb3c\uc5b4\ubd10 \uc8fc\uc138\uc694.\n\uc608: \uc591\ud30c \ubcf4\uad00\ubc95, \uac10\uc790\ud280\uae40 \uc5d0\uc5b4\ud504\ub77c\uc774\uae30 \uc2dc\uac04, \ub450\ubd80 \ub808\uc2dc\ud53c"
CANCEL_REPLY = "\uc54c\uaca0\uc5b4\uc694. \uc791\uc5c5\uc744 \ucde8\uc18c\ud588\uc5b4\uc694."

# 확인/취소 액션 키워드
CONFIRM_PREFIX = "\ud655\uc778:"
CANCEL_WORDS = ("\ucde8\uc18c", "\uc544\ub2c8", "\uc544\ub2c8\uc694", "\ucde8\uc18c\ud560\uac8c")

# 의도 분류용 키워드
INVENTORY_ACTION_WORDS = (
    "\uba39\uc5c8\uc5b4",
    "\ub2e4\uc37c\uc5b4",
    "\ub2e4\uba39\uc5c8\uc5b4",
    "\ubc84\ub838\uc5b4",
    "\uc18c\ube44\ud588",
    "\uc0ac\uc6a9\ud588",
    "\uc37c\uc5b4",
    "\ucd94\uac00",
    "\ucd94\uac00\ud574\uc918",
    "\ub4f1\ub85d",
    "\ub4f1\ub85d\ud574\uc918",
    "\ub123\uc5c8\uc5b4",
    "\ub123\uc5b4\uc918",
    "\uc0c0\uc5b4",
    "\uc0bf\uc5b4",
    "\uc0ac\uc654\uc5b4",
    "\uad6c\ub9e4\ud588",
    "\uc0ad\uc81c",
    "\ud3d0\uae30",
    "\uc9c0\uc6cc",
)
CALENDAR_WORDS = ("\uc77c\uc815", "\uce98\ub9b0\ub354")
DELETE_WORDS = ("\uc0ad\uc81c", "\ud3d0\uae30", "\uc9c0\uc6cc", "\ubc84\ub824")
INVENTORY_LIST_WORDS = ("뭐 있어", "뭐 있지", "뭐있", "뭐잇", "머있", "머잇", "뭐이", "목록", "현재 재료", "현재 냉장고")
ADD_WORDS = ("\ucd94\uac00", "\ub4f1\ub85d", "\ub123", "\uc0c0", "\uc0bf", "\uc0ac\uc654", "\uad6c\ub9e4")

# 식재료 입력 파싱용 기본값
DEFAULT_STORAGE = "\ub0c9\uc7a5"
STORAGE_KEYS = ("\ub0c9\uc7a5", "\ub0c9\ub3d9", "\uc2e4\uc628")
KOREAN_QUANTITIES = {
    "\ud55c": 1,
    "\ud558\ub098": 1,
    "\ub450": 2,
    "\ub458": 2,
    "\uc138": 3,
    "\uc14b": 3,
    "\ub124": 4,
    "\ub137": 4,
}


def _normalize_text(text: str) -> str:
    """사용자 문장을 간단 비교할 수 있도록 정리합니다."""
    return text.replace(" ", "").lower()


def _confirm_action(label: str, command: str) -> dict:
    """쓰기 작업 전 사용자 확인 버튼을 만듭니다."""
    return {"label": label, "data": {"message": command}}


def _inventory_refresh_action() -> dict:
    """냉장고 목록을 다시 불러오도록 프론트에 전달할 액션을 만듭니다."""
    return {"label": "\ub0c9\uc7a5\uace0 \uc0c8\ub85c\uace0\uce68", "data": {"refreshInventory": True}}


def _quantity_text(quantity: float) -> str:
    """수량을 사용자가 읽기 좋은 형태로 바꿉니다."""
    number = float(quantity or 1)
    return str(int(number)) if number.is_integer() else str(number)



def _extract_quantity(text: str) -> float | None:
    """사용자 문장에서 수량만 간단히 추출합니다."""
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:\uac1c|g|kg|ml|l)?", text, re.IGNORECASE)
    if match:
        return float(match.group(1))
    normalized = text.replace(" ", "")
    for word, quantity in KOREAN_QUANTITIES.items():
        if f"{word}\uac1c" in normalized:
            return float(quantity)
    return None




def _extract_delete_name(text: str) -> str:
    """\uc0ad\uc81c/\ud3d0\uae30 \ubb38\uc7a5\uc5d0\uc11c \uc2dd\uc7ac\ub8cc\uba85\ub9cc \uac04\ub2e8\ud788 \ucd94\ucd9c\ud569\ub2c8\ub2e4."""
    target = text
    for word in DELETE_WORDS:
        if word in target:
            target = target.split(word, 1)[0]
            break
    for token in ("\ub0c9\uc7a5\uace0\uc5d0\uc11c", "\ub0c9\uc7a5\uace0\uc5d0", "\ub0c9\uc7a5\uace0", "\uc7ac\ub8cc", "\uc2dd\uc7ac\ub8cc"):
        target = target.replace(token, " ")
    return target.strip().rstrip("\uc744\ub97c\uc740\ub294\uc774\uac00")




def _strip_add_name(name: str) -> str:
    """\ucd94\uac00 \ubb38\uc7a5\uc5d0\uc11c \uc2dd\uc7ac\ub8cc\uba85\uc5d0 \ubd99\uc740 \ubd88\ud544\uc694\ud55c \ub2e8\uc5b4\ub97c \uc815\ub9ac\ud569\ub2c8\ub2e4."""
    cleaned = name
    for token in ("\ub0c9\uc7a5\uace0\uc5d0\uc11c", "\ub0c9\uc7a5\uace0\uc5d0", "\ub0c9\uc7a5\uace0", "\uc7ac\ub8cc", "\uc2dd\uc7ac\ub8cc"):
        cleaned = cleaned.replace(token, " ")
    for storage in STORAGE_KEYS:
        cleaned = re.sub(rf"(?<![\uac00-\ud7a3A-Za-z0-9]){storage}(?![\uac00-\ud7a3A-Za-z0-9])", " ", cleaned)
    return cleaned.strip(" ,/\t\n\uc744\ub97c\uc740\ub294\uc774\uac00")


def _extract_add_items(text: str) -> list[dict]:
    """\ucd94\uac00 \uc694\uccad\uc5d0\uc11c \uc2dd\uc7ac\ub8cc\uba85, \uc218\ub7c9, \ubcf4\uad00 \uc704\uce58\ub97c \uac04\ub2e8\ud788 \ucd94\ucd9c\ud569\ub2c8\ub2e4."""
    target = text
    for word in ADD_WORDS:
        if word in target:
            target = target.split(word, 1)[0]
            break
    items = []
    for raw_part in re.split(r"[,/]", target):
        part = raw_part.strip()
        if not part:
            continue
        storage = _extract_storage(part)
        quantity = _extract_quantity(part)
        name = re.sub(r"\d+(?:\.\d+)?\s*(?:\uac1c|g|kg|ml|l)?", " ", part, flags=re.IGNORECASE)
        for word in KOREAN_QUANTITIES:
            name = name.replace(f"{word}\uac1c", " ")
        name = _strip_add_name(name)
        if name:
            items.append({"name": name, "quantity": quantity, "storage": storage})
    return items


def _pending_add_many_from_history(history) -> bool:
    """\uc9c1\uc804 \ubd07 \uc751\ub2f5\uc774 \uc5ec\ub7ec \uc2dd\uc7ac\ub8cc \uc218\ub7c9\uc744 \uae30\ub2e4\ub9ac\ub294\uc9c0 \ud655\uc778\ud569\ub2c8\ub2e4."""
    for message in reversed(history or []):
        if getattr(message, "role", "") != "bot":
            continue
        text = getattr(message, "text", "")
        return "\uac01 \uc2dd\uc7ac\ub8cc\uc758 \uc218\ub7c9" in text
    return False

def _is_quantity_only_list(text: str) -> bool:
    """여러 재료 추가 대기 중 수량만 나열한 응답인지 확인합니다."""
    parts = [part.strip() for part in re.split(r"[,/]", text) if part.strip()]
    return len(parts) > 1 and all(
        _extract_quantity(part) is not None
        and not _strip_add_name(re.sub(r"\d+(?:\.\d+)?\s*(?:\uac1c|g|kg|ml|l)?", " ", part, flags=re.IGNORECASE))
        for part in parts
    )
def _extract_storage(text: str) -> str | None:
    """사용자 문장에서 보관 위치를 찾습니다."""
    normalized = text.replace(" ", "")
    aliases = {"냉장실": "냉장", "냉동실": "냉동", "상온": "실온"}
    for alias, storage in aliases.items():
        if alias in normalized:
            return storage
    for storage in STORAGE_KEYS:
        if re.search(rf"(?<![가-힣A-Za-z0-9]){storage}(?![가-힣A-Za-z0-9])", text):
            return storage
    return None


def _pending_add_storage_from_history(history) -> tuple[str, float] | None:
    """직전 봇의 보관 위치 질문에서 추가 대기 중인 식재료명과 수량을 찾습니다."""
    pattern = r"(.+?)\s+(\d+(?:\.\d+)?)개를\s+어디에\s+보관"
    for message in reversed(history or []):
        if getattr(message, "role", "") != "bot":
            continue
        match = re.search(pattern, getattr(message, "text", ""))
        if match:
            return match.group(1).strip(), float(match.group(2))
    return None


def _pending_add_from_history(history) -> str | None:
    """직전 봇의 수량 질문에서 추가 대기 중인 식재료명을 찾습니다."""
    patterns = (
        r"(.+?)(?:\uc744|\ub97c)\s*\uba87\s*\uac1c.*\ucd94\uac00",
        r"(.+?)\s*\uba87\s*\uac1c.*\ucd94\uac00",
    )
    for message in reversed(history or []):
        if getattr(message, "role", "") != "bot":
            continue
        text = getattr(message, "text", "")
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1).strip(" \"'.,!?\uc744\ub97c")
    return None


def _pending_consume_from_history(history) -> str | None:
    """직전 봇의 수량 질문에서 소비 대기 중인 식재료명을 찾습니다."""
    for message in reversed(history or []):
        if getattr(message, "role", "") != "bot":
            continue
        match = re.search(r"(.+?)(?:\uc744|\ub97c) \uba87 \uac1c (?:\uba39|\uc18c\ube44)", getattr(message, "text", ""))
        return match.group(1).strip() if match else None
    return None

def _parse_calendar_date(date_str: str) -> date:
    """챗봇이 뽑은 짧은 날짜 표현을 캘린더 날짜로 변환합니다."""
    text = (date_str or "\uc624\ub298").strip()
    today = date.today()
    if "\ubaa8\ub808" in text:
        return today + timedelta(days=2)
    if "\ub0b4\uc77c" in text:
        return today + timedelta(days=1)
    if "\uc624\ub298" in text:
        return today
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return today



def _calendar_datetime_from_text(text: str, fallback: str) -> datetime:
    """사용자 원문을 우선해 캘린더 일정 시작 시간을 계산합니다."""
    base_date = _parse_calendar_date(text if any(word in text for word in ("오늘", "내일", "모레")) else fallback)
    time_match = re.search(r"(오전|오후)?\s*(\d{1,2})\s*시(?:\s*(\d{1,2})\s*분)?", text)
    hour = 9
    minute = 0
    if time_match:
        meridiem, hour_text, minute_text = time_match.groups()
        hour = int(hour_text)
        minute = int(minute_text or 0)
        if meridiem == "오후" and hour < 12:
            hour += 12
        if meridiem == "오전" and hour == 12:
            hour = 0
    elif "T" in fallback:
        try:
            parsed = datetime.fromisoformat(fallback[:19])
            hour, minute = parsed.hour, parsed.minute
        except ValueError:
            pass
    return datetime.combine(base_date, time(hour, minute), timezone(timedelta(hours=9)))


def _calendar_display(value: datetime) -> str:
    """캘린더 확인 문구에 보여줄 날짜와 시간을 만듭니다."""
    return value.strftime("%Y-%m-%d %H:%M")

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
            "description": "\ubc25\ubc8c\uc774 \ucc57\ubd07\uc5d0\uc11c \ub4f1\ub85d\ud55c \uc77c\uc815\uc785\ub2c8\ub2e4.",
            "start": {"dateTime": start_at.isoformat()},
            "end": {"dateTime": end_at.isoformat()},
            "extendedProperties": {"private": {"bobbeoriKey": event_key}},
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            await _create_event_once(client, integration.calendar_id, access_token, event_key, event, db, user_id, "chatbot")

    try:
        asyncio.run(create_event())
        return f"'{title}' \uc77c\uc815\uc744 {_calendar_display(_calendar_datetime_from_text(date_str, date_str))}\uc5d0 \ub4f1\ub85d\ud588\uc5b4\uc694."
    except HTTPException as exc:
        if exc.status_code == 404:
            return "Google Calendar \uc5f0\ub3d9\uc774 \ud544\uc694\ud574\uc694. \ub9c8\uc774\ud398\uc774\uc9c0\uc5d0\uc11c \uce98\ub9b0\ub354\ub97c \uba3c\uc800 \uc5f0\uacb0\ud574\uc8fc\uc138\uc694."
        return "\uce98\ub9b0\ub354 \ub4f1\ub85d \uc911 \ubb38\uc81c\uac00 \uc0dd\uacbc\uc5b4\uc694. \uc7a0\uc2dc \ud6c4 \ub2e4\uc2dc \uc2dc\ub3c4\ud574\uc8fc\uc138\uc694."
    except Exception:
        return "\uce98\ub9b0\ub354 \ub4f1\ub85d \uc911 \ubb38\uc81c\uac00 \uc0dd\uacbc\uc5b4\uc694. \uc7a0\uc2dc \ud6c4 \ub2e4\uc2dc \uc2dc\ub3c4\ud574\uc8fc\uc138\uc694."


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
    return {"response_text": "\ud655\uc778\ud560 \uc791\uc5c5\uc744 \ucc3e\uc9c0 \ubabb\ud588\uc5b4\uc694. \ub2e4\uc2dc \uc694\uccad\ud574\uc8fc\uc138\uc694."}


def router_node(state: GraphState) -> dict:
    """사용자 메시지를 분석하여 LangGraph 분기용 intent를 반환합니다."""
    text = state["text"]
    normalized = _normalize_text(text)

    if normalized.startswith(CONFIRM_PREFIX):
        return {"intent": "mcp.confirm"}
    if normalized in CANCEL_WORDS:
        return {"intent": "mcp.cancel"}
    if _pending_add_many_from_history(state.get("history", [])):
        if len(_extract_add_items(text)) > 1:
            return {"intent": "mcp.pending_add_many"}
        if _is_quantity_only_list(text):
            return {"intent": "mcp.pending_add_many_retry"}
    if _pending_consume_from_history(state.get("history", [])) and _extract_quantity(text):
        return {"intent": "mcp.pending_consume"}
    
    if _pending_add_from_history(state.get("history", [])) and _extract_quantity(text):
        return {"intent": "mcp.pending_add_quantity"}

    history = state.get("history", [])
    if history:
        last_msg = history[-1]
        if getattr(last_msg, "role", "") == "bot":
            last_text = getattr(last_msg, "text", "")
            if "먼저 어떤 식재료를 추가하시겠어요?" in last_text or "어디에 보관할까요" in last_text or "몇 개를 추가" in last_text or "수량을 알려주" in last_text or "보관 방법" in last_text:
                return {"intent": "mcp.inventory"}

    intent = state["service"]._route_intent_with_llm(text, history)
    
    if intent == "general":
        if any(word in normalized for word in DELETE_WORDS):
            intent = "mcp.delete"
        elif any(word in normalized for word in CALENDAR_WORDS):
            intent = "mcp.calendar"
        elif any(word.replace(" ", "") in normalized for word in INVENTORY_LIST_WORDS):
            intent = "inventory.list"
        elif any(word in normalized for word in INVENTORY_ACTION_WORDS):
            intent = "mcp.inventory"

    return {"intent": intent}


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
        text = f"{name} \ud3d0\uae30 \ucc98\ub9ac\ud560\uae4c\uc694?"
        command = f"\ud655\uc778:delete_ingredient:{name}"
        return {"response_text": text, "actions": [_confirm_action("\ud655\uc778", command), _confirm_action("\ucde8\uc18c", "\ucde8\uc18c")]}

    if state.get("intent") == "mcp.pending_consume":
        name = _pending_consume_from_history(state.get("history", [])) or ""
        quantity = _extract_quantity(state["text"]) or 1
        text = f"{name} {_quantity_text(quantity)}\uac1c\ub97c \uc18c\ube44 \ucc98\ub9ac\ud560\uae4c\uc694?"
        command = f"\ud655\uc778:consume_ingredient:{name}:{quantity}"
        return {"response_text": text, "actions": [_confirm_action("\ud655\uc778", command), _confirm_action("\ucde8\uc18c", "\ucde8\uc18c")]}
        
    if state.get("intent") == "mcp.pending_add_quantity":
        name = _pending_add_from_history(state.get("history", [])) or ""
        quantity = _extract_quantity(state["text"]) or 1
        text = f"{name} {_quantity_text(quantity)}개를 어디에 보관하여 추가할까요?"
        actions = [
            _confirm_action("냉장", f"확인:add_ingredient:{name}:{quantity}:냉장"),
            _confirm_action("냉동", f"확인:add_ingredient:{name}:{quantity}:냉동"),
            _confirm_action("실온", f"확인:add_ingredient:{name}:{quantity}:실온"),
            _confirm_action("취소", "취소")
        ]
        return {"response_text": text, "actions": actions}

    if state.get("intent") == "mcp.pending_add_many_retry":
        return {"response_text": "식재료와 갯수를 함께 말해주세요. 예: 파스타면1, 토마토소스1, 냉동 새우1"}

    if state.get("intent") == "mcp.pending_add_many":
        items = _extract_add_items(state["text"])
        payload = "|".join(f"{item['name']},{item['quantity'] or 1},{item['storage'] or DEFAULT_STORAGE}" for item in items)
        summary = ", ".join(f"{item['name']} {_quantity_text(item['quantity'] or 1)}\uac1c" for item in items)
        text = f"{summary}\ub97c \ub0c9\uc7a5\uace0\uc5d0 \ucd94\uac00\ud560\uae4c\uc694?"
        return {"response_text": text, "actions": [_confirm_action("\ud655\uc778", f"\ud655\uc778:add_ingredients:{payload}"), _confirm_action("\ucde8\uc18c", "\ucde8\uc18c")]}


    if not state["user_id"]:
        return {"response_text": LOGIN_REQUIRED_REPLY}

    messages = state.get("messages") or [HumanMessage(content=state["text"])]
    if state.get("intent") == "mcp.inventory":
        sys_msg = SystemMessage(content="[절대 규칙]\n1. 식재료 추가 요청 시 수량을 모르면 '몇 개 추가할까요?'만 질문하세요.\n2. 사용자가 수량을 말해주거나 이미 알고 있다면, 텍스트로 대답하지 말고 반드시 `add_ingredient` 도구를 호출하세요.\n3. 절대로 '추가해두었어요', '넣어두세요' 같은 텍스트 답변을 금지합니다. 무조건 도구(Tool)를 실행해야 합니다.")
        if not any(getattr(m, "type", "") == "system" for m in messages):
            messages = [sys_msg] + messages
    elif state.get("intent") == "mcp.calendar":
        sys_msg = SystemMessage(content="당신은 사용자의 일정을 관리하는 비서입니다. 사용자가 캘린더에 일정을 추가해 달라고 요청할 때, 일정의 제목(무엇을 할지)과 날짜 정보가 모두 있다면 절대로 당신이 직접 '등록했습니다'라고 텍스트로 말하지 마세요. **반드시 즉시 add_calendar_event 도구(tool)를 호출해야 합니다.** 도구를 호출해야만 실제 시스템에 등록됩니다.")
        if not any(getattr(m, "type", "") == "system" for m in messages):
            messages = [sys_msg] + messages
    tools_by_intent = {"mcp.inventory": INVENTORY_TOOLS, "mcp.calendar": CALENDAR_TOOLS}
    tools = tools_by_intent.get(state["intent"], [])

    llm = ChatOpenAI(model=settings.OPENAI_MODEL, api_key=settings.OPENAI_API_KEY, temperature=0.0)
    response = llm.bind_tools(tools).invoke(messages)

    if not response.tool_calls:
        resp_data = {"response_text": response.content, "messages": messages + [response]}
        if any(kw in response.content for kw in ("어디에 보관", "보관 방법", "어떻게 보관", "냉장, 냉동, 실온")):
            resp_data["actions"] = [
                _confirm_action("냉장", "냉장"),
                _confirm_action("냉동", "냉동"),
                _confirm_action("실온", "실온")
            ]
        return resp_data

    tool_call = response.tool_calls[0]
    func_name = tool_call["name"]
    args = tool_call["args"]

    from langchain_core.messages import ToolMessage
    
    if func_name == "consume_ingredient":
        raw_name = args.get("ingredient_name", "")
        name = re.sub(r'^\d+\.\s*', '', raw_name).rstrip('은는이가을를')
        quantity = float(args.get("quantity") or 1)
        text = f"{name} {_quantity_text(quantity)}개를 소비 처리할까요?"
        command = f"확인:consume_ingredient:{name}:{quantity}"
        tool_msg = ToolMessage(content="사용자에게 소비 확인 버튼을 띄웠습니다.", tool_call_id=tool_call["id"])
        return {"response_text": text, "actions": [_confirm_action("확인", command), _confirm_action("취소", "취소")], "messages": messages + [response, tool_msg]}

    if func_name == "add_ingredient":
        raw_name = args.get("ingredient_name", "")
        name = re.sub(r'^\d+\.\s*', '', raw_name).rstrip('은는이가을를')
        quantity = args.get("quantity")
        if quantity is None:
            tool_msg = ToolMessage(content="사용자에게 수량을 물어보고 대답을 기다리는 중입니다.", tool_call_id=tool_call["id"])
            return {"response_text": f"{name} 몇 개 추가할까요?", "messages": messages + [response, tool_msg]}
            
        quantity = float(quantity)
        storage_method = args.get("storage_method") or DEFAULT_STORAGE
        text = f"{name} {_quantity_text(quantity)}개를 어디에 보관하여 추가할까요?"
        actions = [
            _confirm_action("냉장", f"확인:add_ingredient:{name}:{quantity}:냉장"),
            _confirm_action("냉동", f"확인:add_ingredient:{name}:{quantity}:냉동"),
            _confirm_action("실온", f"확인:add_ingredient:{name}:{quantity}:실온"),
            _confirm_action("취소", "취소")
        ]
        tool_msg = ToolMessage(content="사용자에게 보관방법 선택 버튼을 띄웠습니다.", tool_call_id=tool_call["id"])
        return {"response_text": text, "actions": actions, "messages": messages + [response, tool_msg]}


        
    if func_name == "add_calendar_event":
        title = args.get("title", "\uc77c\uc815")
        date_str = args.get("date_str", "\uc624\ub298")
        start_at = _calendar_datetime_from_text(state["text"], date_str)
        date_value = start_at.isoformat()
        text = f"'{title}' \uc77c\uc815\uc744 {_calendar_display(start_at)}\uc5d0 \ub4f1\ub85d\ud560\uae4c\uc694?"
        command = f"\ud655\uc778:add_calendar_event:{title}:{date_value}"
        return {"response_text": text, "actions": [_confirm_action("\ud655\uc778", command), _confirm_action("\ucde8\uc18c", "\ucde8\uc18c")], "messages": messages + [response]}
    return {"response_text": "\uc544\uc9c1 \uc9c0\uc6d0\ud558\uc9c0 \uc54a\ub294 \ucc57\ubd07 \uc791\uc5c5\uc774\uc5d0\uc694.", "messages": messages + [response]}


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
    if svc._requires_login("recipe.recommend", state["text"]) and not state["user_id"]:
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
        "response_text": "\uc601\uc218\uc99d\uc740 \ud30c\uc77c \uc5c5\ub85c\ub4dc\uac00 \ud544\uc694\ud574\uc11c \uc544\ub798 \ubc84\ud2bc\uc744 \ub20c\ub7ec \uc601\uc218\uc99d \ub4f1\ub85d \ud654\uba74\uc73c\ub85c \uc774\ub3d9\ud574\uc8fc\uc138\uc694.",
        "actions": [{"label": "\uc601\uc218\uc99d \ub4f1\ub85d\ud558\ub7ec \uac00\uae30", "url": "/receipt-ocr"}],
    }


def general_node(state: GraphState) -> dict:
    """지원 범위 밖 질문이나 일상 대화에 대해 LLM으로 자연스럽게 응답합니다."""
    from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
    
    llm = ChatOpenAI(model=settings.OPENAI_MODEL, api_key=settings.OPENAI_API_KEY, temperature=0.7)
    sys_msg = SystemMessage(content="당신은 요리와 냉장고 관리를 돕는 친절한 비서 챗봇입니다. 사용자의 일상적인 인사나 대화에 다정하고 친절하게 1~2문장으로 짧게 답하세요. 대화 끝에는 자연스럽게 요리나 식재료 관리에 도움이 필요한지 가볍게 물어보세요.")
    
    messages = [sys_msg]
    if "history" in state and state["history"]:
        for msg in state["history"][-4:]:
            if getattr(msg, "role", "") == "user":
                messages.append(HumanMessage(content=getattr(msg, "text", "")))
            elif getattr(msg, "role", "") == "bot":
                messages.append(AIMessage(content=getattr(msg, "text", "")))
                
    messages.append(HumanMessage(content=state["text"]))
    
    try:
        response = llm.invoke(messages)
        return {"response_text": response.content}
    except Exception:
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
