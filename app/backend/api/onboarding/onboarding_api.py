from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.backend.db.session import get_db
from app.backend.api.deps import get_current_user_required
from app.backend.schemas.onboarding import OnboardingRequest, OnboardingResponse
from app.backend.services.onboarding_service.onboarding_service import onboarding_service

router = APIRouter(prefix="/onboarding", tags=["Onboarding (사용자 설정)"])

@router.get("", response_model=OnboardingResponse)
def get_onboarding_settings(current_user_id: int = Depends(get_current_user_required), db: Session = Depends(get_db)):
    """
    현재 로그인된 사용자의 취향 및 알레르기 온보딩 설정 정보를 조회합니다.
    """
    return onboarding_service.get_onboarding(db=db, user_id=current_user_id)

@router.post("", response_model=OnboardingResponse, status_code=status.HTTP_201_CREATED)
def save_onboarding_settings(request_data: OnboardingRequest, current_user_id: int = Depends(get_current_user_required), db: Session = Depends(get_db)):
    """
    현재 로그인된 사용자의 취향(비선호 재료), 알레르기 목록 및 알림 수신 동의 여부를 저장하거나 갱신합니다.
    """
    return onboarding_service.save_onboarding(db=db, user_id=current_user_id, data=request_data)
