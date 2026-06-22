from pydantic import BaseModel, Field


class MessageResponse(BaseModel):
    message: str = Field(..., description="처리 결과 메시지")
