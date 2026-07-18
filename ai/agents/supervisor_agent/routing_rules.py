import re

_RECIPE_RECOMMEND_PHRASES = (
    "뭐해먹", "뭐먹", "만들어먹", "요리추천", "메뉴추천", "추천메뉴", "냉장고파먹",
)
_RECIPE_SEARCH_PHRASES = ("레시피", "요리법", "요리방법")
_GUIDE_PHRASES = (
    "보관법", "보관방법", "보관해", "어떻게보관", "보관어떻게", "손질법", "손질방법",
    "손질해", "어떻게손질", "세척법", "세척방법", "세척해", "씻는법", "어떻게씻", "식재료가이드",
    "신선도", "상했", "상한", "물러", "곰팡이",
    "영양", "영양성분", "칼로리", "열량", "단백질", "탄수화물", "지방",
    "당류", "나트륨", "제철",
)
_GUIDE_CATEGORY_WORDS = (
    "채소", "과일", "버섯", "육류", "수산물", "해산물", "곡류", "유제품", "가공식품", "발효식품", "조미료",
)
_GUIDE_LIST_PHRASES = ("뭐가있", "어떤재료", "무슨재료", "종류", "목록", "리스트", "분류")


def _normalize_text(text: str) -> str:
    """사용자 문장을 간단 비교할 수 있도록 정리합니다."""
    return text.replace(" ", "").lower()


def _is_food_general_query(text: str) -> bool:
    """식품 비교나 남은 음식 재가열처럼 전담 Agent가 없는 일반 요리 질문인지 확인합니다."""
    normalized = _normalize_text(text)
    if any(word in normalized for word in ("가격", "최저가", "얼마")):
        return False
    is_reheating = any(word in normalized for word in ("데우", "재가열", "다시가열", "다시익히"))
    is_comparison = (
        any(word in normalized for word in ("차이", "뭐가달라", "어떻게달라", "비교"))
        and bool(re.search(r"(?:와|과|랑|이랑|vs|대비)", normalized, re.IGNORECASE))
    )
    return is_reheating or is_comparison

def _is_receipt_query(text: str) -> bool:
    """영수증 또는 OCR 사용 방법을 묻는 요청인지 확인합니다."""
    normalized = _normalize_text(text)
    return any(word in normalized for word in ("영수증", "ocr", "구매내역"))


def _is_alarm_notification_query(text: str) -> bool:
    """캘린더 일정이 아닌 알림 관리 요청인지 확인합니다."""
    normalized = _normalize_text(text)
    notification_words = ("알림", "알람", "리마인더", "디바이스", "푸시토큰", "읽음", "읽었")
    return any(word in normalized for word in notification_words) and not _is_alarm_calendar_query(text)


def _is_alarm_calendar_query(text: str) -> bool:
    """캘린더 일정 관리 요청인지 확인합니다."""
    normalized = _normalize_text(text)
    return any(word in normalized for word in ("일정", "캘린더"))

def _is_alarm_write_query(text: str) -> bool:
    """알림 또는 일정 데이터를 변경하는 요청인지 확인합니다."""
    normalized = _normalize_text(text)
    write_words = ("등록", "추가", "생성", "삭제", "지워", "취소", "수정", "변경", "읽음", "동기화", "연결", "해제")
    return (
        _is_alarm_notification_query(text) or _is_alarm_calendar_query(text)
    ) and any(word in normalized for word in write_words)


def _is_shopping_price_query(text: str) -> bool:
    """상품 가격 또는 최저가를 묻는 요청인지 확인합니다."""
    normalized = _normalize_text(text)
    return any(word in normalized for word in ("가격", "최저가", "싼곳", "싼데", "저렴", "비싸"))


def _is_shopping_price_explanation(text: str) -> bool:
    """가격 정보가 표시되지 않는 이유를 묻는 후속 질문인지 확인합니다."""
    normalized = _normalize_text(text)
    return "가격정보" in normalized and any(word in normalized for word in ("안나", "없", "이유", "왜"))



def _is_recipe_pairing_query(text: str) -> bool:
    """특정 음식과 함께 먹을 메뉴를 묻는 요청인지 확인합니다."""
    normalized = _normalize_text(text)
    phrases = ("이랑먹기좋은", "같이먹기좋은", "어울리는음식", "곁들일", "곁들이", "사이드메뉴", "반찬추천")
    return any(phrase in normalized for phrase in phrases)


def _is_recipe_recommend_query(text: str) -> bool:
    """메뉴 또는 보유 재료 활용 추천 요청인지 확인합니다."""
    normalized = _normalize_text(text)
    inventory_context = ("냉장고", "보유재료", "보유식재료", "내재료", "내식재료")
    recipe_goal = ("레시피", "요리", "메뉴", "음식")
    return (
        any(word in normalized for word in inventory_context)
        and any(word in normalized for word in recipe_goal)
    ) or any(phrase in normalized for phrase in _RECIPE_RECOMMEND_PHRASES)


def _is_recipe_search_query(text: str) -> bool:
    """특정 레시피나 요리법 검색 요청인지 확인합니다."""
    normalized = _normalize_text(text)
    return any(phrase in normalized for phrase in _RECIPE_SEARCH_PHRASES)

def _is_guide_query(text: str) -> bool:
    """명시적인 식재료 가이드 또는 분류 목록 질문인지 확인합니다."""
    normalized = _normalize_text(text)
    if any(phrase in normalized for phrase in _RECIPE_RECOMMEND_PHRASES):
        return False
    if any(phrase in normalized for phrase in _GUIDE_PHRASES):
        return True
    if any(word in normalized for word in ("냉장고", "냉동고", "냉장실", "냉동실")):
        return False
    return (
        any(category in normalized for category in _GUIDE_CATEGORY_WORDS)
        and any(phrase in normalized for phrase in _GUIDE_LIST_PHRASES)
    )

def _apply_josa(word: str, josa_type: str) -> str:
    if not word: return ""
    last_char = word[-1]
    if not ('가' <= last_char <= '힣'):
        return word + ("가" if josa_type == "이가" else "는" if josa_type == "은는" else "를")
    has_jongseong = (ord(last_char) - 44032) % 28 > 0
    if josa_type == "이가":
        return word + ("이" if has_jongseong else "가")
    elif josa_type == "은는":
        return word + ("은" if has_jongseong else "는")
    elif josa_type == "을를":
        return word + ("을" if has_jongseong else "를")
    elif josa_type == "과와":
        return word + ("과" if has_jongseong else "와")
    return word

def _is_login_status_question(text: str) -> bool:
    """사용자가 현재 로그인 상태를 묻는 문장인지 확인합니다."""
    normalized = text.replace(" ", "").lower()
    return "로그인" in normalized and any(word in normalized for word in ("되어", "됐", "되있", "상태", "했", "했어"))

def _is_cooking_time_question(text: str) -> bool:
    """조리 시간이나 온도를 묻는 질문인지 확인합니다."""
    normalized = text.replace(" ", "").lower()
    return any(word in normalized for word in ("에어프라이", "몇분", "몇도", "온도", "조리시간", "굽는시간", "익히는시간"))

def _is_expiring_question(text: str) -> bool:
    """소비기한 임박 재료를 묻는 질문인지 먼저 확인합니다."""
    normalized = text.replace(" ", "").lower()
    return any(word in normalized for word in ("상하는", "임박", "소비기한", "유통기한", "기한", "적게남", "남은거", "먼저먹", "먹어야", "다되어", "다돼", "끝나", "d-day", "디데이"))

def _build_read_tasks(text: str) -> list[dict[str, str]]:
    """복합 조회 요청을 기존 Agent가 처리할 순차 작업 목록으로 분해합니다."""
    intents = []
    normalized = _normalize_text(text)

    if any(phrase in normalized for phrase in _GUIDE_PHRASES):
        intents.append("ingredient.guide")
    if _is_expiring_question(text):
        intents.append("inventory.expiring")
    if _is_shopping_price_query(text):
        intents.append("shopping.compare")
    if _is_recipe_pairing_query(text):
        intents.append("recipe.pairing")
    elif _is_cooking_time_question(text):
        intents.append("recipe.search")
    elif _is_recipe_recommend_query(text):
        intents.append("recipe.recommend")
    elif _is_recipe_search_query(text):
        intents.append("recipe.search")

    tasks = [{"intent": intent, "text": text} for intent in dict.fromkeys(intents)]
    if "ingredient.guide" in intents and "shopping.compare" in intents:
        price_text = re.sub(
            r"^.+?(?:보관법|보관방법|손질법|손질방법|세척법|세척방법|영양성분|칼로리|제철)"
            r"(?:이랑|랑|과|와|그리고)?\s*",
            "",
            text,
        ).strip()
        if price_text.startswith(("가격", "최저가", "얼마")):
            ingredient = text.split(maxsplit=1)[0]
            price_text = f"{ingredient} {price_text}"
        for task in tasks:
            if task["intent"] == "shopping.compare":
                task["text"] = price_text or text
    return tasks
