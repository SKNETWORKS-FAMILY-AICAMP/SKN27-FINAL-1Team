from pydantic import BaseModel, Field
from langchain_core.tools import tool

class AddCalendarEventInput(BaseModel):
    title: str = Field(description="일정의 제목 (예: 김치찌개 요리하기)")
    date_str: str = Field(description="일정 날짜 (예: 내일, 2026-07-01 등)")

@tool("add_calendar_event", args_schema=AddCalendarEventInput)
def add_calendar_event_tool(title: str, date_str: str) -> str:
    """사용자가 특정 요리나 이벤트를 캘린더(일정)에 등록해달라고 요청할 때 호출합니다."""
    # TODO: Google Calendar API OAuth 인증 및 이벤트 등록 로직 추가
    return f"'{title}' 일정이 {date_str}에 구글 캘린더에 임시 등록되었습니다!"

CALENDAR_TOOLS = [add_calendar_event_tool]
