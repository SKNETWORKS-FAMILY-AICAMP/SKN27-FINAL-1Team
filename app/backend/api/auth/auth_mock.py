from fastapi import APIRouter, Depends, HTTPException, status
from app.backend.schemas.auth import SocialLoginRequest, TokenResponse, UserResponse
from app.backend.core.security import create_access_token
from app.backend.api.deps import get_current_user_required
from datetime import datetime

router = APIRouter(prefix="/auth", tags=["Mock Auth (인증)"])

# 가상 유저 데이터베이스 (테스트용)
MOCK_USERS = {
    1: {"id": 1, "email": "user1@kakao.com", "provider": "kakao", "nickname": "맛있는대파", "created_at": datetime.now()},
    2: {"id": 2, "email": "user2@naver.com", "provider": "naver", "nickname": "신선한우유", "created_at": datetime.now()},
    3: {"id": 3, "email": "user3@google.com", "provider": "google", "nickname": "바삭한토마토", "created_at": datetime.now()}
}

@router.post("/login", response_model=TokenResponse)
def mock_social_login(login_data: SocialLoginRequest):
    """
    [Mock] 소셜 로그인 API.
    실제 OAuth2 인증 서버 통신 없이, 특정 provider로 로그인 시 더미 토큰을 즉시 반환합니다.
    - provider: kakao, naver, google 중 하나
    - code: 아무 문자열이나 가능 (예: "mock_code_123")
    """
    if login_data.provider not in ["kakao", "naver", "google"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="지원하지 않는 소셜 로그인 제공자입니다. (kakao, naver, google 중 하나 선택)"
        )
    
    # 임의로 user_id 1번(kakao), 2번(naver), 3번(google)으로 바인딩하여 토큰 생성
    user_id_map = {"kakao": 1, "naver": 2, "google": 3}
    user_id = user_id_map[login_data.provider]
    
    # 우리 서버만의 자체 JWT Access Token 발행
    access_token = create_access_token(subject=str(user_id))
    
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me", response_model=UserResponse)
def mock_get_me(current_user_id: int = Depends(get_current_user_required)):
    """
    [Mock] 로그인 사용자 프로필 정보 조회 API.
    발행한 Bearer 토큰을 Authorization 헤더에 넣어 요청하면 가상 유저 프로필 정보를 반환합니다.
    """
    user = MOCK_USERS.get(current_user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="사용자를 찾을 수 없습니다."
        )
    return user
