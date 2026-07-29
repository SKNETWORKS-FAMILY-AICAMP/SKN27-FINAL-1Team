import json
import logging
import re
from typing import Any

from pydantic import ValidationError

from app.backend.schemas.chat import AgentResult
from ai.agents.supervisor_agent.supervisor_utils import _infer_task_mode

logger = logging.getLogger(__name__)
def _calendar_task_needs_recipe_result(text: str) -> bool:
    """제목이 생략된 일정 등록 task가 추천 메뉴명을 필요로 하는지 확인합니다."""
    normalized = re.sub(r"\s+", "", text or "")
    if not any(word in normalized for word in ("등록", "추가", "생성")):
        return False
    if any(word in normalized for word in ("추천메뉴", "추천레시피", "그메뉴", "그요리")):
        return True

    remainder = re.sub(r"(?:오늘|내일|모레|다음날|오전|오후)", "", normalized)
    remainder = re.sub(r"\d{1,2}(?:월|일|시|분)|\d{1,2}:\d{2}", "", remainder)
    remainder = re.sub(r"(?:캘린더|일정|등록|추가|생성|해줘|해주세요|에|으로|로)", "", remainder)
    return not remainder

def _prepare_task_plan(tasks: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """기존 task 형식을 유지하면서 실행 ID, 모드, 의존성을 보완합니다."""
    plan = []
    used_ids = set()
    for index, raw_task in enumerate(tasks or [], start=1):
        if not isinstance(raw_task, dict) or not raw_task.get("intent"):
            continue
        task_id = str(raw_task.get("id") or f"task_{index}")
        if task_id in used_ids:
            task_id = f"task_{index}"
        used_ids.add(task_id)
        intent = str(raw_task["intent"])
        plan.append({
            "id": task_id,
            "intent": intent,
            "text": str(raw_task.get("text") or ""),
            "mode": _infer_task_mode(intent, str(raw_task.get("text") or "")),
            "depends_on": [
                str(dependency)
                for dependency in raw_task.get("depends_on") or []
                if str(dependency) != task_id
            ],
        })

    task_by_intent = {task["intent"]: task for task in plan}
    if "inventory.expiring" in task_by_intent and "recipe.recommend" in task_by_intent:
        dependency_id = task_by_intent["inventory.expiring"]["id"]
        dependencies = task_by_intent["recipe.recommend"]["depends_on"]
        if dependency_id not in dependencies:
            dependencies.append(dependency_id)
    if "inventory.list" in task_by_intent and "recipe.recommend" in task_by_intent:
        dependency_id = task_by_intent["inventory.list"]["id"]
        dependencies = task_by_intent["recipe.recommend"]["depends_on"]
        if dependency_id not in dependencies:
            dependencies.append(dependency_id)
    if "recipe.recommend" in task_by_intent and "alarm.calendar" in task_by_intent:
        calendar_task = task_by_intent["alarm.calendar"]
        if _calendar_task_needs_recipe_result(calendar_task["text"]):
            dependency_id = task_by_intent["recipe.recommend"]["id"]
            if dependency_id not in calendar_task["depends_on"]:
                calendar_task["depends_on"].append(dependency_id)
    return plan


def _ready_task_batch(
    pending: list[dict[str, Any]],
    completed_ids: set[str],
    failed_ids: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """완료된 의존성을 기준으로 다음 실행 묶음과 실행 불가 작업을 반환합니다."""
    blocked = [task for task in pending if set(task["depends_on"]) & failed_ids]
    ready = [
        task
        for task in pending
        if task not in blocked and set(task["depends_on"]).issubset(completed_ids)
    ]
    return ready, blocked

_LOW_QUALITY_RESPONSE_MARKERS = (
    "실행할 도구가 연결되지 않았어요",
    "챗봇 연결 중 문제가 생겼어요",
    "요청을 처리하는 중 문제가 생겼어요",
    "음식과 관련된 대화만 지원하고 있어요",
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


def _agent_result_satisfies_task(task: dict[str, Any], agent_result: Any) -> bool:
    """Agent 결과가 요청한 작업을 정상적으로 마쳤거나 다음 입력을 요청했는지 확인합니다."""
    if _agent_result_failed(agent_result) or _agent_result_needs_retry(agent_result):
        return False
    if task.get("mode") != "read" or not isinstance(agent_result, dict):
        return True

    # 조회 작업이 확인 대기 상태로 바뀌면 잘못된 쓰기 분기로 판단합니다.
    if isinstance(agent_result.get("pending_action"), dict):
        return False
    for action in agent_result.get("actions") or []:
        message = (action.get("data") or {}).get("message") if isinstance(action, dict) else None
        if isinstance(message, str) and message.startswith("확인:"):
            return False
    return True

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
