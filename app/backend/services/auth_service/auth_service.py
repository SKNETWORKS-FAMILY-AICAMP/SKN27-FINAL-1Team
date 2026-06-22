from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from fastapi import HTTPException, status
from app.backend.db.models import User
from app.backend.core.security import create_access_token

class AuthService:
    """
    소셜 로그인 인증 및 데이터베이스 회원가입/조회를 전담하는 서비스 클래스입니다.
    """
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

        Args:
            db (Session): 데이터베이스 세션
            provider (str): 소셜 제공자 이름 (예: kakao, naver, google)
            provider_id (str): 소셜 제공자 측의 고유 식별자 ID
            email (str, optional): 소셜 계정 이메일
            nickname (str, optional): 소셜 계정 닉네임

        Returns:
            str: 클라이언트에게 전달할 JWT Access Token
        """
        try:
            # 1. 기존 가입된 사용자인지 데이터베이스에서 조회 (provider와 provider_id 기준)
            user = db.query(User).filter(
                User.provider == provider, 
                User.provider_id == provider_id
            ).first()
            
            # 1-1. provider_id로는 못 찾았으나 동일한 이메일을 가진 계정이 있는지 조회 (이메일 통합 정책)
            if not user and email:
                user = db.query(User).filter(User.email == email).first()
                if user:
                    # 기존 계정이 있다면, 방금 접속한 소셜 플랫폼 정보로 업데이트
                    user.provider = provider
                    user.provider_id = provider_id
                    if nickname:
                        user.nickname = nickname
                    db.commit()
                    db.refresh(user)

            # 2. 신규 사용자일 경우 (DB에 유저 정보가 없으면) 회원가입 처리 진행
            if not user:
                # 2-1. User 테이블에 신규 회원 레코드 추가
                user = User(
                    provider=provider,
                    provider_id=provider_id,
                    email=email,
                    nickname=nickname
                )
                db.add(user)
                # user.id 값을 임시로 얻어와서 하위 테이블 생성을 위해 DB에 flush 실행
                db.flush()
                
                # 변경사항을 최종적으로 DB에 확정(commit)
                db.commit()
                # 새롭게 생성된 DB의 최신 상태를 객체에 동기화(refresh)
                db.refresh(user)
                
            # 3. 자체 JWT Access Token 생성 (유저 ID를 subject로 담음)
            access_token = create_access_token(subject=str(user.id))
            return access_token

        except SQLAlchemyError as db_error:
            # 데이터베이스 처리 중 예외 발생 시 롤백 및 에러 반환
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"데이터베이스 처리 중 오류가 발생했습니다: {str(db_error)}"
            )

auth_service = AuthService()
