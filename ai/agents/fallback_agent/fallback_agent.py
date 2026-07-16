from __future__ import annotations

from typing import Any

from app.backend.core.config import settings

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


_FOOD_FALLBACK_SYSTEM_PROMPT = """
당신은 밥벌이 서비스의 일반 요리 지식 보조 Agent입니다.
요리, 식재료, 계량 환산, 재료 대체, 조리 팁에 관한 질문만 답하세요.
냉장고 보유 재료, 장보기 목록, 일정처럼 사용자의 실제 데이터는 추측하지 마세요.
재료 추가·소비·삭제와 같은 데이터 변경을 실행했다고 말하지 마세요.
음식과 관계없는 질문에는 '음식과 관련된 질문만 도와드릴 수 있어요.'라고만 답하세요.
근거가 불확실한 수치는 단정하지 말고 일반적인 기준임을 밝혀주세요.
답변은 한국어 존댓말로 간결하게 작성하세요.
""".strip()


def _history_messages(history: list[Any] | None) -> list[dict[str, str]]:
    """최근 대화에서 fallback 답변에 필요한 일반 텍스트 문맥만 추출합니다."""
    messages = []
    for item in (history or [])[-4:]:
        role = item.get("role") if isinstance(item, dict) else getattr(item, "role", "")
        text = item.get("text") if isinstance(item, dict) else getattr(item, "text", "")
        if role in {"user", "bot"} and text:
            messages.append({"role": "assistant" if role == "bot" else "user", "content": text})
    return messages


def run_food_fallback(text: str, history: list[Any] | None = None) -> dict[str, Any]:
    """기존 Agent가 담당하지 않는 일반 요리 질문에 제한된 LLM 답변을 생성합니다."""
    if OpenAI is None or not settings.OPENAI_API_KEY:
        return {"response_text": "일반 요리 답변 기능을 현재 사용할 수 없어요. 잠시 후 다시 시도해주세요."}

    messages = [{"role": "system", "content": _FOOD_FALLBACK_SYSTEM_PROMPT}]
    messages.extend(_history_messages(history))
    messages.append({"role": "user", "content": text})
    try:
        response = OpenAI(api_key=settings.OPENAI_API_KEY).chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=messages,
            temperature=0.2,
        )
        reply = (response.choices[0].message.content or "").strip()
        return {"response_text": reply or "답변을 만들지 못했어요. 질문을 조금 더 구체적으로 알려주세요."}
    except Exception:
        return {"response_text": "일반 요리 답변을 만드는 중 문제가 생겼어요. 잠시 후 다시 시도해주세요."}