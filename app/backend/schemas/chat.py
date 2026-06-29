from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """챗봇 메시지 요청 스키마입니다."""

    message: str = Field(..., min_length=1, description="사용자 메시지")


class ChatResponse(BaseModel):
    """챗봇 메시지 응답 스키마입니다."""

    intent: str = Field(..., description="분류된 사용자 의도")
    reply: str = Field(..., description="챗봇 응답 메시지")
