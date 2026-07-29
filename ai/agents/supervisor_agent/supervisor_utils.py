import json
import re
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any
from uuid import uuid4

from jose import JWTError, jwt

from app.backend.core.config import settings
from ai.agents.supervisor_agent.routing_rules import _normalize_text

# 챗봇 기본 응답 문구
LOGIN_REQUIRED_REPLY = "로그인이 필요한 질문이에요. 비회원 상태에서는 보관법이나 일반 레시피 검색을 이용할 수 있어요."
GENERAL_REPLY = "음식과 관련된 대화만 지원하고 있어요! 요리 레시피, 식재료 보관법, 냉장고 재료 관리 등을 물어봐주세요!"

# 확인/취소 액션 키워드
CONFIRM_PREFIX = "확인:"
SIGNED_CONFIRM_PREFIX = "확인토큰:"
CANCEL_WORDS = ("취소", "아니", "아니요", "아니다", "아니야", "취소할게", "안넣어", "넣지마", "추가하지마")

# 확인 토큰은 짧게 유지하고 한 프로세스 안에서 재사용을 차단합니다.
_CONFIRM_TOKEN_TTL_MINUTES = 10
# ponytail: 단일 프로세스용 저장소이며, 백엔드 다중화 시 Redis SET NX 방식으로 교체합니다.
_consumed_confirm_tokens: dict[str, float] = {}
_confirm_token_lock = Lock()

_CONTEXT_TOKEN_TTL_MINUTES = 120
_TRUSTED_CONTEXT_SLOT_KEYS = {
    "inventory_pending", "inventory_last_action", "ingredient", "keyword",
    "guide_type", "shopping_product", "date", "quantity", "storage", "use_inventory",
    "expiring_ingredients", "shopping_flow",
}

_CONTEXT_SLOT_KEYS = {
    "ingredient.guide": {"ingredient", "keyword", "guide_type"},
    "recipe.recommend": {"ingredient", "keyword", "use_inventory", "expiring_ingredients"},
    "recipe.search": {"ingredient", "keyword"},
    "recipe.pairing": {"ingredient", "keyword"},
    "shopping.compare": {"shopping_product", "shopping_flow"},
    "alarm.notification": {"date", "keyword"},
    "alarm.calendar": {"date", "keyword"},
}

# Guide Agent action을 내부 가이드 유형과 화면 표시 이름으로 매핑합니다.
_GUIDE_ACTION_TYPES = {
    "lookup_storage": ("storage", "보관법"),
    "lookup_prep": ("prep", "손질법"),
    "lookup_washing": ("washing", "세척법"),
    "lookup_freshness": ("freshness", "신선도 확인법"),
    "lookup_intake": ("intake", "섭취 팁"),
}
_GUIDE_TYPE_LABELS = dict(_GUIDE_ACTION_TYPES.values())

# LLM 읽기 분류기가 반환할 수 있는 intent입니다.
_LLM_ROUTE_INTENTS = (
    "receipt.lookup", "receipt.guide", "recipe.recommend", "recipe.pairing", "recipe.search",
    "ingredient.guide", "inventory.expiring", "inventory.list",
    "shopping.current", "shopping.history", "shopping.compare", "shopping.price_help",
    "alarm.notification", "alarm.calendar",
    "food.general", "multi_agent", "general",
)
_LLM_ROUTE_CONFIDENCE = 0.5
_LLM_SLOT_KEYS = {"ingredient", "keyword", "shopping_product", "date", "quantity", "storage", "use_inventory", "guide_type"}
_MULTI_AGENT_TASK_INTENTS = {
    "receipt.lookup",
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
    "inventory.action",
    "inventory.delete",
    "inventory.storage_change",
    "shopping.create",
    "shopping.purchase",
    "shopping.delete_item",
    "shopping.check_item",
    "alarm.notification",
    "alarm.calendar",
}
_WRITE_TASK_INTENTS = {
    "inventory.action",
    "inventory.delete",
    "inventory.storage_change",
    "shopping.create",
    "shopping.purchase",
    "shopping.delete_item",
    "shopping.check_item",
}

_ALARM_TASK_INTENTS = {"alarm.notification", "alarm.calendar"}
_ALARM_WRITE_WORDS = ("등록", "추가", "생성", "삭제", "수정", "변경", "동기화", "읽음 처리")
_ALARM_READ_WORDS = ("조회", "목록", "알려", "보여", "있어", "뭐", "확인", "읽지 않은")


def _infer_task_mode(intent: str, text: str) -> str:
    """Agent intent와 요청 문장을 기준으로 조회 또는 변경 작업을 구분합니다."""
    if intent in _WRITE_TASK_INTENTS:
        return "write"
    if intent not in _ALARM_TASK_INTENTS:
        return "read"

    normalized = re.sub(r"\s+", "", text or "")
    if any(word.replace(" ", "") in normalized for word in _ALARM_WRITE_WORDS):
        return "write"
    if any(word.replace(" ", "") in normalized for word in _ALARM_READ_WORDS):
        return "read"
    # 알람 요청이 모호하면 병렬 실행으로 변경 작업이 섞이지 않도록 보수적으로 처리합니다.
    return "write"

_LLM_ROUTE_SYSTEM_PROMPT = """
You are the Supervisor intent router for the Bobbeori food chatbot.
Return exactly one JSON object. Do not include markdown, code fences, or explanations.

Allowed intents:
{allowed_intents}

Response schema:
{{
  "intent": "one allowed intent",
  "confidence": 0.0,
  "is_follow_up": false,
  "slots": {{
    "ingredient": null,
    "keyword": null,
    "shopping_product": null,
    "date": null,
    "quantity": null,
    "storage": null
  }},
  "tasks": [
    {{
      "id": "task_1",
      "intent": "one allowed task intent",
      "text": "standalone task request",
      "mode": "read or write",
      "depends_on": []
    }}
  ]
}}

Rules:
- recipe.recommend: menu recommendation only when the user explicitly asks to use their fridge or owned ingredients.
- recipe.search: making a named dish, recipe steps, or the original cooking time for a dish. Do not use it for reheating already-cooked or leftover food.
- food.general: use this for general cooking tips or food ideas without the user's fridge context, including leftover rice use, dressing tips, rolling kimbap, and snack ideas.
- recipe.pairing: side dish, pairing food, food that goes well with another dish.
- ingredient.guide: a single ingredient's overview, storage, washing, prep, freshness, nutrition, calories, seasonal food, or ingredient category lists. Do not use it to compare two ingredient or product variants.
- inventory.expiring: expiry, use-by date, expiring ingredients.
- inventory.list: list current fridge ingredients.
- receipt.lookup: recent receipt history, receipt amount, receipt item, or receipt detail lookup guidance.
- receipt.guide: receipt OCR or purchase upload guide.
- shopping.current/history: current shopping list or purchase history lookup.
- shopping.compare: asks for a product price, lowest price, cheaper seller, or why a product is expensive. Put an explicitly named product in slots.shopping_product; leave it null for a context-only follow-up.
- shopping.price_help: asks for general shopping price guidance, including why prices are unavailable or how to find better-value products; never use it for a direct named product price question.
- alarm.notification: notification lookup or management.
- alarm.calendar: calendar schedule lookup or management.
- food.general: food-related unit conversion, ingredient substitution, comparison between ingredient or product variants, reheating already-cooked leftovers, or general cooking knowledge not handled by another intent. Do not use it for storage questions, including leftover food storage.
- Examples: "동물성 휘핑크림과 식물성은 뭐가 달라?" and "남은 치킨 데우는 방법은?" must be food.general.
- multi_agent: a request that needs two or more intents. Split it into standalone tasks.
- Give every task a unique id. Set mode to read or write and list prerequisite task ids in depends_on.
- Independent read tasks have an empty depends_on list. A task that uses another task's result must depend on it.
- A fridge-based recipe request must plan inventory.list first and make recipe.recommend depend on it.
- If a calendar title is omitted after asking for a recipe, make alarm.calendar depend on recipe.recommend and preserve the requested date and time.
- Example: '냉장고 재료 조회해서 레시피 추천해주고 내일 6시 30분에 일정 등록해줘' becomes inventory.list -> recipe.recommend -> alarm.calendar.
- A write task may appear only as part of a multi-step request. It still requires the domain Agent's confirmation flow.
- general: non-food requests or unsupported requests outside the service scope.
- Set is_follow_up=true only when the current message depends on the latest assistant response and omits a subject or entity.
- Use previous_intent metadata from the latest assistant message when the current message is a short follow-up.

Safety:
- For a single DB-changing request, return general because rule-based routing handles it first.
- For a mixed read/write request, return multi_agent and include the write task without claiming it was executed.
- If uncertain, lower confidence below 0.5.
""".format(allowed_intents="\n".join(f"- {intent}" for intent in _LLM_ROUTE_INTENTS))

_INVENTORY_CONFIRM_ACTIONS = {
    "consume_ingredient",
    "add_ingredient",
    "add_ingredient_unchecked",
    "add_ingredients",
    "delete_ingredient",
}

_ALARM_CONFIRM_ACTIONS = {
    "alarm",
    "add_calendar_event",
    "delete_event",
    "sync_daily_events",
}

_SHOPPING_WRITE_INTENTS = {
    "shopping.create",
    "shopping.purchase",
    "shopping.delete_item",
    "shopping.check_item",
}


def _issue_confirm_token(command: str, user_id: int | None) -> str:
    """서버 내부 쓰기 명령을 사용자 귀속 일회용 JWT로 서명합니다."""
    if not user_id or not command.startswith(CONFIRM_PREFIX):
        return command
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "type": "chat_confirm",
            "sub": str(user_id),
            "command": command,
            "jti": uuid4().hex,
            "iat": now,
            "exp": now + timedelta(minutes=_CONFIRM_TOKEN_TTL_MINUTES),
        },
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    return f"{SIGNED_CONFIRM_PREFIX}{token}"


def _verify_and_claim_confirm_token(text: str, user_id: int | None) -> str | None:
    """확인 JWT의 서명, 사용자, 만료, 재사용 여부를 검증하고 내부 명령을 반환합니다."""
    if not user_id or not text.startswith(SIGNED_CONFIRM_PREFIX):
        return None
    try:
        payload = jwt.decode(
            text[len(SIGNED_CONFIRM_PREFIX):],
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except JWTError:
        return None

    command = payload.get("command")
    jti = payload.get("jti")
    expires_at = payload.get("exp")
    if (
        payload.get("type") != "chat_confirm"
        or payload.get("sub") != str(user_id)
        or not isinstance(command, str)
        or not command.startswith(CONFIRM_PREFIX)
        or not isinstance(jti, str)
        or not isinstance(expires_at, (int, float))
    ):
        return None

    now = datetime.now(timezone.utc).timestamp()
    with _confirm_token_lock:
        expired = [token_id for token_id, expiry in _consumed_confirm_tokens.items() if expiry <= now]
        for token_id in expired:
            _consumed_confirm_tokens.pop(token_id, None)
        if jti in _consumed_confirm_tokens:
            return None
        _consumed_confirm_tokens[jti] = float(expires_at)
    return command


def _secure_confirm_actions(actions: list[dict[str, Any]], user_id: int | None) -> list[dict[str, Any]]:
    """응답 액션의 평문 확인 명령을 서명된 확인 토큰으로 교체합니다."""
    secured = []
    for action in actions:
        copied = {**action, "data": dict(action.get("data") or {})}
        command = copied["data"].get("message")
        if isinstance(command, str) and command.startswith(CONFIRM_PREFIX):
            copied["data"]["message"] = _issue_confirm_token(command, user_id)
        secured.append(copied)
    return secured


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
    seen_task_intents = set()
    raw_tasks = payload.get("tasks") or []
    raw_ids = {
        str(task.get("id", "")).strip()
        for task in raw_tasks
        if isinstance(task, dict) and str(task.get("id", "")).strip()
    }
    for index, task in enumerate(raw_tasks, start=1):
        if not isinstance(task, dict):
            continue
        intent = str(task.get("intent", "")).strip()
        if intent not in _MULTI_AGENT_TASK_INTENTS or intent in seen_task_intents:
            continue
        task_text = str(task.get("text", "")).strip() or fallback_text
        if not task_text:
            continue
        task_id = str(task.get("id", "")).strip() or f"task_{index}"
        depends_on = [
            dependency
            for dependency in task.get("depends_on") or []
            if isinstance(dependency, str) and dependency in raw_ids and dependency != task_id
        ]
        tasks.append({
            "id": task_id,
            "intent": intent,
            "text": task_text,
            "mode": _infer_task_mode(intent, task_text),
            "depends_on": list(dict.fromkeys(depends_on)),
        })
        seen_task_intents.add(intent)

    task_by_intent = {task["intent"]: task for task in tasks}
    if "inventory.expiring" in task_by_intent and "recipe.recommend" in task_by_intent:
        dependency_id = task_by_intent["inventory.expiring"]["id"]
        recipe_dependencies = task_by_intent["recipe.recommend"]["depends_on"]
        if dependency_id not in recipe_dependencies:
            recipe_dependencies.append(dependency_id)

    intent = str(payload.get("intent", "")).strip()
    if intent not in _LLM_ROUTE_INTENTS:
        intent = "general"
        confidence = 0.0
    return {
        "intent": intent,
        "confidence": max(0.0, min(confidence, 1.0)),
        "is_follow_up": payload.get("is_follow_up") is True,
        "slots": slots,
        "tasks": tasks,
    }


def _is_llm_route_payload_valid(payload: dict[str, Any], text: str = "") -> bool:
    """LLM 라우팅 결과에 intent별 필수 정보가 있는지 후검증합니다."""
    intent = payload.get("intent")
    slots = payload.get("slots") or {}
    tasks = payload.get("tasks") or []

    if intent not in _LLM_ROUTE_INTENTS:
        return False
    if intent == "multi_agent":
        task_intents = [task.get("intent") for task in tasks if isinstance(task, dict)]
        return len(task_intents) >= 2
    if intent == "shopping.compare" and not (slots.get("shopping_product") or payload.get("is_follow_up")):
        return False
    if intent in {"alarm.notification", "alarm.calendar"}:
        normalized = _normalize_text(text)
        return any(word in normalized for word in ("조회", "목록", "알려", "있어", "확인", "읽지않은", "등록된"))
    return True


def _route_payload(
    intent: str,
    confidence: float = 1.0,
    slots: dict[str, Any] | None = None,
    tasks: list[dict[str, str]] | None = None,
    is_follow_up: bool = False,
) -> dict[str, Any]:
    """LLM 라우팅 결과를 Supervisor 공통 dict 형식으로 반환합니다."""
    return {
        "intent": intent,
        "confidence": confidence,
        "is_follow_up": is_follow_up,
        "slots": slots or {},
        "tasks": tasks or [],
    }


def _inherit_route_context(payload: dict[str, Any], previous_intent: str | None, previous_slots: dict) -> dict[str, Any]:
    """같은 의도의 후속 질문에서 허용된 직전 슬롯만 안전하게 이어받습니다."""
    intent = payload.get("intent")
    if not payload.get("is_follow_up"):
        return payload

    if intent == previous_intent:
        allowed_keys = _CONTEXT_SLOT_KEYS.get(intent, set())
    elif previous_intent == "inventory.expiring" and intent == "recipe.recommend":
        # 임박 재료 조회 직후의 레시피 요청에는 조회된 재료명만 넘깁니다.
        allowed_keys = {"expiring_ingredients"}
    else:
        return payload

    inherited = {key: value for key, value in previous_slots.items() if key in allowed_keys and value is not None}
    current = {key: value for key, value in (payload.get("slots") or {}).items() if value is not None}
    return {**payload, "slots": {**inherited, **current}}


def _rewrite_guide_query(text: str) -> str:
    """Guide Agent가 식재료명과 조회 유형을 정확히 읽도록 질문을 정규화합니다."""
    query = re.sub(r"^.+?(?:말고|대신)\s+", "", text).strip()
    related = re.match(r"^(.+?)(?:와|과)\s*비슷한\s*식재료", query)
    if related:
        return f"{related.group(1).strip()} 뭐가 있어?"
    washing = re.match(r"^(.+?)\s*깨끗하게\s*세척하는\s*방법", query)
    if washing:
        return f"{washing.group(1).strip()} 세척법 알려줘"
    nutrition = re.match(r"^(.+?)\s*영양성분(?:과|와)\s*칼로리", query)
    if nutrition:
        return f"{nutrition.group(1).strip()} 영양성분 알려줘"
    return query


def _is_shopping_show_all_request(text: str) -> bool:
    """생략된 장보기 항목을 모두 보여 달라는 후속 요청인지 확인합니다."""
    normalized = _normalize_text(text)
    return bool(re.search(r"^외\d+개", normalized)) or any(
        word in normalized for word in ("나머지", "전부", "다말해", "다알려", "다보여", "전체")
    )


def _normalize_shopping_create_query(text: str) -> str:
    """장보기 추가 질문의 의문형 어미와 위치 조사로 상품명이 오염되지 않게 정리합니다."""
    query = re.sub(
        r"((?:장보기|쇼핑)(?:\s*목록)?|구매\s*(?:목록|리스트))\s*(?:에서|에)",
        r"\1 ",
        text,
    )
    query = re.sub(r"(?:추가|담아|넣어)(?:할까|할까요)\??$", "추가해줘", query.strip())
    return re.sub(r"\s+", " ", query).strip()


def _is_shopping_history_request(text: str) -> bool:
    """현재 목록이 아니라 과거 구매 기록을 묻는 장보기 요청인지 확인합니다."""
    normalized = _normalize_text(text)
    return any(word in normalized for word in ("기록", "내역", "히스토리", "지난")) and any(
        word in normalized for word in ("산", "구매", "샀")
    )


def _shopping_requested_quantity(text: str) -> str | None:
    """장보기 추가 질문에 명시된 수량을 사용자 안내용 문자열로 추출합니다."""
    match = re.search(r"(\d+(?:\.\d+)?)\s*(개|g|kg|ml|l|봉|팩|묶음)", text, re.IGNORECASE)
    return f"{match.group(1)}{match.group(2)}" if match else None


def _truncated_shopping_count(history: list[Any] | None) -> int | None:
    """직전 장보기 응답에서 생략됐다고 안내한 품목 수를 복원합니다."""
    for message in reversed(history or []):
        role = message.get("role") if isinstance(message, dict) else getattr(message, "role", "")
        content = message.get("text", "") if isinstance(message, dict) else getattr(message, "text", "")
        if role != "bot":
            continue
        match = re.search(r"외\s*(\d+)개", content or "")
        return int(match.group(1)) if match else None
    return None


def _should_use_food_fallback(domain: str, query: str, response_text: str) -> bool:
    """도메인 응답이 질문의 핵심 조건을 놓쳤을 때 일반 음식 답변으로 보완할지 판단합니다."""
    normalized_query = _normalize_text(query)
    normalized_response = _normalize_text(response_text)
    if domain == "recipe":
        if any(marker in normalized_response for marker in ("찾지못", "서비스에없", "추천하기어려", "등록되어있지않")):
            return True
        excluded = re.match(r"^(.+?)(?:없이|대신)", query.strip())
        return bool(excluded and _normalize_text(excluded.group(1)) in normalized_response)
    if domain == "guide":
        if "비슷한식재료" in normalized_query and not any(
            marker in normalized_response for marker in ("관련식재료", "비슷한식재료", "후보")
        ):
            return True
        if any(word in normalized_query for word in ("세척", "영양", "칼로리")) and "비슷한식재료를찾았어요" in normalized_response:
            return True
        if "상했" in normalized_query and not any(
            word in normalized_response for word in ("냄새", "물러", "곰팡이", "변색", "썩")
        ):
            return True
        storage = next((word for word in ("냉장", "냉동", "실온") if word in normalized_query), None)
        return bool(storage and storage not in normalized_response)
    return False


def _normalize_shopping_delete_query(text: str) -> str:
    """장보기 삭제 후속 문장에서 실제 재료명만 남깁니다."""
    cleaned = re.sub(r"\s*(?:빼\s*줘|빼|삭제\s*해줘|삭제|지워\s*줘|지워)\s*[?!.]*$", "", text).strip()
    return re.sub(
        r"^(?:장보기|쇼핑)(?:\s*목록)?(?:에서|에)?\s*",
        "",
        cleaned,
    ).strip()


def _strip_shopping_compare_suffix(text: str) -> str:
    """가격 비교 후속 표현을 제거하고 실제 상품명만 반환합니다."""
    cleaned = re.sub(
        r"\s*더\s*(?:싼|저렴한)\s*(?:곳|데)(?:은|는)?(?:\s*(?:있어|없어)(?:요)?)?\s*\??$",
        "",
        text,
    )
    return re.sub(r"\s*왜\s*(?:이렇게\s*)?비싸(?:요)?\s*\??$", "", cleaned).strip()


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
