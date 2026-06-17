from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime

class SocialLoginRequest(BaseModel):
    provider: str  # kakao, naver, google
    code: str      # 인가 코드 (OAuth2 Authorization Code)

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class UserResponse(BaseModel):
    id: int
    email: Optional[EmailStr] = None
    provider: str
    nickname: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
