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
from app.backend.schemas.chat_state import GraphState

logger = logging.getLogger(__name__)
# 챗봇 기본 응답 문구
LOGIN_REQUIRED_REPLY = "로그인이 필요한 질문이에요. 비회원 상태에서는 보관법이나 일반 레시피 검색을 이용할 수 있어요."
GENERAL_REPLY = "요리와 식재료 관련 질문을 물어봐 주세요.\n예: 양파 보관법, 감자튀김 에어프라이기 시간, 두부 레시피"
CANCEL_REPLY = "알겠습니다. 작업을 취소하겠습니다."

# 확인/취소 액션 키워드
CONFIRM_PREFIX = "확인:"
CANCEL_WORDS = ("취소", "아니", "아니요", "취소할게")

# 의도 분류용 키워드
INVENTORY_ACTION_WORDS = (
    "먹었어",
    "다썼어",
    "다먹었어",
    "버렸어",
    "소비했",
    "사용했",
    "썼어",
    "추가",
    "추가해줘",
    "등록",
    "등록해줘",
    "넣었어",
    "넣어줘",
    "샀어",
    "삿어",
    "사왔어",
    "구매했",
    "삭제",
    "폐기",
    "지워",
)
CALENDAR_WORDS = ("일정", "캘린더")
DELETE_WORDS = ("삭제", "폐기", "지워", "버려")
CONSUME_WORDS = ("먹었어", "다썼어", "다먹었어", "소비했", "사용했", "썼어")
INVENTORY_LIST_WORDS = ("뭐 있어", "뭐 있지", "뭐있", "뭐잇", "머있", "머잇", "뭐이", "목록", "현재 재료", "현재 냉장고")
EXPIRING_WORDS = ("임박", "소비기한", "유통기한", "기한", "적게남", "남은거", "먼저먹", "먹어야", "d-day", "디데이")
ADD_WORDS = ("추가", "등록", "넣", "샀", "삿", "사왔", "구매")

# 식재료 입력 파싱용 기본값
DEFAULT_STORAGE = "냉장"
STORAGE_KEYS = ("냉장", "냉동", "실온")
KOREAN_QUANTITIES = {
    "한": 1,
    "하나": 1,
    "두": 2,
    "둘": 2,
    "세": 3,
    "셋": 3,
    "네": 4,
    "넷": 4,
}


def _normalize_text(text: str) -> str:
    """사용자 문장을 간단 비교할 수 있도록 정리합니다."""
    return text.replace(" ", "").lower()


def _confirm_action(label: str, command: str) -> dict:
    """쓰기 작업 전 사용자 확인 버튼을 만듭니다."""
    return {"label": label, "data": {"message": command}}


def _inventory_refresh_action() -> dict:
    """냉장고 목록을 다시 불러오도록 프론트에 전달할 액션을 만듭니다."""
    return {"label": "냉장고 새로고침", "data": {"refreshInventory": True}}


def _quantity_text(quantity: float) -> str:
    """수량을 사용자가 읽기 좋은 형태로 바꿉니다."""
    number = float(quantity or 1)
    return str(int(number)) if number.is_integer() else str(number)



def _extract_quantity(text: str) -> float | None:
    """사용자 문장에서 수량만 간단히 추출합니다."""
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:개|g|kg|ml|l)?", text, re.IGNORECASE)
    if match:
        return float(match.group(1))
    normalized = text.replace(" ", "")
    for word, quantity in KOREAN_QUANTITIES.items():
        if f"{word}개" in normalized:
            return float(quantity)
    return None




def _extract_delete_name(text: str) -> str:
    """삭제/폐기 문장에서 식재료명만 간단히 추출합니다."""
    target = text
    for word in DELETE_WORDS:
        if word in target:
            target = target.split(word, 1)[0]
            break
    for token in ("냉장고에서", "냉장고에", "냉장고", "재료", "식재료", "어제", "오늘", "방금"):
        target = target.replace(token, " ")
    return target.strip().rstrip("을를은는이가")




def _extract_consume_name(text: str) -> str:
    """소비 문장에서 식재료명만 간단히 추출합니다."""
    target = text
    for word in CONSUME_WORDS:
        if word in target:
            target = target.split(word, 1)[0]
            break
    target = re.sub(r"\d+(?:\.\d+)?\s*(?:개|g|kg|ml|l)?", " ", target, flags=re.IGNORECASE)
    for token in ("냉장고에서", "냉장고에", "냉장고", "재료", "식재료", "어제", "오늘", "방금"):
        target = target.replace(token, " ")
    return target.strip(" ,/\t\n을를은는이가도")


def _strip_add_name(name: str) -> str:
    """추가 문장에서 식재료명에 붙은 불필요한 단어를 정리합니다."""
    cleaned = name
    for token in ('냉장고에서', '냉장고에', '냉장고', '재료', '식재료', '어제', '오늘', '방금'):
        cleaned = cleaned.replace(token, " ")
    for storage in STORAGE_KEYS:
        cleaned = re.sub(rf"(?<![가-힣A-Za-z0-9]){storage}(?![가-힣A-Za-z0-9])", " ", cleaned)
    cleaned = cleaned.strip(" ,/\t\n을를은는이가")
    # '양파도 추가해줘'처럼 이어 말한 조사만 제거하되, 포도/아보카도 같은 재료명은 보존합니다.
    if cleaned.endswith("도") and (" " in cleaned or (len(cleaned) > 2 and not cleaned.endswith(('포도', '아보카도')))):
        cleaned = cleaned[:-1].rstrip()
    return cleaned


def _extract_add_items(text: str) -> list[dict]:
    """추가 요청에서 식재료명, 수량, 보관 위치를 간단히 추출합니다."""
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
        name = re.sub(r"\d+(?:\.\d+)?\s*(?:개|g|kg|ml|l)?", " ", part, flags=re.IGNORECASE)
        for word in KOREAN_QUANTITIES:
            name = name.replace(f"{word}개", " ")
        name = _strip_add_name(name)
        if name:
            items.append({"name": name, "quantity": quantity, "storage": storage})
    return items


def _pending_calendar_from_history(history) -> tuple[str, str] | None:
    """최근 봇의 일정 등록 확인 문구에서 제목과 날짜를 찾습니다."""
    text = _latest_bot_text(history)
    match = re.search(r"'(.+?)'\s+일정을\s+(\d{4}-\d{2}-\d{2} \d{2}:\d{2})에\s+등록할까요", text)
    return (match.group(1), match.group(2)) if match else None

def _pending_add_many_from_history(history) -> bool:
    """최근 봇 응답이 여러 식재료 수량을 기다리는지 확인합니다."""
    return "각 식재료의 수량" in _latest_bot_text(history)

def _is_quantity_only_list(text: str) -> bool:
    """여러 재료 추가 대기 중 수량만 나열한 응답인지 확인합니다."""
    parts = [part.strip() for part in re.split(r"[,/]", text) if part.strip()]
    return len(parts) > 1 and all(
        _extract_quantity(part) is not None
        and not _strip_add_name(re.sub(r"\d+(?:\.\d+)?\s*(?:개|g|kg|ml|l)?", " ", part, flags=re.IGNORECASE))
        for part in parts
    )

def _latest_bot_text(history) -> str:
    """가장 최근 봇 응답만 후속 작업 대기 상태로 확인합니다."""
    for message in reversed(history or []):
        if getattr(message, "role", "") == "bot":
            return getattr(message, "text", "")
    return ""

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
    """최근 봇의 보관 위치 질문에서 추가 대기 중인 식재료명과 수량을 찾습니다."""
    pattern = r"(.+?)\s+(\d+(?:\.\d+)?)개를\s+어디에\s+보관"
    match = re.search(pattern, _latest_bot_text(history))
    return (match.group(1).strip(), float(match.group(2))) if match else None


def _pending_add_from_history(history) -> str | None:
    """최근 봇의 수량 질문에서 추가 대기 중인 식재료명을 찾습니다."""
    patterns = (
        r"(.+?)(?:을|를)\s*몇\s*개.*추가",
        r"(.+?)\s*몇\s*개.*추가",
    )
    text = _latest_bot_text(history)
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip(" \"'.,!?을를")
    return None


def _pending_consume_from_history(history) -> str | None:
    """최근 봇의 수량 질문에서 소비 대기 중인 식재료명을 찾습니다."""
    match = re.search(r"(.+?)(?:을|를) 몇 개 (?:먹|소비)", _latest_bot_text(history))
    return match.group(1).strip() if match else None

def _parse_calendar_date(date_str: str) -> date:
    """챗봇이 뽑은 짧은 날짜 표현을 캘린더 날짜로 변환합니다."""
    text = (date_str or "오늘").strip()
    today = date.today()
    if "모레" in text:
        return today + timedelta(days=2)
    if "내일" in text:
        return today + timedelta(days=1)
    if "오늘" in text:
        return today
    month_day = re.search(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일", text)
    if month_day:
        month, day = map(int, month_day.groups())
        return date(today.year, month, day)
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return today


def _has_calendar_date_text(text: str) -> bool:
    """사용자 원문에 날짜 표현이 있는지 확인합니다."""
    return bool(
        any(word in text for word in ("오늘", "내일", "모레"))
        or re.search(r"\d{1,2}\s*월\s*\d{1,2}\s*일", text)
        or re.search(r"\d{4}-\d{2}-\d{2}", text)
    )


def _calendar_datetime_from_text(text: str, fallback: str) -> datetime:
    """사용자 원문을 우선해 캘린더 일정 시작 시간을 계산합니다."""
    base_date = _parse_calendar_date(text if _has_calendar_date_text(text) else fallback)
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


def _storage_choice_response(name: str, quantity: float) -> dict:
    """보관 위치 선택 버튼을 만듭니다."""
    text = f"{name} {_quantity_text(quantity)}개를 어디에 보관할까요? 냉장, 냉동, 실온 중에서 알려주세요."
    return {
        "response_text": text,
        "actions": [
            _confirm_action("냉장", f"확인:add_ingredient:{name}:{quantity}:냉장"),
            _confirm_action("냉동", f"확인:add_ingredient:{name}:{quantity}:냉동"),
            _confirm_action("실온", f"확인:add_ingredient:{name}:{quantity}:실온"),
            _confirm_action("취소", "취소"),
        ],
    }


def _handle_inventory_action(state: GraphState) -> dict:
    """식재료 추가/소비는 LLM 대신 규칙 기반으로 처리합니다."""
    text = state["text"]
    normalized = _normalize_text(text)

    if any(word in normalized for word in ADD_WORDS):
        items = _extract_add_items(text)
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
