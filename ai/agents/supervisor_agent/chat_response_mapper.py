"""각 Agent 결과를 챗봇 공통 응답 형식으로 변환합니다."""

import json
import re
from typing import Any

from ai.agents.supervisor_agent.chat_context import _issue_context_token
from ai.agents.supervisor_agent.supervisor_utils import (
    CONFIRM_PREFIX,
    SIGNED_CONFIRM_PREFIX,
    _GUIDE_ACTION_TYPES,
    _GUIDE_TYPE_LABELS,
    _secure_confirm_actions,
)

def _format_guide_tip(tip: str) -> str:
    """긴 가이드 설명을 최대 세 개의 읽기 쉬운 문장으로 정리합니다."""
    sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?。])\s+", tip) if sentence.strip()]
    if len(sentences) <= 1:
        sentences = [sentence.strip() for sentence in re.split(r"[;；]\s*", tip) if sentence.strip()]
    if len(sentences) <= 1:
        return sentences[0] if sentences else tip.strip()
    return "\n".join(f"{index + 1}. {sentence}" for index, sentence in enumerate(sentences[:3]))


def _format_guide_message(agent_result: dict[str, Any]) -> str:
    """Guide Agent의 action과 data를 챗봇에서 읽기 좋은 문장으로 변환합니다."""
    message = agent_result.get("message") or "가이드 정보를 찾지 못했어요."
    if agent_result.get("status") != "success":
        return message

    action = agent_result.get("action") or ""
    data = agent_result.get("data") or {}
    ingredient = data.get("ingredient") or {}
    item_name = ingredient.get("name") or ingredient.get("representative_name") or "식재료"

    if action == "list_seasonal_ingredients":
        month = data.get("month")
        names = [item.get("name") for item in data.get("items", []) if item.get("name")]
        if month and names:
            suffix = " 등" if len(names) > 10 else ""
            return f"{month}월 제철 식재료는 {', '.join(names[:10])}{suffix}이에요."

    if action == "lookup_nutrition":
        nutrition = data.get("nutrition") or {}
        lines = []
        base = nutrition.get("nutrition_base_amount") or nutrition.get("base_amount")
        if base:
            lines.append(f"기준량: {base}")
        for key, label, unit in (
            ("energy_kcal", "열량", "kcal"),
            ("protein_g", "단백질", "g"),
            ("carbohydrate_g", "탄수화물", "g"),
            ("fat_g", "지방", "g"),
            ("sugar_g", "당류", "g"),
            ("sodium_mg", "나트륨", "mg"),
        ):
            value = nutrition.get(key)
            if value is not None:
                lines.append(f"{label}: {value}{unit}")
        if lines:
            return f"{item_name} 영양성분이에요.\n" + "\n".join(lines[:7])

    action_type = _GUIDE_ACTION_TYPES.get(action)
    if not action_type and data.get("guide_type"):
        guide_type = data["guide_type"]
        action_type = (guide_type, _GUIDE_TYPE_LABELS.get(guide_type, "가이드"))
    if action_type:
        guide_type, label = action_type
        guide = (data.get("guides") or {}).get(guide_type) or {}
        tip = guide.get("content")
        if tip:
            return f"{item_name} {label}이에요.\n{_format_guide_tip(tip)}"

    return message


def _guide_result_to_state(agent_result: dict[str, Any]) -> dict[str, Any]:
    """Guide Agent 공통 응답을 Supervisor GraphState 형식으로 변환합니다."""
    status = agent_result.get("status") or "error"
    ui = agent_result.get("ui") or {}
    actions = []
    for action in ui.get("actions") or []:
        label = action.get("label")
        data = dict(action.get("data") or {})
        message = data.get("message") or action.get("value")
        if message:
            data["message"] = message
        for key in ("intent", "guide_type", "original_query"):
            if action.get(key) is not None:
                data[key] = action[key]
        url = action.get("url") or ""
        if label and (message or url):
            actions.append({"label": label, "url": url, "data": data})

    sources = [
        {"title": source.get("title") or "출처", "url": source.get("url") or ""}
        for source in ui.get("sources") or []
        if isinstance(source, dict)
    ]
    if not agent_result.get("ok") or status == "error":
        response_text = "가이드 정보를 조회하는 중 문제가 생겼어요. 잠시 후 다시 시도해주세요."
        actions = []
    else:
        response_text = _format_guide_message(agent_result)

    return {
        "response_text": response_text,
        "actions": actions,
        "sources": sources,
        "slots": {
            "guide_status": status,
            "guide_action": agent_result.get("action"),
        },
    }


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


def _extract_pending_action(final_state: dict[str, Any], actions: list[dict[str, Any]]) -> dict[str, Any] | None:
    """에이전트 결과나 확인 버튼에서 실행 대기 작업을 추출합니다."""
    pending = final_state.get("pending_action")
    if isinstance(pending, dict):
        return pending
    if pending:
        return {"action": str(pending)}
    for action in actions:
        command = (action.get("data") or {}).get("message")
        if isinstance(command, str) and command.startswith((CONFIRM_PREFIX, SIGNED_CONFIRM_PREFIX)):
            return {"command": command}
    return None


def _auth_status_response(user_id: int | None) -> dict[str, Any]:
    """현재 로그인 상태를 챗봇 공통 응답으로 반환합니다."""
    reply = "현재 로그인된 상태예요." if user_id else "현재 비로그인 상태예요. 보관법이나 일반 레시피 검색은 이용할 수 있어요."
    return {
        "intent": "auth.status",
        "reply": reply,
        "actions": [],
        "sources": [],
        "slots": {},
        "pending_action": None,
    }


def _chat_response_from_state(final_state: dict[str, Any], session_id: str | None = None) -> dict[str, Any]:
    """LangGraph 최종 상태를 채팅 API 응답 형식으로 변환합니다."""
    actions = _secure_confirm_actions(final_state.get("actions") or [], final_state.get("user_id"))
    response = {
        "intent": final_state.get("intent", "general"),
        "reply": final_state.get("response_text", ""),
        "actions": actions,
        "sources": final_state.get("sources") or [],
        "slots": final_state.get("slots") or {},
        "pending_action": _extract_pending_action(final_state, actions),
    }

    context_token = _issue_context_token(response, final_state.get("user_id"), session_id)
    if context_token:
        response["context_token"] = context_token
    return response


def _chat_error_response() -> dict[str, Any]:
    """Supervisor 실행 실패 시 사용할 공통 채팅 응답을 반환합니다."""
    return {
        "intent": "error",
        "reply": "요청을 처리하는 중 문제가 생겼어요. 잠시 후 다시 시도해주세요.",
        "actions": [],
        "sources": [],
        "slots": {},
        "pending_action": None,
    }


def _alarm_result_to_state(agent_result: dict[str, Any]) -> dict[str, Any]:
    """Alarm Agent 공통 응답을 Supervisor GraphState 형식으로 변환합니다."""
    response_text = _format_calendar_events(agent_result.get("data", {})) if agent_result.get("intent") == "calendar.list" else None
    response_text = response_text or agent_result.get("message", "요청을 처리했습니다.")
    actions = []

    for action in (agent_result.get("ui") or {}).get("actions") or []:
        label = action.get("label", "")
        value = action.get("value", {})
        if isinstance(value, dict):
            if value.get("action") == "cancel":
                message = "취소"
            else:
                payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
                message = f"확인:alarm:{payload}"
        else:
            message = str(value)
        actions.append({"label": label, "data": {"message": message}})

    result = {"response_text": response_text, "status": agent_result.get("status") or ("error" if agent_result.get("ok") is False else "success")}
    if actions:
        result["actions"] = actions
    return result
