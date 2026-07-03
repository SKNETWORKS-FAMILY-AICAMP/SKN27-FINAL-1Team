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
    for token in ("\ub0c9\uc7a5\uace0\uc5d0\uc11c", "\ub0c9\uc7a5\uace0\uc5d0", "\ub0c9\uc7a5\uace0", "\uc7ac\ub8cc", "\uc2dd\uc7ac\ub8cc", "\uc5b4\uc81c", "\uc624\ub298", "\ubc29\uae08"):
        target = target.replace(token, " ")
    return target.strip().rstrip("\uc744\ub97c\uc740\ub294\uc774\uac00")




def _extract_consume_name(text: str) -> str:
    """소비 문장에서 식재료명만 간단히 추출합니다."""
    target = text
    for word in CONSUME_WORDS:
        if word in target:
            target = target.split(word, 1)[0]
            break
    target = re.sub(r"\d+(?:\.\d+)?\s*(?:\uac1c|g|kg|ml|l)?", " ", target, flags=re.IGNORECASE)
    for token in ("\ub0c9\uc7a5\uace0\uc5d0\uc11c", "\ub0c9\uc7a5\uace0\uc5d0", "\ub0c9\uc7a5\uace0", "\uc7ac\ub8cc", "\uc2dd\uc7ac\ub8cc", "\uc5b4\uc81c", "\uc624\ub298", "\ubc29\uae08"):
        target = target.replace(token, " ")
    return target.strip(" ,/\t\n\uc744\ub97c\uc740\ub294\uc774\uac00\ub3c4")


def _strip_add_name(name: str) -> str:
    """추가 문장에서 식재료명에 붙은 불필요한 단어를 정리합니다."""
    cleaned = name
    for token in ('냉장고에서', '냉장고에', '냉장고', '재료', '식재료', '어제', '오늘', '방금'):
        cleaned = cleaned.replace(token, " ")
    for storage in STORAGE_KEYS:
        cleaned = re.sub(rf"(?<![\uac00-\ud7a3A-Za-z0-9]){storage}(?![\uac00-\ud7a3A-Za-z0-9])", " ", cleaned)
    cleaned = cleaned.strip(" ,/\t\n\uc744\ub97c\uc740\ub294\uc774\uac00")
    # '양파도 추가해줘'처럼 이어 말한 조사만 제거하되, 포도/아보카도 같은 재료명은 보존합니다.
    if cleaned.endswith("\ub3c4") and (" " in cleaned or (len(cleaned) > 2 and not cleaned.endswith(('포도', '아보카도')))):
        cleaned = cleaned[:-1].rstrip()
    return cleaned


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


def _pending_calendar_from_history(history) -> tuple[str, str] | None:
    """최근 봇의 일정 등록 확인 문구에서 제목과 날짜를 찾습니다."""
    text = _latest_bot_text(history)
    match = re.search(r"'(.+?)'\s+\uc77c\uc815\uc744\s+(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\uc5d0\s+\ub4f1\ub85d\ud560\uae4c\uc694", text)
    return (match.group(1), match.group(2)) if match else None

def _pending_add_many_from_history(history) -> bool:
    """최근 봇 응답이 여러 식재료 수량을 기다리는지 확인합니다."""
    return "각 식재료의 수량" in _latest_bot_text(history)

def _is_quantity_only_list(text: str) -> bool:
    """여러 재료 추가 대기 중 수량만 나열한 응답인지 확인합니다."""
    parts = [part.strip() for part in re.split(r"[,/]", text) if part.strip()]
    return len(parts) > 1 and all(
        _extract_quantity(part) is not None
        and not _strip_add_name(re.sub(r"\d+(?:\.\d+)?\s*(?:\uac1c|g|kg|ml|l)?", " ", part, flags=re.IGNORECASE))
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
        r"(.+?)(?:\uc744|\ub97c)\s*\uba87\s*\uac1c.*\ucd94\uac00",
        r"(.+?)\s*\uba87\s*\uac1c.*\ucd94\uac00",
    )
    text = _latest_bot_text(history)
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip(" \"'.,!?\uc744\ub97c")
    return None


def _pending_consume_from_history(history) -> str | None:
    """최근 봇의 수량 질문에서 소비 대기 중인 식재료명을 찾습니다."""
    match = re.search(r"(.+?)(?:\uc744|\ub97c) \uba87 \uac1c (?:\uba39|\uc18c\ube44)", _latest_bot_text(history))
    return match.group(1).strip() if match else None

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
    month_day = re.search(r"(\d{1,2})\s*\uc6d4\s*(\d{1,2})\s*\uc77c", text)
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
        any(word in text for word in ("\uc624\ub298", "\ub0b4\uc77c", "\ubaa8\ub808"))
        or re.search(r"\d{1,2}\s*\uc6d4\s*\d{1,2}\s*\uc77c", text)
        or re.search(r"\d{4}-\d{2}-\d{2}", text)
    )


def _calendar_datetime_from_text(text: str, fallback: str) -> datetime:
    """사용자 원문을 우선해 캘린더 일정 시작 시간을 계산합니다."""
    base_date = _parse_calendar_date(text if _has_calendar_date_text(text) else fallback)
    time_match = re.search(r"(\uc624\uc804|\uc624\ud6c4)?\s*(\d{1,2})\s*\uc2dc(?:\s*(\d{1,2})\s*\ubd84)?", text)
    hour = 9
    minute = 0
    if time_match:
        meridiem, hour_text, minute_text = time_match.groups()
        hour = int(hour_text)
        minute = int(minute_text or 0)
        if meridiem == "\uc624\ud6c4" and hour < 12:
            hour += 12
        if meridiem == "\uc624\uc804" and hour == 12:
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
    text = f"{name} {_quantity_text(quantity)}\uac1c\ub97c \uc5b4\ub514\uc5d0 \ubcf4\uad00\ud560\uae4c\uc694? \ub0c9\uc7a5, \ub0c9\ub3d9, \uc2e4\uc628 \uc911\uc5d0\uc11c \uc54c\ub824\uc8fc\uc138\uc694."
    return {
        "response_text": text,
        "actions": [
            _confirm_action("\ub0c9\uc7a5", f"\ud655\uc778:add_ingredient:{name}:{quantity}:\ub0c9\uc7a5"),
            _confirm_action("\ub0c9\ub3d9", f"\ud655\uc778:add_ingredient:{name}:{quantity}:\ub0c9\ub3d9"),
            _confirm_action("\uc2e4\uc628", f"\ud655\uc778:add_ingredient:{name}:{quantity}:\uc2e4\uc628"),
            _confirm_action("\ucde8\uc18c", "\ucde8\uc18c"),
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
                return {"response_text": "\uac01 \uc2dd\uc7ac\ub8cc\uc758 \uc218\ub7c9\uc744 \uc54c\ub824\uc8fc\uc2dc\uba74 \ucd94\uac00\ud574\ub4dc\ub9b4\uac8c\uc694."}
            payload = "|".join(f"{item['name']},{item['quantity']},{item['storage'] or DEFAULT_STORAGE}" for item in items)
            summary = ", ".join(f"{item['name']} {_quantity_text(item['quantity'])}\uac1c" for item in items)
            return {"response_text": f"{summary}\ub97c \ub0c9\uc7a5\uace0\uc5d0 \ucd94\uac00\ud560\uae4c\uc694?", "actions": [_confirm_action("\ud655\uc778", f"\ud655\uc778:add_ingredients:{payload}"), _confirm_action("\ucde8\uc18c", "\ucde8\uc18c")]}
        if len(items) == 1:
            item = items[0]
            if item["quantity"] is None:
                return {"response_text": f"{item['name']}\ub97c \uba87 \uac1c \ucd94\uac00\ud558\uc2dc\uaca0\uc5b4\uc694?"}
            if not item["storage"]:
                return _storage_choice_response(item["name"], item["quantity"])
            text = f"{item['name']} {_quantity_text(item['quantity'])}\uac1c\ub97c {item['storage']}\uc5d0 \ucd94\uac00\ud560\uae4c\uc694?"
            command = f"\ud655\uc778:add_ingredient:{item['name']}:{item['quantity']}:{item['storage']}"
            return {"response_text": text, "actions": [_confirm_action("\ud655\uc778", command), _confirm_action("\ucde8\uc18c", "\ucde8\uc18c")]}
        return {"response_text": "\uc5b4\ub5a4 \uc2dd\uc7ac\ub8cc\ub97c \ucd94\uac00\ud560\uae4c\uc694? \uc2dd\uc7ac\ub8cc\uba85\uacfc \uc218\ub7c9\uc744 \ud568\uaed8 \uc54c\ub824\uc8fc\uc138\uc694."}

    if any(word in normalized for word in CONSUME_WORDS):
        name = _extract_consume_name(text)
        if not name:
            return {"response_text": "\uc5b4\ub5a4 \uc2dd\uc7ac\ub8cc\ub97c \uc18c\ube44 \ucc98\ub9ac\ud560\uae4c\uc694?"}
        quantity = _extract_quantity(text)
        if quantity is None:
            return {"response_text": f"{name}\ub97c \uba87 \uac1c \uc18c\ube44\ud560\uae4c\uc694?"}
        command = f"\ud655\uc778:consume_ingredient:{name}:{quantity}"
        return {"response_text": f"{name} {_quantity_text(quantity)}\uac1c\ub97c \uc18c\ube44 \ucc98\ub9ac\ud560\uae4c\uc694?", "actions": [_confirm_action("\ud655\uc778", command), _confirm_action("\ucde8\uc18c", "\ucde8\uc18c")]}

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
        text = f"{name} \ud3d0\uae30 \ucc98\ub9ac\ud560\uae4c\uc694?"
        command = f"\ud655\uc778:delete_ingredient:{name}"
        return {"response_text": text, "actions": [_confirm_action("\ud655\uc778", command), _confirm_action("\ucde8\uc18c", "\ucde8\uc18c")]}

    if state.get("intent") == "mcp.pending_calendar":
        pending = _pending_calendar_from_history(state.get("history", []))
        if not pending:
            return {"response_text": GENERAL_REPLY}
        title, fallback = pending
        start_at = _calendar_datetime_from_text(state["text"], fallback)
        date_value = start_at.isoformat()
        text = f"'{title}' \uc77c\uc815\uc744 {_calendar_display(start_at)}\uc5d0 \ub4f1\ub85d\ud560\uae4c\uc694?"
        command = f"\ud655\uc778:add_calendar_event:{title}:{date_value}"
        return {"response_text": text, "actions": [_confirm_action("\ud655\uc778", command), _confirm_action("\ucde8\uc18c", "\ucde8\uc18c")]}

    if state.get("intent") == "mcp.pending_consume":
        name = _pending_consume_from_history(state.get("history", [])) or ""
        quantity = _extract_quantity(state["text"]) or 1
        text = f"{name} {_quantity_text(quantity)}\uac1c\ub97c \uc18c\ube44 \ucc98\ub9ac\ud560\uae4c\uc694?"
        command = f"\ud655\uc778:consume_ingredient:{name}:{quantity}"
        return {"response_text": text, "actions": [_confirm_action("\ud655\uc778", command), _confirm_action("\ucde8\uc18c", "\ucde8\uc18c")]}

    if state.get("intent") == "mcp.pending_add_storage":
        pending = _pending_add_storage_from_history(state.get("history", []))
        storage = _extract_storage(state["text"]) or DEFAULT_STORAGE
        if not pending:
            return {"response_text": GENERAL_REPLY}
        name, quantity = pending
        text = f"{name} {_quantity_text(quantity)}\uac1c\ub97c {storage}\uc5d0 \ucd94\uac00\ud560\uae4c\uc694?"
        command = f"\ud655\uc778:add_ingredient:{name}:{quantity}:{storage}"
        return {"response_text": text, "actions": [_confirm_action("\ud655\uc778", command), _confirm_action("\ucde8\uc18c", "\ucde8\uc18c")]}

    if state.get("intent") == "mcp.pending_add":
        name = _pending_add_from_history(state.get("history", [])) or ""
        quantity = _extract_quantity(state["text"]) or 1
        storage = _extract_storage(state["text"])
        if not storage:
            return _storage_choice_response(name, quantity)
        text = f"{name} {_quantity_text(quantity)}\uac1c\ub97c {storage}\uc5d0 \ucd94\uac00\ud560\uae4c\uc694?"
        command = f"\ud655\uc778:add_ingredient:{name}:{quantity}:{storage}"
        return {"response_text": text, "actions": [_confirm_action("\ud655\uc778", command), _confirm_action("\ucde8\uc18c", "\ucde8\uc18c")]}

    if state.get("intent") == "mcp.pending_add_many_retry":
        return {"response_text": "\uc2dd\uc7ac\ub8cc\uc640 \uac2f\uc218\ub97c \ud568\uaed8 \ub9d0\ud574\uc8fc\uc138\uc694. \uc608: \ud30c\uc2a4\ud0c0\uba741, \ud1a0\ub9c8\ud1a0\uc18c\uc2a41, \ub0c9\ub3d9 \uc0c8\uc6b01"}

    if state.get("intent") == "mcp.pending_add_many":
        items = _extract_add_items(state["text"])
        payload = "|".join(f"{item['name']},{item['quantity'] or 1},{item['storage'] or DEFAULT_STORAGE}" for item in items)
        summary = ", ".join(f"{item['name']} {_quantity_text(item['quantity'] or 1)}\uac1c" for item in items)
        text = f"{summary}\ub97c \ub0c9\uc7a5\uace0\uc5d0 \ucd94\uac00\ud560\uae4c\uc694?"
        return {"response_text": text, "actions": [_confirm_action("\ud655\uc778", f"\ud655\uc778:add_ingredients:{payload}"), _confirm_action("\ucde8\uc18c", "\ucde8\uc18c")]}

    if not state["user_id"]:
        return {"response_text": LOGIN_REQUIRED_REPLY}

    if state.get("intent") == "mcp.inventory":
        return _handle_inventory_action(state)

    messages = state.get("messages") or [HumanMessage(content=state["text"])]
    if state.get("intent") == "mcp.calendar":
        sys_msg = SystemMessage(content="\ub2f9\uc2e0\uc740 \uc0ac\uc6a9\uc790\uc758 \uc77c\uc815\uc744 \uad00\ub9ac\ud558\ub294 \ube44\uc11c\uc785\ub2c8\ub2e4. \uc0ac\uc6a9\uc790\uac00 \uce98\ub9b0\ub354\uc5d0 \uc77c\uc815\uc744 \ucd94\uac00\ud574 \ub2ec\ub77c\uace0 \uc694\uccad\ud560 \ub54c, \uc77c\uc815\uc758 \uc81c\ubaa9\uacfc \ub0a0\uc9dc \uc815\ubcf4\uac00 \ubaa8\ub450 \uc788\ub2e4\uba74 \ubc18\ub4dc\uc2dc add_calendar_event \ub3c4\uad6c\ub97c \ud638\ucd9c\ud558\uc138\uc694.")
        if not any(getattr(m, "type", "") == "system" for m in messages):
            messages = [sys_msg] + messages
    llm = ChatOpenAI(model=settings.OPENAI_MODEL, api_key=settings.OPENAI_API_KEY, temperature=0.0)
    response = llm.bind_tools(CALENDAR_TOOLS).invoke(messages)

    if not response.tool_calls:
        return {"response_text": "\uc77c\uc815 \uc81c\ubaa9\uacfc \ub0a0\uc9dc\ub97c \ud568\uaed8 \uc54c\ub824\uc8fc\uc138\uc694."}

    tool_call = response.tool_calls[0]
    if tool_call["name"] == "add_calendar_event":
        args = tool_call["args"]
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
