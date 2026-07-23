from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, SecretStr


class SocialLoginRequest(BaseModel):
    provider: str
    code: str
    state: Optional[str] = None
    redirect_uri: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    is_new_user: bool = False


class McpIdentityLinkRequest(BaseModel):
    oauth_access_token: SecretStr


class McpIdentityLinkResponse(BaseModel):
    linked: bool
    issuer: str


class UserResponse(BaseModel):
    id: int
    email: Optional[EmailStr] = None
    provider: str
    nickname: Optional[str] = None
    created_at: datetime
    is_onboarded: bool = False

    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    nickname: Optional[str] = None
