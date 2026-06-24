from sqlalchemy.orm import Session
from app.backend.db.models import UserPreference
from app.backend.schemas.onboarding import OnboardingRequest, OnboardingResponse
from datetime import datetime

class OnboardingService:
    def get_onboarding(self, db: Session, user_id: int) -> dict:
        """
        주어진 user_id의 온보딩 설정 정보를 반환합니다.
        DB에 쉼표로 저장된 문자열을 리스트로 복원합니다.
        데이터가 없는 경우 기본값 딕셔너리를 반환합니다.
        """
        onboarding = db.query(UserPreference).filter(UserPreference.user_id == user_id).first()
        
        if not onboarding:
            return {
                "id": 0,
                "user_id": user_id,
                "disliked_ingredients": [],
                "allergy": [],
                "preferred_ingredients": [],
                "is_alert_allowed": True,
                "updated_at": None
            }
            
        return {
            "id": onboarding.id,
            "user_id": onboarding.user_id,
            "disliked_ingredients": [x.strip() for x in onboarding.disliked_ingredients.split(",") if x.strip()] if onboarding.disliked_ingredients else [],
            "allergy": [x.strip() for x in onboarding.allergies.split(",") if x.strip()] if onboarding.allergies else [],
            "preferred_ingredients": [x.strip() for x in onboarding.preferred_ingredients.split(",") if x.strip()] if onboarding.preferred_ingredients else [],
            "is_alert_allowed": onboarding.allow_expiry_alert,
            "updated_at": None
        }

    def save_onboarding(self, db: Session, user_id: int, data: OnboardingRequest) -> dict:
        """
        주어진 user_id에 대한 온보딩 설정 정보를 생성하거나 업데이트합니다.
        List[str]을 쉼표로 연결된 문자열로 직렬화하여 DB에 저장합니다.
        """
        # 리스트 내의 유효한 값만 필터링하여 쉼표 구분 문자열로 변환 (빈 리스트는 None 처리)
        valid_dislikes = [x.strip() for x in (data.disliked_ingredients or []) if x.strip()]
        disliked_str = ",".join(valid_dislikes) if valid_dislikes else None
        
        valid_allergies = [x.strip() for x in (data.allergy or []) if x.strip()]
        allergy_str = ",".join(valid_allergies) if valid_allergies else None
        
        valid_preferred = [x.strip() for x in (data.preferred_ingredients or []) if x.strip()]
        preferred_str = ",".join(valid_preferred) if valid_preferred else None
        
        onboarding = db.query(UserPreference).filter(UserPreference.user_id == user_id).first()
        
        if onboarding:
            # 기존 레코드가 있으면 UPDATE
            onboarding.disliked_ingredients = disliked_str
            onboarding.allergies = allergy_str
            onboarding.preferred_ingredients = preferred_str
            onboarding.allow_expiry_alert = data.is_alert_allowed
        else:
            # 기존 레코드가 없으면 INSERT
            onboarding = UserPreference(
                user_id=user_id,
                disliked_ingredients=disliked_str,
                allergies=allergy_str,
                preferred_ingredients=preferred_str,
                allow_expiry_alert=data.is_alert_allowed
            )
            db.add(onboarding)
            
        db.commit()
        db.refresh(onboarding)
        
        # 저장 후, 프론트엔드가 요구하는 Response 형태로 다시 파싱하여 반환
        return {
            "id": onboarding.id,
            "user_id": onboarding.user_id,
            "disliked_ingredients": data.disliked_ingredients,
            "allergy": data.allergy,
            "is_alert_allowed": onboarding.allow_expiry_alert,
            "updated_at": None
        }

onboarding_service = OnboardingService()
