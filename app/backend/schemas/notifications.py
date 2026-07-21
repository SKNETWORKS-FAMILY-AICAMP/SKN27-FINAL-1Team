from datetime import datetime
from pydantic import BaseModel, Field
from typing import List


class DeviceTokenRequest(BaseModel):
    device_token: str = Field(..., description="FCM 등 푸시 알림용 디바이스 토큰")


class NotificationItem(BaseModel):
    id: int = Field(..., description="알림 ID")
    type: str = Field(..., description="알림 유형")
    title: str = Field(..., description="알림 제목")
    message: str = Field(..., description="알림 내용")
    is_read: bool = Field(default=False, description="읽음 여부")
    created_at: datetime = Field(..., description="알림 생성 시각")


class NotificationListResponse(BaseModel):
    notifications: List[NotificationItem] = Field(default_factory=list, description="알림 목록")
