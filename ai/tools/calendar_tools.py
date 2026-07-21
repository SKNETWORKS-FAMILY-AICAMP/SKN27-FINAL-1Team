from pydantic import BaseModel, Field
from langchain_core.tools import tool

class AddCalendarEventInput(BaseModel):
    title: str = Field(description="일정의 제목 (예: 김치찌개 요리하기)")
    date_str: str = Field(description="일정 날짜 (예: 내일, 2026-07-01 등)")

@tool("add_calendar_event", args_schema=AddCalendarEventInput)
def add_calendar_event_tool(title: str, date_str: str) -> str:
    """사용자가 특정 요리나 이벤트를 캘린더(일정)에 등록해달라고 요청할 때 호출합니다.
    [경고]: 일정 제목(title)과 날짜(date_str) 정보가 모두 확보되었다면, 절대로 당신이 직접 '등록했습니다'라고 대답하지 말고 반드시 이 도구(tool)를 즉시 호출하세요! 도구를 호출해야만 실제 캘린더에 저장됩니다."""
    # TODO: Google Calendar API OAuth 인증 및 이벤트 등록 로직 추가
    return f"'{title}' 일정이 {date_str}에 구글 캘린더에 임시 등록되었습니다!"

CALENDAR_TOOLS = [add_calendar_event_tool]
