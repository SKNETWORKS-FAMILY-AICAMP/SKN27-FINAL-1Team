from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.backend.core.security import verify_access_token

# Swagger UI에서 토큰 직접 입력이 가능하도록 HTTPBearer 사용
security = HTTPBearer(auto_error=False)

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> int:
    """
    API 호출 시 HTTP Authorization 헤더에서 Bearer 토큰을 파싱하여 검증하고,
    검증 완료된 사용자의 고유 ID(int)를 반환합니다.
    """
    if not credentials:
        # 비회원 '둘러보기' 대응을 위한 예외 처리 (토큰이 없어도 0을 리턴하여 게스트 모드로 동작)
        return 0
        
    token = credentials.credentials
        
    user_id_str = verify_access_token(token)
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않거나 만료된 토큰입니다.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return int(user_id_str)

def get_current_user_optional(credentials: HTTPAuthorizationCredentials = Depends(security)) -> int:
    """
    챗봇처럼 비회원도 일부 기능을 쓸 수 있는 API에서 사용합니다.
    토큰이 없거나 만료되면 예외 대신 게스트 ID(0)를 반환합니다.
    """
    if not credentials:
        return 0

    user_id_str = verify_access_token(credentials.credentials)
    return int(user_id_str) if user_id_str else 0
def get_current_user_required(user_id: int = Depends(get_current_user)) -> int:
    """
    회원 전용 API 호출 시 토큰이 유효한지 강제로 검증하는 함수입니다.
    비로그인(Guest = 0) 상태로 접근 시 401 Unauthorized 에러를 발생시킵니다.
    """
    if user_id == 0:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="이 기능을 사용하려면 로그인이 필요합니다.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user_id
