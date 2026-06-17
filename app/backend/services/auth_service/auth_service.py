from sqlalchemy.orm import Session
from app.backend.db.models import User, Fridge, UserOnboarding
from app.backend.core.security import create_access_token

class AuthService:
    def authenticate_social_user(
        self, 
        db: Session, 
        provider: str, 
        provider_id: str, 
        email: str = None, 
        nickname: str = None
    ) -> str:
        """
        소셜 프로필 정보를 받아 DB 조회를 거쳐 회원가입 또는 로그인을 처리하고,
        자체 서비스 권한 인증을 위한 JWT Access Token을 발급합니다.
        """
        # 기존 가입된 사용자인지 조회
        user = db.query(User).filter(
            User.provider == provider, 
            User.provider_id == provider_id
        ).first()
        
        # 신규 사용자일 경우 가입 처리
        if not user:
            user = User(
                provider=provider,
                provider_id=provider_id,
                email=email,
                nickname=nickname
            )
            db.add(user)
            # user.id 값을 임시로 얻어와서 하위 테이블 생성을 위해 flush 실행
            db.flush()
            
            # 알림 및 선호도 온보딩 기본 레코드 생성
            onboarding = UserOnboarding(
                user_id=user.id,
                is_alert_allowed=True
            )
            db.add(onboarding)
            
            # 사용자가 즉시 식재료를 등록할 수 있게 기본 냉장고 생성
            fridge = Fridge(
                user_id=user.id,
                name="나의 냉장고"
            )
            db.add(fridge)
            
            db.commit()
            db.refresh(user)
            
        # 자체 JWT Access Token 생성 및 반환
        access_token = create_access_token(subject=str(user.id))
        return access_token

auth_service = AuthService()
