import httpx
from fastapi import HTTPException, status
from app.backend.core.config import settings

class OAuthClient:
    """
    각 소셜 플랫폼(카카오, 네이버, 구글)의 OAuth2.0 서버와 비동기로 통신하여
    Access Token을 발급받고, 유저 정보를 추출하는 통신 전담 클래스입니다.
    """
    async def get_kakao_user(self, code: str) -> dict:
        """
        카카오 인가 코드를 이용하여 액세스 토큰을 발급받고,
        해당 토큰으로 사용자 정보를 가져와 정제된 딕셔너리로 반환합니다.
        """
        try:
            # 10초의 타임아웃을 설정하여 무한 대기 방지
            async with httpx.AsyncClient(timeout=10.0) as client:
                # 1. 액세스 토큰 요청 (카카오 API)
                token_res = await client.post(
                    "https://kauth.kakao.com/oauth/token",
                    data={
                        "grant_type": "authorization_code",
                        "client_id": settings.KAKAO_CLIENT_ID,
                        "client_secret": settings.KAKAO_CLIENT_SECRET,
                        "redirect_uri": settings.KAKAO_REDIRECT_URI,
                        "code": code,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                )
                token_res.raise_for_status()
                access_token = token_res.json().get("access_token")

                # 2. 발급받은 토큰으로 사용자 정보 요청
                user_res = await client.get(
                    "https://kapi.kakao.com/v2/user/me",
                    headers={"Authorization": f"Bearer {access_token}"}
                )
                user_res.raise_for_status()
                user_data = user_res.json()
                
                # 3. 카카오 고유 ID 및 프로필 추출하여 반환
                return {
                    "provider_id": str(user_data.get("id")),
                    "email": user_data.get("kakao_account", {}).get("email"),
                    "nickname": user_data.get("properties", {}).get("nickname"),
                }
        except httpx.HTTPError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"카카오 인증 서버와 통신 중 오류가 발생했습니다: {str(e)}"
            )

    async def get_naver_user(self, code: str) -> dict:
        """
        네이버 인가 코드를 이용하여 액세스 토큰을 발급받고,
        해당 토큰으로 사용자 정보를 가져와 정제된 딕셔너리로 반환합니다.
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # 1. 액세스 토큰 요청 (네이버 API - 네이버는 쿼리 파라미터로 전송해야 안전함)
                token_res = await client.post(
                    "https://nid.naver.com/oauth2.0/token",
                    data={
                        "grant_type": "authorization_code",
                        "client_id": settings.NAVER_CLIENT_ID,
                        "client_secret": settings.NAVER_CLIENT_SECRET,
                        "redirect_uri": settings.NAVER_REDIRECT_URI,
                        "code": code,
                        "state": "bobbeori_naver_state"
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                )
                token_res.raise_for_status()
                token_data = token_res.json()
                if "error" in token_data:
                    raise HTTPException(
                        status_code=400,
                        detail=f"네이버 토큰 발급 실패: {token_data.get('error_description')}"
                    )
                access_token = token_data.get("access_token")

                # 2. 발급받은 토큰으로 사용자 정보 요청
                user_res = await client.get(
                    "https://openapi.naver.com/v1/nid/me",
                    headers={"Authorization": f"Bearer {access_token}"}
                )
                user_res.raise_for_status()
                response_data = user_res.json().get("response", {})
                
                # 3. 네이버 고유 ID 및 프로필 추출하여 반환
                return {
                    "provider_id": str(response_data.get("id")),
                    "email": response_data.get("email"),
                    "nickname": response_data.get("nickname"),
                }
        except httpx.HTTPError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"네이버 인증 서버와 통신 중 오류가 발생했습니다: {str(e)}"
            )

    async def get_google_user(self, code: str) -> dict:
        """
        구글 인가 코드를 이용하여 액세스 토큰을 발급받고,
        해당 토큰으로 사용자 정보를 가져와 정제된 딕셔너리로 반환합니다.
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # 1. 액세스 토큰 요청 (구글 API)
                token_res = await client.post(
                    "https://oauth2.googleapis.com/token",
                    data={
                        "grant_type": "authorization_code",
                        "client_id": settings.GOOGLE_CLIENT_ID,
                        "client_secret": settings.GOOGLE_CLIENT_SECRET,
                        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                        "code": code,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                )
                token_res.raise_for_status()
                access_token = token_res.json().get("access_token")

                # 2. 발급받은 토큰으로 사용자 정보 요청
                user_res = await client.get(
                    "https://www.googleapis.com/oauth2/v3/userinfo",
                    headers={"Authorization": f"Bearer {access_token}"}
                )
                user_res.raise_for_status()
                user_data = user_res.json()
                
                # 3. 구글 고유 ID 및 프로필 추출하여 반환
                return {
                    "provider_id": str(user_data.get("sub")),
                    "email": user_data.get("email"),
                    "nickname": user_data.get("name"),
                }
        except httpx.HTTPError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"구글 인증 서버와 통신 중 오류가 발생했습니다: {str(e)}"
            )

oauth_client = OAuthClient()
