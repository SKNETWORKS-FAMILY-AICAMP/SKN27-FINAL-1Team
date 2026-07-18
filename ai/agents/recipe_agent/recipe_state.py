from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from langchain.agents import AgentState
from pydantic import BaseModel, Field


class SearchRecipesInput(BaseModel):
    keyword: str = Field(description="찾을 요리명 또는 레시피 키워드")


class RecommendByIngredientInput(BaseModel):
    ingredient: str = Field(description="추천의 기준이 되는 주재료 한 가지")


class SearchExternalInput(BaseModel):
    keyword: str = Field(description="웹에서 찾을 요리 또는 재료 키워드")
    query_text: str = Field(description="조리 시간, 온도 등 사용자의 원문 질문")


class SuggestPairingInput(BaseModel):
    text: str = Field(description="함께 먹을 음식이나 곁들임을 묻는 사용자 원문")


class RecipeAction(BaseModel):
    label: str
    url: str
    data: dict[str, Any] = Field(default_factory=dict)


class RecipeSource(BaseModel):
    title: str
    url: str


class RecipeAgentReply(BaseModel):
    """모델이 슈퍼바이저에 반환할 최종 응답."""

    message: str = Field(description="사용자에게 보여줄 한국어 답변")
    actions: list[RecipeAction] = Field(
        default_factory=list,
        description="도구 결과에 포함된 이동 버튼. 임의로 만들지 않는다.",
    )
    sources: list[RecipeSource] = Field(
        default_factory=list,
        description="외부 검색 도구가 제공한 출처. 임의로 만들지 않는다.",
    )


class RecipeToolPayload(BaseModel):
    """ToolMessage로 모델과 결과 파서가 함께 읽는 공통 도구 결과."""

    tool: str
    status: Literal["success", "empty", "error"]
    message: str
    actions: list[RecipeAction] = Field(default_factory=list)
    sources: list[RecipeSource] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)


class RecipeAgentState(AgentState):
    """LangChain agent loop에서 사용하는 메시지 기반 상태."""

    intent: str


@dataclass
class RecipeToolContext:
    """LLM에 노출하지 않고 recipe tool에만 주입하는 실행 의존성."""

    db: Any
    user_id: int | None = None
    history: list[Any] = field(default_factory=list)
    settings_obj: Any = None

