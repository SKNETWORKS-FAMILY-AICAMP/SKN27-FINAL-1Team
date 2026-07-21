from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.backend.api.deps import get_current_user_required
from app.backend.core.config import settings
from app.backend.db.models import User
from app.backend.db.session import get_db
from app.backend.mcp.auth import BobbeoriTokenVerifier
from app.backend.schemas.auth import (
    McpIdentityLinkRequest,
    McpIdentityLinkResponse,
    SocialLoginRequest,
    TokenResponse,
    UserResponse,
)
from app.backend.services.auth_service.auth_service import auth_service
from app.backend.services.auth_service.external_identity_service import (
    ExternalIdentityConflictError,
    link_external_identity,
)
from app.backend.services.auth_service.oauth import oauth_client


router = APIRouter(prefix="/auth", tags=["Auth (실제 인증)"])
mcp_token_verifier = BobbeoriTokenVerifier(settings)


@router.post("/social-login", response_model=TokenResponse)
async def social_login(login_data: SocialLoginRequest, db: Session = Depends(get_db)):
    """Exchange a social authorization code for a Bobbeori access token."""
    provider = login_data.provider.lower()
    try:
        if provider == "kakao":
            user_info = await oauth_client.get_kakao_user(login_data.code)
        elif provider == "naver":
            user_info = await oauth_client.get_naver_user(login_data.code, login_data.state)
        elif provider == "google":
            user_info = await oauth_client.get_google_user(login_data.code, login_data.redirect_uri)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="지원하지 않는 소셜 로그인 제공자입니다. (kakao, naver, google 중 하나 선택)",
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"소셜 인증 서버 통신 중 오류가 발생했습니다: {exc}",
        ) from exc

    access_token = auth_service.authenticate_social_user(
        db=db,
        provider=provider,
        provider_id=user_info["provider_id"],
        email=user_info.get("email"),
        nickname=user_info.get("nickname"),
    )
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=UserResponse)
def get_me(current_user_id: int = Depends(get_current_user_required), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == current_user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="사용자를 찾을 수 없습니다.")
    return user


@router.post("/mcp/link", response_model=McpIdentityLinkResponse)
async def link_mcp_account(
    request_data: McpIdentityLinkRequest,
    current_user_id: int = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """Link the signed-in Bobbeori user to a verified production OAuth subject."""
    if settings.MCP_DEV_TOKEN_AUTH:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MCP account linking is production-only.")

    access_token = await mcp_token_verifier.verify_token(request_data.oauth_access_token.get_secret_value())
    claims = access_token.claims if access_token else None
    issuer = str((claims or {}).get("iss") or "")
    if access_token is None or access_token.subject is None or not issuer:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid OAuth access token.")

    try:
        identity = link_external_identity(
            db,
            user_id=current_user_id,
            issuer=issuer,
            subject=str(access_token.subject),
        )
    except ExternalIdentityConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return {"linked": True, "issuer": identity.issuer}


@router.post("/dev-login", response_model=TokenResponse)
def dev_cheat_login(db: Session = Depends(get_db)):
    if not settings.DEV_MODE:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")

    access_token = auth_service.authenticate_social_user(
        db=db,
        provider="kakao",
        provider_id="dev_cheat_id_9999",
        email="dev@bobbeori.com",
        nickname="개발자용치트유저",
    )
    return {"access_token": access_token, "token_type": "bearer"}
