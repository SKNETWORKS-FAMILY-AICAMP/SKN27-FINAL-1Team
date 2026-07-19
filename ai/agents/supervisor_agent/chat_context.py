"""Supervisor의 대화 이력, 슬롯, 서명 문맥을 관리합니다."""

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt

from app.backend.core.config import settings
from ai.agents.supervisor_agent.routing_rules import _normalize_text
from ai.agents.supervisor_agent.supervisor_utils import (
    _CONTEXT_TOKEN_TTL_MINUTES,
    _TRUSTED_CONTEXT_SLOT_KEYS,
)

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
    """가장 최근 봇 응답에서 아직 실행을 기다리는 작업만 반환합니다."""
    for message in reversed(history or []):
        if _message_value(message, "role", "") != "bot":
            continue
        pending = _message_value(message, "pending_action")
        return pending if isinstance(pending, dict) else None
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


def _issue_context_token(response: dict[str, Any], user_id: int | None, session_id: str | None) -> str | None:
    """다음 요청에 사용할 최소 대화 문맥을 세션 귀속 JWT로 서명합니다."""
    if not session_id:
        return None
    slots = {
        key: value
        for key, value in (response.get("slots") or {}).items()
        if key in _TRUSTED_CONTEXT_SLOT_KEYS
    }
    safe_slots = json.loads(json.dumps(slots, ensure_ascii=False, default=str))
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "type": "chat_context",
            "sub": str(user_id or "guest"),
            "session_id": session_id,
            "intent": response.get("intent") or "general",
            "slots": safe_slots,
            "iat": now,
            "exp": now + timedelta(minutes=_CONTEXT_TOKEN_TTL_MINUTES),
        },
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def _verify_context_token(token: str | None, user_id: int | None, session_id: str | None) -> dict[str, Any]:
    """서명된 대화 문맥이 현재 사용자와 채팅 세션에 속하는지 검증합니다."""
    if not token or not session_id:
        return {}
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except JWTError:
        return {}
    if (
        payload.get("type") != "chat_context"
        or payload.get("sub") != str(user_id or "guest")
        or payload.get("session_id") != session_id
    ):
        return {}
    return {
        "intent": payload.get("intent") or "general",
        "slots": payload.get("slots") if isinstance(payload.get("slots"), dict) else {},
    }


def _build_chat_state(
    *,
    db: Any,
    user_id: int | None,
    text: str,
    history: list[Any] | None,
    user_settings: Any,
    service: Any,
    trusted_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """LangGraph 실행에 필요한 초기 Supervisor 상태를 구성합니다."""
    return {
        "user_id": user_id,
        "text": text,
        "history": history or [],
        "settings_obj": user_settings,
        "db": db,
        "context_enforced": True,
        "trusted_context": trusted_context or {},
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
