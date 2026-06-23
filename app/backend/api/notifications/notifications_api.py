from datetime import datetime

from fastapi import APIRouter, Depends

from app.backend.api.deps import get_current_user_required
from app.backend.schemas.common import MessageResponse
from app.backend.schemas.notifications import DeviceTokenRequest, NotificationItem


router = APIRouter(prefix="/notifications", tags=["Notifications (알림)"])


@router.get("", response_model=list[NotificationItem])
def get_notifications(
    current_user_id: int = Depends(get_current_user_required),
):
    """
    로그인한 사용자의 알림 목록을 최근 순으로 조회합니다.
    현재는 API 계약 확인용 임시 응답을 반환합니다.
    """
    return [
        {
            "id": 1,
            "type": "EXPIRING_SOON",
            "title": "소비 임박 알림",
            "message": "냉장고의 두부가 소비기한 3일 남았습니다!",
            "is_read": False,
            "created_at": datetime.utcnow(),
        }
    ]


@router.put("/{notification_id}/read", response_model=MessageResponse)
def mark_notification_as_read(
    notification_id: int,
    current_user_id: int = Depends(get_current_user_required),
):
    """
    특정 알림을 읽음 처리합니다.
    현재는 API 계약 확인용 임시 응답을 반환합니다.
    """
    return {"message": "알림을 읽음 처리했습니다."}


@router.post("/device-token", response_model=MessageResponse)
def register_device_token(
    request_data: DeviceTokenRequest,
    current_user_id: int = Depends(get_current_user_required),
):
    """
    푸시 알림 수신용 디바이스 토큰을 등록하거나 갱신합니다.
    현재는 API 계약 확인용 임시 응답을 반환합니다.
    """
    return {"message": "디바이스 토큰이 성공적으로 등록되었습니다."}
