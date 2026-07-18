from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ChatMessage(BaseModel):
    """이전 대화의 화면 문구와 분류된 의도를 함께 보관합니다."""

    role: str
    text: str
    intent: str | None = None
    slots: dict[str, Any] = Field(default_factory=dict, description="이전 응답에서 추출한 문맥 슬롯")
    pending_action: dict[str, Any] | None = Field(default=None, description="이전 응답의 실행 대기 작업")

class ChatSettings(BaseModel):
    shortAnswer: bool = True
    fridgeFirst: bool = True
    expiringFirst: bool = True
    excludeDislikes: bool = True

class ChatRequest(BaseModel):
    """챗봇 메시지 요청 스키마입니다."""

    message: str = Field(..., min_length=1, description="사용자 메시지")
    session_id: str | None = Field(default=None, max_length=100, description="Langfuse 대화 추적 세션 ID")
    context_token: str | None = Field(default=None, description="서버가 서명한 직전 대화 문맥")
    history: list[ChatMessage] = Field(default_factory=list, description="이전 대화 내역")
    settings: ChatSettings = Field(default_factory=ChatSettings, description="사용자 설정 값")


class ChatAction(BaseModel):
    """챗봇 응답에서 사용자가 바로 누를 수 있는 액션입니다."""

    label: str = Field(..., description="버튼에 표시할 문구")
    url: str = Field("", description="이동할 프론트엔드 경로")
    data: dict[str, Any] = Field(default_factory=dict, description="추가 응답 데이터")


class ChatSource(BaseModel):
    """웹 검색 fallback 응답에 표시할 출처입니다."""

    title: str = Field(..., description="출처 제목")
    url: str = Field(..., description="출처 URL")


class ChatResponse(BaseModel):
    """챗봇 메시지 응답 스키마입니다."""

    intent: str = Field(..., description="분류된 사용자 의도")
    reply: str = Field(..., description="챗봇 응답 메시지")
    actions: list[ChatAction] = Field(default_factory=list, description="응답 액션 목록")
    sources: list[ChatSource] = Field(default_factory=list, description="응답 출처 목록")
    slots: dict[str, Any] = Field(default_factory=dict, description="다음 대화에 전달할 문맥 슬롯")
    pending_action: dict[str, Any] | None = Field(default=None, description="사용자 확인을 기다리는 작업")
    context_token: str | None = Field(default=None, description="다음 요청에 전달할 서명된 대화 문맥")


class AgentResult(BaseModel):
    """서로 다른 에이전트 응답을 Supervisor에서 검증할 공통 스키마입니다."""

    model_config = ConfigDict(extra="allow")

    ok: bool | None = None
    status: str | None = None
    response_text: str | None = None
    message: str | None = None
    actions: list[dict[str, Any]] | None = None
    sources: list[dict[str, Any]] | None = None
    slots: dict[str, Any] = Field(default_factory=dict)
    pending_action: dict[str, Any] | None = None
    ui: dict[str, Any] = Field(default_factory=dict)
    action: str | None = None
    error: Any = None
