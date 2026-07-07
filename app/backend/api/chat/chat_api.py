from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.backend.api.deps import get_current_user_optional
from app.backend.db.session import get_db
from app.backend.schemas.chat import ChatRequest, ChatResponse
from ai.agents.supervisor_agent.supervisor_service import supervisor_service

router = APIRouter(prefix="/chat", tags=["Chat (챗봇)"])


@router.post("", response_model=ChatResponse)
def send_chat_message(
    request_data: ChatRequest,
    current_user_id: int = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    """사용자 메시지를 의도별 서비스로 라우팅해 챗봇 응답을 반환합니다."""
    return supervisor_service.handle_message(
        db=db, 
        user_id=current_user_id, 
        message=request_data.message,
        history=request_data.history,
        user_settings=request_data.settings
    )
