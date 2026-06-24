from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.backend.schemas.auth import SocialLoginRequest, TokenResponse, UserResponse
from app.backend.db.session import get_db
from app.backend.services.auth_service.oauth import oauth_client
from app.backend.services.auth_service.auth_service import auth_service
from app.backend.api.deps import get_current_user_required
from app.backend.db.models import User

router = APIRouter(prefix="/auth", tags=["Auth (실제 인증)"])

@router.post("/social-login", response_model=TokenResponse)
async def social_login(login_data: SocialLoginRequest, db: Session = Depends(get_db)):
    """
    실제 소셜 로그인 연동 API.
    프론트엔드로부터 수신한 인가 코드로 카카오/네이버/구글 OAuth2 서버와 비동기 통신을 수행한 뒤,
    사용자 가입/로그인 및 JWT 발급을 처리합니다.
    """
    provider = login_data.provider.lower()
    code = login_data.code
    oauth_state = login_data.state

    # 소셜 제공자 확인 및 사용자 프로필 가져오기
    try:
        if provider == "kakao":
            user_info = await oauth_client.get_kakao_user(code)
        elif provider == "naver":
            user_info = await oauth_client.get_naver_user(code, oauth_state)
        elif provider == "google":
            user_info = await oauth_client.get_google_user(code, login_data.redirect_uri)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="지원하지 않는 소셜 로그인 제공자입니다. (kakao, naver, google 중 하나 선택)"
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"소셜 인증 서버 통신 중 오류가 발생했습니다: {str(e)}"
        )

    # 데이터베이스 대조 및 가입/로그인 처리 후 JWT 발급
    access_token = auth_service.authenticate_social_user(
        db=db,
        provider=provider,
        provider_id=user_info["provider_id"],
        email=user_info.get("email"),
        nickname=user_info.get("nickname")
    )

    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me", response_model=UserResponse)
def get_me(current_user_id: int = Depends(get_current_user_required), db: Session = Depends(get_db)):
    """
    실제 로그인된 사용자 본인의 프로필 정보를 데이터베이스에서 조회하여 반환합니다.
    """
    user = db.query(User).filter(User.id == current_user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="사용자를 찾을 수 없습니다."
        )
    return user

@router.post("/dev-login", response_model=TokenResponse)
def dev_cheat_login(db: Session = Depends(get_db)):
    """
    [개발자 전용 치트키 API]
    서버를 껐다 켜거나 DB가 날아갔을 때, 매번 카카오 로그인을 하기 번거로우므로 만든 치트키입니다.
    이 API를 호출하면 가짜 유저(개발자)를 무조건 DB에 생성하거나 불러와서 즉시 사용할 수 있는 진짜 Access Token을 발급해 줍니다.
    """
    # 1. 개발자용 가짜 카카오 유저 정보를 강제로 세팅
    access_token = auth_service.authenticate_social_user(
        db=db,
        provider="kakao",
        provider_id="dev_cheat_id_9999",
        email="dev@bobbeori.com",
        nickname="개발자용치트유저"
    )
    return {"access_token": access_token, "token_type": "bearer"}
