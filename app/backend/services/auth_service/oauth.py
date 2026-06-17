import httpx
from app.backend.core.config import settings

class OAuthClient:
    async def get_kakao_user(self, code: str) -> dict:
        """
        카카오 인가 코드를 이용하여 액세스 토큰을 발급받고,
        해당 토큰으로 사용자 정보를 가져와 정제된 딕셔너리로 반환합니다.
        """
        async with httpx.AsyncClient() as client:
            # 액세스 토큰 요청
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

            # 사용자 정보 요청
            user_res = await client.get(
                "https://kapi.kakao.com/v2/user/me",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            user_res.raise_for_status()
            user_data = user_res.json()
            
            # 카카오 고유 ID 및 프로필 획득
            return {
                "provider_id": str(user_data.get("id")),
                "email": user_data.get("kakao_account", {}).get("email"),
                "nickname": user_data.get("properties", {}).get("nickname"),
            }

    async def get_naver_user(self, code: str) -> dict:
        """
        네이버 인가 코드를 이용하여 액세스 토큰을 발급받고,
        해당 토큰으로 사용자 정보를 가져와 정제된 딕셔너리로 반환합니다.
        """
        async with httpx.AsyncClient() as client:
            # 액세스 토큰 요청
            token_res = await client.post(
                "https://nid.naver.com/oauth2.0/token",
                data={
                    "grant_type": "authorization_code",
                    "client_id": settings.NAVER_CLIENT_ID,
                    "client_secret": settings.NAVER_CLIENT_SECRET,
                    "redirect_uri": settings.NAVER_REDIRECT_URI,
                    "code": code,
                    "state": "naver_login_state"
                }
            )
            token_res.raise_for_status()
            access_token = token_res.json().get("access_token")

            # 사용자 정보 요청
            user_res = await client.get(
                "https://openapi.naver.com/v1/nid/me",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            user_res.raise_for_status()
            response_data = user_res.json().get("response", {})
            
            # 네이버 고유 ID 및 프로필 획득
            return {
                "provider_id": str(response_data.get("id")),
                "email": response_data.get("email"),
                "nickname": response_data.get("nickname"),
            }

    async def get_google_user(self, code: str) -> dict:
        """
        구글 인가 코드를 이용하여 액세스 토큰을 발급받고,
        해당 토큰으로 사용자 정보를 가져와 정제된 딕셔너리로 반환합니다.
        """
        async with httpx.AsyncClient() as client:
            # 액세스 토큰 요청
            token_res = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "grant_type": "authorization_code",
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                    "code": code,
                }
            )
            token_res.raise_for_status()
            access_token = token_res.json().get("access_token")

            # 사용자 정보 요청
            user_res = await client.get(
                "https://www.googleapis.com/oauth2/v3/userinfo",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            user_res.raise_for_status()
            user_data = user_res.json()
            
            # 구글 고유 ID 및 프로필 획득
            return {
                "provider_id": str(user_data.get("sub")),
                "email": user_data.get("email"),
                "nickname": user_data.get("name"),
            }

oauth_client = OAuthClient()
