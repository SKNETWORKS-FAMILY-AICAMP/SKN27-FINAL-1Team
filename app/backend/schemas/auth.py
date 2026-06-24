from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime

class SocialLoginRequest(BaseModel):
    provider: str  # kakao, naver, google
    code: str      # 인가 코드 (OAuth2 Authorization Code)
    state: Optional[str] = None  # OAuth 요청 위조 방지를 위한 state 값

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class UserResponse(BaseModel):
    id: int
    email: Optional[EmailStr] = None
    provider: str
    nickname: Optional[str] = None
    created_at: datetime
    is_onboarded: bool = False

    class Config:
        from_attributes = True
