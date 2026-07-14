from typing import TypedDict, Any, Optional

class GraphState(TypedDict):
    """LangGraph에서 노드 간에 전달되는 챗봇의 작업 상태(State)입니다."""
    
    # 입력 및 맥락 데이터
    user_id: int
    text: str                       # 사용자가 현재 입력한 메시지 원본
    history: list[Any]              # 이전 대화 내역 (SQLAlchemy Model 등)
    settings_obj: Optional[Any]     # 사용자 설정 객체
    db: Any                         # 데이터베이스 세션
    service: Any                    # ChatService 인스턴스 (기존 메서드 호출용)
    
    # 분석 및 라우팅 결과
    intent: Optional[str]           # 라우터가 판단한 의도 (예: recipe.recommend, inventory.consume 등)
    intent_payload: Optional[dict] # LLM/룰 라우팅 결과 원본 dict
    slots: Optional[dict]          # LLM이 추출한 식재료, 날짜 등 슬롯
    keyword: Optional[str]          # 추출된 핵심 키워드 (예: "감자", "양파")
    
    # 도구(Tool) 및 에이전트 통신용
    messages: list[Any]             # LangChain Messages 배열 (멀티턴 툴 호출용)
    
    # 최종 출력 데이터
    response_text: Optional[str]    # 챗봇이 사용자에게 반환할 최종 메시지 문자열
    actions: Optional[list[dict]]   # 프론트엔드 버튼/링크 액션 목록
    sources: Optional[list[dict]]   # 외부 출처 링크 목록
