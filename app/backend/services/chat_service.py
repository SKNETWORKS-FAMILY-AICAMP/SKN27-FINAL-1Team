import re
from typing import Any

from sqlalchemy.orm import Session

from app.backend.services.guide_service.guide_service import guide_service
from app.backend.services.inventory_service.inventory_service import inventory_service
from app.backend.services.recommendation_service.recipe_search_service import recipe_search_service
from app.backend.services.recommendation_service.recommend_config import RecipeRecommendConfig
from app.backend.services.recommendation_service.recommendation_service import recommendation_service


class ChatService:
    """사용자 자연어 메시지를 간단한 intent로 분류하고 기존 서비스를 호출합니다."""

    def handle_message(self, db: Session, user_id: int, message: str) -> dict[str, str]:
        """메시지를 처리하고 챗봇 응답 딕셔너리를 반환합니다."""
        text = message.strip()
        intent = self._route_intent(text)

        try:
            if intent == "inventory.list":
                reply = self._reply_inventory_list(db, user_id)
            elif intent == "inventory.expiring":
                reply = self._reply_expiring_items(db, user_id)
            elif intent == "ingredient.guide":
                reply = self._reply_guide(text)
            elif intent == "recipe.recommend":
                reply = self._reply_recipe_recommend(db, user_id)
            elif intent == "recipe.search":
                reply = self._reply_recipe_search(db, text)
            elif intent == "receipt.guide":
                reply = "영수증은 파일 업로드가 필요해서 상단 메뉴의 영수증 OCR 화면에서 등록해주세요."
            else:
                reply = "냉장고 재료 조회, 소비기한 임박 재료, 보관법, 레시피 추천을 물어볼 수 있어요."
        except Exception:
            reply = "요청을 처리하는 중 문제가 생겼어요. 잠시 후 다시 시도해주세요."

        return {"intent": intent, "reply": reply}

    def _route_intent(self, text: str) -> str:
        """키워드 기반으로 1차 챗봇 intent를 분류합니다."""
        normalized = text.replace(" ", "").lower()

        if any(word in normalized for word in ("영수증", "ocr", "구매내역")):
            return "receipt.guide"
        if any(word in normalized for word in ("보관법", "보관방법", "손질", "신선", "가이드")):
            return "ingredient.guide"
        # 유통기한 질문에 "뭐 있어"가 섞여도 목록보다 임박 조회를 우선합니다.
        if any(word in normalized for word in ("상하는", "임박", "소비기한", "유통기한", "기한", "다되어", "다돼", "끝나", "d-day", "디데이")):
            return "inventory.expiring"
        if any(word in normalized for word in ("뭐있", "뭐가있", "냉장고목록", "재료목록", "내재료")):
            return "inventory.list"
        if any(word in normalized for word in ("추천", "뭐해먹", "뭐먹", "만들수", "만들수있는", "만들수있", "만들 수", "메뉴", "냉장고파먹")):
            return "recipe.recommend"
        if "레시피" in normalized or "요리" in normalized:
            return "recipe.search"
        return "general"

    def _extract_keyword(self, text: str) -> str:
        """조사와 기능 키워드를 덜어내고 검색에 쓸 핵심 단어를 추립니다."""
        cleaned = re.sub(r"(보관법|보관방법|손질법|가이드|레시피|요리|추천|알려줘|찾아줘|해줘|은|는|이|가|을|를|로|으로|에|의|좀|해먹을|만들)", " ", text)
        words = [word.strip() for word in cleaned.split() if word.strip()]
        return words[0] if words else text.strip()

    def _reply_inventory_list(self, db: Session, user_id: int) -> str:
        """냉장고 보유 재료를 짧게 요약합니다."""
        items = inventory_service.get_ingredients(db=db, user_id=user_id)
        if not items:
            return "현재 냉장고에 등록된 재료가 없어요."

        names = [item["name"] for item in items[:8]]
        suffix = "" if len(items) <= 8 else f" 외 {len(items) - 8}개"
        return f"현재 냉장고에는 {', '.join(names)}{suffix}가 있어요."

    def _reply_expiring_items(self, db: Session, user_id: int) -> str:
        """소비기한이 가까운 재료를 D-day 기준으로 안내합니다."""
        items = inventory_service.get_ingredients(db=db, user_id=user_id)
        expiring = sorted(
            [item for item in items if item.get("d_day") is not None and item["d_day"] <= 3],
            key=lambda item: item["d_day"],
        )
        if not expiring:
            return "D-3 이내로 임박한 재료는 없어요."

        summary = [f"{item['name']} {self._format_d_day(item['d_day'])}" for item in expiring[:5]]
        return "소비기한이 가까운 재료는 " + ", ".join(summary) + "예요."

    def _format_d_day(self, d_day: int) -> str:
        """프론트와 같은 기준으로 D-day 문구를 표시합니다."""
        if d_day > 0:
            return f"D-{d_day}"
        if d_day == 0:
            return "D-Day"
        return f"D+{abs(d_day)} 지남"

    def _reply_guide(self, text: str) -> str:
        """식재료 가이드 검색 결과를 이용해 보관 정보를 안내합니다."""
        keyword = self._extract_keyword(text)
        guides = guide_service.search_guides(keyword=keyword, page=1, page_size=1)
        if not guides["items"]:
            return f"{keyword} 보관 가이드를 찾지 못했어요."

        item = guides["items"][0]
        detail = guide_service.get_guide_detail(item["code"]) or {}
        tip = detail.get("storage_tips") or detail.get("horticultural_storage_tips")
        if not tip:
            return f"{item['name']} 가이드는 찾았지만 보관법 정보가 비어 있어요."
        return f"{item['name']} 보관법: {tip}"

    def _reply_recipe_search(self, db: Session, text: str) -> str:
        """레시피명 또는 재료명 검색 결과를 안내합니다."""
        keyword = self._extract_keyword(text)
        result = recipe_search_service.search_recipes(db=db, query=keyword, page=1, page_size=3)
        items: list[dict[str, Any]] = result["items"]
        if not items:
            result = recipe_search_service.search_recipes(db=db, ingredient=keyword, page=1, page_size=3)
            items = result["items"]
        if not items:
            return f"{keyword} 관련 레시피를 찾지 못했어요."

        titles = [item["title"] for item in items]
        return "찾은 레시피는 " + ", ".join(titles) + "예요."

    def _reply_recipe_recommend(self, db: Session, user_id: int) -> str:
        """냉장고 재료 기반 레시피 추천 결과를 안내합니다."""
        result = recommendation_service.recommend_recipes(
            db,
            user_id,
            RecipeRecommendConfig.fridge_consume_preset(),
        )
        items: list[dict[str, Any]] = [
            item for item in result.get("items", []) if item.get("missing_ingredient_count", 0) == 0
        ]
        if not items:
            return "현재 냉장고 재료만으로 완성 가능한 레시피를 찾지 못했어요. 부족 재료를 허용하면 더 넓게 추천할 수 있어요."

        titles = [item["title"] for item in items[:3]]
        return "현재 냉장고 재료만으로는 " + ", ".join(titles) + "를 만들 수 있어요."


chat_service = ChatService()
