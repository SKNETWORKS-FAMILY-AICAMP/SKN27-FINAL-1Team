import json
import logging
import os
from typing import Any

from sqlalchemy.orm import Session

from app.backend.core.config import settings as app_settings
from ai.agents.guide_agent import answer_guide_query

logger = logging.getLogger(__name__)


try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

try:
    from langfuse import get_client as get_langfuse_client, propagate_attributes
    from langfuse.langchain import CallbackHandler as LangfuseCallbackHandler
except ImportError:
    get_langfuse_client = None
    propagate_attributes = None
    LangfuseCallbackHandler = None

from ai.agents.supervisor_agent.supervisor_utils import (
    _LLM_ROUTE_CONFIDENCE,
    _LLM_ROUTE_INTENTS,
    _LLM_ROUTE_SYSTEM_PROMPT,
    _auth_status_response,
    _build_chat_state,
    _build_llm_route_history,
    _chat_error_response,
    _chat_response_from_state,
    _guide_result_to_state,
    _is_login_status_question,
    _is_llm_route_payload_valid,
    _parse_llm_route_payload,
    _route_payload,
)


class ChatService:
    """사용자 자연어 메시지를 intent로 분류하고 기존 서비스를 호출합니다."""

    def handle_message(
        self,
        db: Session,
        user_id: int,
        message: str,
        history: list[Any] | None = None,
        user_settings: Any = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """LangGraph를 활용하여 메시지를 처리하고 챗봇 응답 딕셔너리를 반환합니다."""
        text = message.strip()
        if _is_login_status_question(text):
            return _auth_status_response(user_id)

        from ai.agents.supervisor_agent.supervisor_agent import supervisor_agent

        initial_state = _build_chat_state(
            db=db,
            user_id=user_id,
            text=text,
            history=history,
            user_settings=user_settings,
            service=self,
        )

        invoke_config = {
            "run_name": "supervisor-chat",
            "metadata": {
                "chat_session_id": session_id or "",
                "history_count": len(history or []),
                "has_pending_action": any(
                    bool(item.get("pending_action"))
                    for item in _build_llm_route_history(history)
                    if item.get("role") == "bot"
                ),
            },
        }

        try:
            if (
                get_langfuse_client
                and propagate_attributes
                and LangfuseCallbackHandler
                and os.getenv("LANGFUSE_PUBLIC_KEY")
                and os.getenv("LANGFUSE_SECRET_KEY")
            ):
                invoke_config["callbacks"] = [LangfuseCallbackHandler()]
                with propagate_attributes(
                    trace_name="bobbeori-supervisor-chat",
                    user_id=str(user_id or "guest"),
                    session_id=session_id or str(user_id or "guest"),
                    tags=["supervisor", "chatbot", "langgraph"],
                    metadata=invoke_config["metadata"],
                ):
                    langfuse_client = get_langfuse_client()
                    with langfuse_client.start_as_current_observation(
                        name="supervisor-request",
                        as_type="agent",
                        input={"text": text, "history_count": len(history or [])},
                    ) as observation:
                        try:
                            final_state = supervisor_agent.invoke(initial_state, config=invoke_config)
                            route_payload = final_state.get("intent_payload") or {}
                            route_slots = final_state.get("slots") or {}
                            try:
                                observation.update(
                                    output={"intent": final_state.get("intent", "general")},
                                    metadata={
                                        "status": "success",
                                        "route_confidence": route_payload.get("confidence"),
                                        "task_count": len(final_state.get("tasks") or []),
                                        "action_count": len(final_state.get("actions") or []),
                                        "source_count": len(final_state.get("sources") or []),
                                        "completed_intents": route_slots.get("completed_intents", []),
                                        "failed_intents": route_slots.get("failed_intents", []),
                                    },
                                )
                                langfuse_client.score_current_trace(
                                    name="supervisor_success",
                                    value=1,
                                    data_type="BOOLEAN",
                                )
                            except Exception as trace_exc:
                                print(f"[ChatService] Langfuse result recording failed: {trace_exc}")
                        except Exception as exc:
                            try:
                                observation.update(
                                    level="ERROR",
                                    status_message=f"{type(exc).__name__}: {exc}",
                                    metadata={"status": "error"},
                                )
                                langfuse_client.score_current_trace(
                                    name="supervisor_success",
                                    value=0,
                                    data_type="BOOLEAN",
                                )
                            except Exception as trace_exc:
                                print(f"[ChatService] Langfuse error recording failed: {trace_exc}")
                            raise
            else:
                final_state = supervisor_agent.invoke(initial_state, config=invoke_config)
            response = _chat_response_from_state(final_state)
        except Exception as exc:
            print(f"[ChatService] graph failed: {type(exc).__name__}: {exc}")
            response = _chat_error_response()

        reply = response["reply"]
        if user_settings and getattr(user_settings, "shortAnswer", False) and len(reply) > 50:
            if OpenAI is not None and app_settings.OPENAI_API_KEY:
                client_ai = OpenAI(api_key=app_settings.OPENAI_API_KEY)
                try:
                    result = client_ai.chat.completions.create(
                        model=app_settings.OPENAI_MODEL,
                        messages=[
                            {
                                "role": "system",
                                "content": "다음 챗봇 응답을 핵심만 남겨서 1~2문장의 아주 짧은 대화체로 요약해. 존댓말을 사용해.",
                            },
                            {"role": "user", "content": reply},
                        ],
                        temperature=0.3,
                    )
                    response["reply"] = result.choices[0].message.content.strip()
                except Exception:
                    pass

        return response

    def _route_intent_payload_with_llm(self, text: str, history: list[Any] | None = None) -> dict[str, Any]:
        """읽기 요청을 LLM으로 분류해 검증된 JSON dict로 반환합니다."""
        if not app_settings.OPENAI_API_KEY or OpenAI is None:
            return _route_payload("general", confidence=0.0)

        try:
            from langchain_openai import ChatOpenAI
            from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

            # JSON 모드를 사용해 자유 형식 응답이 라우터로 유입되지 않게 합니다.
            llm = ChatOpenAI(
                model=app_settings.OPENAI_MODEL,
                api_key=app_settings.OPENAI_API_KEY,
                temperature=0.0,
            ).bind(response_format={"type": "json_object"})

            messages = [SystemMessage(content=_LLM_ROUTE_SYSTEM_PROMPT)]

            for message in _build_llm_route_history(history):
                if message["role"] == "user":
                    messages.append(HumanMessage(content=message["text"]))
                elif message["role"] == "bot":
                    # 직전 라우팅 결과를 JSON 문맥으로 전달해 생략된 후속 질문을 보완합니다.
                    route_context = {
                        key: message.get(key)
                        for key in ("intent", "slots", "pending_action")
                        if message.get(key)
                    }
                    message_text = message["text"]
                    if route_context:
                        message_text += f"\n[route_context: {json.dumps(route_context, ensure_ascii=False)}]"
                    messages.append(AIMessage(content=message_text))

            messages.append(HumanMessage(content=text))

            response = llm.invoke(messages)
            payload = _parse_llm_route_payload(response.content, fallback_text=text)
            if not _is_llm_route_payload_valid(payload, text):
                return _route_payload("general", confidence=0.0)

            intent = payload.get("intent", "")
            if intent == "multi_agent":
                if payload.get("confidence", 0) >= _LLM_ROUTE_CONFIDENCE and len(payload.get("tasks") or []) >= 2:
                    return payload
                return _route_payload("general", confidence=0.0)
            if intent in _LLM_ROUTE_INTENTS and payload.get("confidence", 0) >= _LLM_ROUTE_CONFIDENCE:
                return payload
            return _route_payload("general", confidence=payload.get("confidence", 0), slots=payload.get("slots", {}))
        except Exception:
            logger.exception("LLM intent 분류에 실패했습니다.")
            return _route_payload("general", confidence=0.0)


    def _reply_guide(self, text: str) -> dict[str, Any]:
        """Guide Agent 공통 응답을 Supervisor GraphState 형식으로 변환합니다."""
        agent_result = answer_guide_query(text)
        return _guide_result_to_state(agent_result)


supervisor_service = ChatService()
