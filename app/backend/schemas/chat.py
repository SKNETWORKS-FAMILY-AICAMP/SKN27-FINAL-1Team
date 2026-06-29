from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """챗봇 메시지 요청 스키마입니다."""

    message: str = Field(..., min_length=1, description="사용자 메시지")


class ChatAction(BaseModel):
    """챗봇 응답에서 사용자가 바로 누를 수 있는 액션입니다."""

    label: str = Field(..., description="버튼에 표시할 문구")
    url: str = Field(..., description="이동할 프론트엔드 경로")
    data: dict[str, Any] = Field(default_factory=dict, description="추가 응답 데이터")


class ChatResponse(BaseModel):
    """챗봇 메시지 응답 스키마입니다."""

    intent: str = Field(..., description="분류된 사용자 의도")
    reply: str = Field(..., description="챗봇 응답 메시지")
    actions: list[ChatAction] = Field(default_factory=list, description="응답 액션 목록")