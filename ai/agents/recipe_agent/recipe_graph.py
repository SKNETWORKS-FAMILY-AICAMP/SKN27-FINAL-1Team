from __future__ import annotations

import json
from typing import Any

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, ToolMessage
from langchain_openai import ChatOpenAI

from app.backend.core.config import settings as app_settings

from .recipe_config import build_recipe_system_prompt
from .recipe_state import (
    RecipeAction,
    RecipeAgentReply,
    RecipeSource,
    RecipeToolContext,
    RecipeToolPayload,
)
from .recipe_tools import build_recipe_tools


def build_recipe_agent(
    context: RecipeToolContext,
    *,
    intent: str | None,
    shown_recipe_ids: set[int],
    model: Any = None,
):
    """모델, 프롬프트, Pydantic 응답, @tool을 모아서 agent로 정의한다."""
    llm = model or ChatOpenAI(
        api_key=app_settings.OPENAI_API_KEY,
        model=app_settings.OPENAI_MODEL,
        temperature=0,
    )
    return create_agent(
        model=llm,
        tools=build_recipe_tools(context),
        system_prompt=build_recipe_system_prompt(intent, shown_recipe_ids),
        response_format=RecipeAgentReply,
    )


def parse_tool_payload(message: ToolMessage) -> RecipeToolPayload | None:
    """ToolMessage의 JSON 본문을 검증된 Recipe Tool 응답으로 변환한다."""

    content = message.content
    if not isinstance(content, str):
        return None
    try:
        return RecipeToolPayload.model_validate_json(content)
    except (ValueError, TypeError):
        return None


def deduplicate_models_by_content(models: list[Any]) -> list[Any]:
    """Pydantic 모델의 직렬화 결과를 기준으로 중복을 제거한다."""

    seen: set[str] = set()
    result: list[Any] = []
    for model in models:
        key = json.dumps(model.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
        if key not in seen:
            seen.add(key)
            result.append(model)
    return result


def parse_recipe_agent_result(result: dict[str, Any]) -> RecipeAgentReply:
    """AgentState 결과를 검증하고 tool의 UI 메타데이터를 보존한다."""
    structured = result.get("structured_response")
    if structured is not None:
        reply = RecipeAgentReply.model_validate(structured)
    else:
        reply = None
        for message in reversed(result.get("messages") or []):
            if isinstance(message, AIMessage) and isinstance(message.content, str) and message.content.strip():
                try:
                    reply = RecipeAgentReply.model_validate_json(message.content)
                except (ValueError, TypeError):
                    reply = RecipeAgentReply(message=message.content.strip())
                break

    payloads = [
        payload
        for message in result.get("messages") or []
        if isinstance(message, ToolMessage)
        if (payload := parse_tool_payload(message)) is not None
    ]
    if reply is None:
        if not payloads:
            return RecipeAgentReply(message="요청을 처리하지 못했어요.")
        last_payload = payloads[-1]
        reply = RecipeAgentReply(message=last_payload.message)

    # 마지막으로 성공한 Tool을 최종 결과의 근거로 사용한다. 실행 도중 발생한
    # 이전 Tool의 액션이나 출처가 최종 응답에 섞이지 않도록 정책별로 선택한다.
    successful_payloads = [payload for payload in payloads if payload.status == "success"]
    selected_payload = successful_payloads[-1] if successful_payloads else None

    actions: list[RecipeAction] = []
    sources: list[RecipeSource] = []
    if selected_payload is not None:
        if selected_payload.metadata_policy in {"actions", "both"}:
            actions = deduplicate_models_by_content(selected_payload.actions)
        if selected_payload.metadata_policy in {"sources", "both"}:
            sources = deduplicate_models_by_content(selected_payload.sources)

    return reply.model_copy(
        update={
            "actions": actions,
            "sources": sources,
        }
    )

