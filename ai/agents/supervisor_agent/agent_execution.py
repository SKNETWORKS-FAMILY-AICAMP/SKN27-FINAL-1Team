import json
import logging
from typing import Any

from pydantic import ValidationError

from app.backend.schemas.chat import AgentResult

logger = logging.getLogger(__name__)

_LOW_QUALITY_RESPONSE_MARKERS = (
    "실행할 도구가 연결되지 않았어요",
    "챗봇 연결 중 문제가 생겼어요",
    "요청을 처리하는 중 문제가 생겼어요",
)

def _agent_result_needs_retry(agent_result: Any) -> bool:
    """Agent 응답이 비어 있거나 명시적으로 실패했는지 확인합니다."""
    if not isinstance(agent_result, dict):
        return True

    slots = agent_result.get("slots") if isinstance(agent_result.get("slots"), dict) else {}
    status = str(agent_result.get("status") or slots.get("agent_status") or slots.get("guide_status") or "").lower()
    if agent_result.get("ok") is False or status == "error" or agent_result.get("error"):
        return True

    response_text = agent_result.get("response_text") or agent_result.get("message")
    if not isinstance(response_text, str) or not response_text.strip():
        return True
    return any(marker in response_text for marker in _LOW_QUALITY_RESPONSE_MARKERS)


def _agent_result_failed(agent_result: Any) -> bool:
    """Agent 실행 결과가 복합 요청의 성공 결과로 사용할 수 있는지 확인합니다."""
    if not isinstance(agent_result, dict):
        return True
    slots = agent_result.get("slots") if isinstance(agent_result.get("slots"), dict) else {}
    status = str(agent_result.get("status") or slots.get("agent_status") or slots.get("guide_status") or "").lower()
    return agent_result.get("ok") is False or status in {"error", "unsupported"} or bool(agent_result.get("error"))


def _run_agent_with_retry(call: Any, *, enabled: bool = True) -> Any:
    """안전한 조회 요청이 실패하면 한 번만 재호출하고 두 번째 실패를 응답으로 변환합니다."""
    if not enabled:
        return call()

    retried = False
    for attempt in range(2):
        try:
            result = call()
        except Exception:
            if attempt == 0:
                retried = True
                continue
            logger.exception("Agent 재시도까지 실패했습니다.")
            result = {"status": "error", "response_text": "요청을 처리하는 중 문제가 생겼어요. 잠시 후 다시 시도해주세요."}
        else:
            if _agent_result_needs_retry(result):
                if attempt == 0:
                    retried = True
                    continue
                result = {
                    **(result if isinstance(result, dict) else {}),
                    "status": "error",
                    "response_text": "요청을 처리하는 중 문제가 생겼어요. 잠시 후 다시 시도해주세요.",
                }
        break

    if retried and isinstance(result, dict):
        result = {
            **result,
            "slots": {**(result.get("slots") or {}), "agent_retry_count": 1},
        }
    return result


def _normalize_agent_result(
    agent_result: Any,
    *,
    inherited_slots: dict | None = None,
    error_reply: str = "요청을 처리하는 중 문제가 생겼어요. 잠시 후 다시 시도해주세요.",
) -> dict[str, Any]:
    """서로 다른 Agent 응답을 Supervisor GraphState 공통 형식으로 정규화합니다."""
    if not isinstance(agent_result, dict):
        return {"response_text": error_reply, "actions": [], "sources": [], "slots": inherited_slots or {}}

    try:
        agent_result = AgentResult.model_validate(agent_result).model_dump(exclude_none=True)
    except ValidationError:
        logger.exception("Agent 공통 응답 스키마 검증에 실패했습니다.")
        return {"response_text": error_reply, "actions": [], "sources": [], "slots": inherited_slots or {}}
    ui = agent_result.get("ui") if isinstance(agent_result.get("ui"), dict) else {}
    status = agent_result.get("status")
    failed = agent_result.get("ok") is False or status == "error" or bool(agent_result.get("error"))
    response_text = agent_result.get("response_text") or agent_result.get("message") or ""
    if failed and not response_text:
        response_text = error_reply

    actions = agent_result.get("actions")
    if not isinstance(actions, list):
        actions = ui.get("actions") if isinstance(ui.get("actions"), list) else []
    sources = agent_result.get("sources")
    if not isinstance(sources, list):
        sources = ui.get("sources") if isinstance(ui.get("sources"), list) else []

    slots = {**(inherited_slots or {}), **(agent_result.get("slots") or {})}
    if status:
        slots["agent_status"] = status
    if agent_result.get("action"):
        slots["agent_action"] = agent_result["action"]

    result = {
        "response_text": response_text or error_reply,
        "actions": [action for action in actions if isinstance(action, dict)],
        "sources": [source for source in sources if isinstance(source, dict)],
        "slots": slots,
    }
    if isinstance(agent_result.get("pending_action"), dict):
        result["pending_action"] = agent_result["pending_action"]
    return result

def _merge_agent_results(*results: dict[str, Any]) -> dict[str, Any]:
    """여러 Agent 응답을 중복 없이 하나의 GraphState 응답으로 합칩니다."""
    response_text = "\n\n".join(
        result.get("response_text", "").strip()
        for result in results
        if result.get("response_text", "").strip()
    )
    actions = list({
        json.dumps(action, ensure_ascii=False, sort_keys=True, default=str): action
        for result in results
        for action in result.get("actions") or []
    }.values())
    sources = list({
        json.dumps(source, ensure_ascii=False, sort_keys=True, default=str): source
        for result in results
        for source in result.get("sources") or []
    }.values())
    slots = {}
    for result in results:
        for key, value in (result.get("slots") or {}).items():
            # 먼저 실행된 Agent의 문맥 슬롯을 뒤 작업이 덮어쓰지 않게 합니다.
            slots.setdefault(key, value)

    merged = {"response_text": response_text}
    if actions:
        merged["actions"] = actions
    if sources:
        merged["sources"] = sources
    if slots:
        merged["slots"] = slots
    return merged
