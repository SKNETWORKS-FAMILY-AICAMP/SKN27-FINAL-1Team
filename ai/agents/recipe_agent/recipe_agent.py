from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from .recipe_graph import build_recipe_agent, parse_recipe_agent_result
from .recipe_state import RecipeAgentReply, RecipeToolContext
from .recipe_utils import LOGIN_REQUIRED_REPLY, _requires_login, extract_shown_recipe_ids

__all__ = ["run_recipe_agent", "to_supervisor_state"]


def _history_messages(history: list[Any]) -> list[BaseMessage]:
    messages: list[BaseMessage] = []
    for item in history[-10:]:
        if isinstance(item, BaseMessage):
            messages.append(item)
            continue
        role = item.get("role", "") if isinstance(item, dict) else getattr(item, "role", "")
        text = item.get("text", "") if isinstance(item, dict) else getattr(item, "text", "")
        if not isinstance(text, str) or not text.strip():
            continue
        if role in {"user", "human"}:
            messages.append(HumanMessage(content=text))
        elif role in {"bot", "assistant", "ai"}:
            messages.append(AIMessage(content=text))
    return messages


def to_supervisor_state(reply: RecipeAgentReply) -> dict[str, Any]:
    result: dict[str, Any] = {
        "response_text": reply.message,
        "actions": [action.model_dump() for action in reply.actions],
        "sources": [source.model_dump() for source in reply.sources],
    }
    shown_recipe_ids = [
        int(action.data["recipe_id"])
        for action in reply.actions
        if action.data.get("recipe_id") is not None
    ]
    if shown_recipe_ids:
        result["slots"] = {"shown_recipe_ids": shown_recipe_ids}
    return result


def run_recipe_agent(
    text: str,
    *,
    db: Any,
    user_id: int | None = None,
    history: list | None = None,
    settings_obj: Any = None,
    intent: str | None = None,
) -> dict:
    """Supervisor 계약을 LangChain recipe agent 호출로 연결한다."""
    history = history or []
    route_intent = intent or "recipe"
    if not user_id and _requires_login(route_intent, text):
        return to_supervisor_state(RecipeAgentReply(message=LOGIN_REQUIRED_REPLY))

    context = RecipeToolContext(
        db=db,
        user_id=user_id,
        history=history,
        settings_obj=settings_obj,
    )
    agent = build_recipe_agent(
        context,
        intent=route_intent,
        shown_recipe_ids=extract_shown_recipe_ids(history),
    )
    messages = [*_history_messages(history), HumanMessage(content=text)]
    state = agent.invoke(
        {"messages": messages, "intent": route_intent},
        config={"recursion_limit": 8},
    )
    return to_supervisor_state(parse_recipe_agent_result(state))
