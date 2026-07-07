from datetime import date, datetime, timedelta, time, timezone
import re

# 챗봇 기본 응답 문구
LOGIN_REQUIRED_REPLY = "로그인이 필요한 질문이에요. 비회원 상태에서는 보관법이나 일반 레시피 검색을 이용할 수 있어요."
GENERAL_REPLY = "음식과 관련된 대화만 지원하고 있어요! 요리 레시피, 식재료 보관법, 냉장고 재료 관리 등을 물어봐주세요!"
CANCEL_REPLY = "알겠습니다. 작업을 취소하겠습니다."

# 확인/취소 액션 키워드
CONFIRM_PREFIX = "확인:"
CANCEL_WORDS = ("취소", "아니", "아니요", "취소할게", "안넣어", "넣지마", "추가하지마")

# 의도 분류용 키워드
INVENTORY_ACTION_WORDS = (
    "먹었어",
    "다썼어",
    "다먹었어",
    "버렸어",
    "소비했",
    "사용했",
    "썼어",
    "추가",
    "추가해줘",
    "등록",
    "등록해줘",
    "넣었어",
    "넣어줘",
    "샀어",
    "삿어",
    "사왔어",
    "구매했",
    "삭제",
    "폐기",
    "지워",
)
CALENDAR_WORDS = ("일정", "캘린더")
DELETE_WORDS = ("삭제", "폐기", "지워", "버려")
CONSUME_WORDS = ("먹었어", "다썼어", "다먹었어", "소비했", "사용했", "썼어")
INVENTORY_LIST_WORDS = ("뭐 있어", "뭐 있지", "뭐있", "뭐잇", "머있", "머잇", "뭐이", "목록", "현재 재료", "현재 냉장고")
EXPIRING_WORDS = ("임박", "소비기한", "유통기한", "기한", "적게남", "남은거", "먼저먹", "먹어야", "d-day", "디데이")
ADD_WORDS = ("추가", "등록", "넣", "샀", "삿", "사왔", "구매")

# 식재료 입력 파싱용 기본값
DEFAULT_STORAGE = "냉장"
STORAGE_KEYS = ("냉장", "냉동", "실온")
KOREAN_QUANTITIES = {
    "한": 1,
    "하나": 1,
    "두": 2,
    "둘": 2,
    "세": 3,
    "셋": 3,
    "네": 4,
    "넷": 4,
}


def _normalize_text(text: str) -> str:
    """사용자 문장을 간단 비교할 수 있도록 정리합니다."""
    return text.replace(" ", "").lower()

def _get_josa(word: str, josa_with_jongseong: str, josa_without_jongseong: str) -> str:
    """단어의 마지막 글자 받침 유무에 따라 적절한 조사를 반환합니다."""
    if not word: return josa_with_jongseong
    last_char = word[-1]
    if '가' <= last_char <= '힣':
        has_jongseong = (ord(last_char) - ord('가')) % 28 > 0
        return josa_with_jongseong if has_jongseong else josa_without_jongseong
    return josa_with_jongseong


def _confirm_action(label: str, command: str) -> dict:
    """쓰기 작업 전 사용자 확인 버튼을 만듭니다."""
    return {"label": label, "data": {"message": command}}


def _inventory_refresh_action() -> dict:
    """냉장고 목록을 다시 불러오도록 프론트에 전달할 액션을 만듭니다."""
    return {"label": "냉장고 새로고침", "data": {"refreshInventory": True}}


def _quantity_text(quantity: float) -> str:
    """수량을 사용자가 읽기 좋은 형태로 바꿉니다."""
    number = float(quantity or 1)
    return str(int(number)) if number.is_integer() else str(number)


def _extract_quantity(text: str) -> float | None:
    """사용자 문장에서 수량만 간단히 추출합니다."""
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:개|g|kg|ml|l)?", text, re.IGNORECASE)
    if match:
        return float(match.group(1))
    normalized = text.replace(" ", "")
    for word, quantity in KOREAN_QUANTITIES.items():
        if f"{word}개" in normalized:
            return float(quantity)
    return None


def _extract_delete_name(text: str) -> str:
    """삭제/폐기 문장에서 식재료명만 간단히 추출합니다."""
    target = text
    for word in DELETE_WORDS:
        if word in target:
            target = target.split(word, 1)[0]
            break
    for token in ("냉장고에서", "냉장고에", "냉장고", "재료", "식재료", "어제", "오늘", "방금"):
        target = target.replace(token, " ")
    target = re.sub(r"\s+(다|전부|모두)$", "", target.rstrip())
    return target.strip().rstrip("을를은는이가도")


def _extract_consume_name(text: str) -> str:
    """소비 문장에서 식재료명만 간단히 추출합니다."""
    target = text
    for word in CONSUME_WORDS:
        if word in target:
            target = target.split(word, 1)[0]
            break
    target = re.sub(r"\d+(?:\.\d+)?\s*(?:개|g|kg|ml|l)?", " ", target, flags=re.IGNORECASE)
    for token in ("냉장고에서", "냉장고에", "냉장고", "재료", "식재료", "어제", "오늘", "방금"):
        target = target.replace(token, " ")
    target = re.sub(r"\s+(다|전부|모두)$", "", target.rstrip())
    return target.strip(" ,/\t\n을를은는이가도")


def _extract_storage(text: str) -> str | None:
    """사용자 문장에서 보관 위치를 추출합니다."""
    for storage in STORAGE_KEYS:
        if storage in text:
            return storage
    return None


def _strip_add_name(name: str) -> str:
    """추가 문장에서 식재료명에 붙은 불필요한 단어를 정리합니다."""
    cleaned = name.strip()
    cleaned = re.sub(r"^(그러면|그럼|그리고|아니면|아|음|자)\s+", "", cleaned)
    for token in ('냉장고에서', '냉장고에', '냉장고', '재료', '식재료', '어제', '오늘', '방금'):
        cleaned = cleaned.replace(token, " ")
    for storage in STORAGE_KEYS:
        cleaned = re.sub(rf"(?<![가-힣A-Za-z0-9]){storage}(?![가-힣A-Za-z0-9])", " ", cleaned)
    cleaned = cleaned.strip(" ,/\t\n").rstrip("을를은는이가")
    # '양파도 추가해줘'처럼 이어 말한 조사만 제거하되, 포도/아보카도 같은 재료명은 보존합니다.
    if cleaned.endswith("도") and (" " in cleaned or (len(cleaned) > 2 and not cleaned.endswith(('포도', '아보카도')))):
        cleaned = cleaned[:-1].rstrip()
    return cleaned


def _extract_add_items(text: str) -> list[dict]:
    """추가 요청에서 식재료명, 수량, 보관 위치를 간단히 추출합니다."""
    target = text
    for word in ADD_WORDS:
        if word in target:
            target = target.split(word, 1)[0]
            break
    items = []
    for raw_part in re.split(r"[,/]", target):
        part = raw_part.strip()
        if not part:
            continue
        storage = _extract_storage(part)
        quantity = _extract_quantity(part)
        name = re.sub(r"\d+(?:\.\d+)?\s*(?:개|g|kg|ml|l)?", " ", part, flags=re.IGNORECASE)
        for word in KOREAN_QUANTITIES:
            name = name.replace(f"{word}개", " ")
        name = _strip_add_name(name)
        if name:
            items.append({"name": name, "quantity": quantity, "storage": storage})
    return items

from typing import Any

def _extract_keyword(text: str) -> str:
    cleaned = re.sub(
        r"(먹다\s*남은|먹다남은|남은|먹다|어떡하지|어떡해|어떻게하지|보관법|보관방법|보관해|보관|세척법|세척방법|세척|씻|손질법|손질방법|손질|신선도|확인법|확인|어떻게|가이드|레시피|요리|추천|알려줘|찾아줘|해줘|좀|해먹을|만들)",
        " ",
        text,
    )
    words = [word.strip() for word in cleaned.split() if word.strip() and word.strip() not in ("내", "제", "나", "어떤", "무슨", "이", "그", "저", "이런", "그런", "저런", "수", "있어", "있어?", "있나요", "있나요?")]
    return words[0] if words else text.strip()

def _extract_recipe_ingredient(text: str) -> str:
    match = re.search(r"(?:남은\s*)?([가-힣A-Za-z0-9]+?)(?:으로|로).*(?:뭐|뭘|무엇|메뉴|레시피|요리|만들|추천)", text)
    if not match:
        match = re.search(r"(?:남은\s*)?([가-힣A-Za-z0-9]+?)\s*(?:빨리|먼저|써야|처리).*(?:뭐|뭘|무엇|메뉴|레시피|요리|추천|하지)", text)
    if not match:
        match = re.search(r"^\s*(?:먹다\s*남은|먹다남은|남은)?\s*([가-힣A-Za-z0-9]+?)\s*(?:어디에\s*)?(?:쓸\s*수|쓸수|활용|처리)", text)
    if not match:
        return ""
    keyword = match.group(1).strip()
    if keyword in ("걸", "있는", "이걸", "이것", "그걸", "그것", "재료", "식재료", "보유재료", "냉장고", "내", "제", "나", "내식재료", "제식재료", "남은거"):
        return ""
    return _normalize_recipe_keyword(keyword)

def _normalize_recipe_keyword(keyword: str) -> str:
    aliases = {"파": "대파"}
    return aliases.get(keyword, keyword)

def _recipe_actions(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for item in items[:3]:
        recipe_id = item.get("recipe_id")
        title = item.get("title")
        if not recipe_id or not title:
            continue
        actions.append({"label": title, "url": f"/recipes/{recipe_id}", "data": {"recipe_id": recipe_id, "title": title}})
    return actions

def _rank_recipe_items(keyword: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized_keyword = keyword.replace(" ", "")
    def score(item: dict[str, Any]) -> tuple[int, int, int]:
        title = (item.get("title") or "").replace(" ", "")
        difficulty = item.get("difficulty") or ""
        cooking_time = item.get("cooking_time_min") or 9999
        return (
            0 if normalized_keyword and normalized_keyword in title else 1,
            0 if difficulty == "초급" else 1,
            int(cooking_time),
        )
    return sorted(items, key=score)

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

def _extract_expiry_keyword(text: str) -> str:
    match = re.search(r"([가-힣A-Za-z0-9]+)\s*(?:유통기한|소비기한|기한)", text)
    if not match:
        match = re.search(r"^\s*(?:먹다\s*남은|먹다남은|남은)?\s*([가-힣A-Za-z0-9]+?)\s*(?:어디에\s*)?(?:쓸\s*수|쓸수|활용|처리)", text)
    if not match:
        return ""
    keyword = match.group(1).strip()
    if keyword in ("재료", "냉장고", "오늘"):
        return ""
    return keyword

def _format_d_day(d_day: int) -> str:
    if d_day > 0:
        return f"D-{d_day}"
    if d_day == 0:
        return "D-Day"
    return f"D+{abs(d_day)} 지남"

def _is_guide_result_match(keyword: str, guide_name: str) -> bool:
    normalized_keyword = keyword.replace(" ", "").lower()
    normalized_name = guide_name.replace(" ", "").lower()
    aliases = {"파": {"대파", "쪽파", "실파"}, "계란": {"달걀"}, "달걀": {"계란"}}
    if normalized_keyword == normalized_name or normalized_name in aliases.get(normalized_keyword, set()):
        return True
    if len(normalized_keyword) <= 1:
        return False
    misleading_suffixes = ("소스", "가루", "분말", "즙", "청", "오일", "잼", "스톡")
    if normalized_name.startswith(normalized_keyword) and normalized_name.endswith(misleading_suffixes):
        return False
    if normalized_name.startswith(normalized_keyword) and any(suffix in normalized_name for suffix in misleading_suffixes):
        return False
    return normalized_keyword in normalized_name or normalized_name in normalized_keyword

def _keyword_tokens(keyword: str) -> list[str]:
    stopwords = {"먹다남은", "남은", "먹다", "보관", "보관법", "보관방법", "세척", "세척법", "세척방법", "손질", "손질법", "손질방법", "신선도", "확인법", "알려줘", "식재료", "레시피", "어떡하지", "어떡해"}
    return [
        token
        for token in re.findall(r"[가-힣A-Za-z0-9]+", keyword.lower())
        if len(token) > 1 and token not in stopwords
    ]

def _format_guide_tip(tip: str) -> str:
    sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?。])\s+", tip) if sentence.strip()]
    if len(sentences) <= 1:
        sentences = [sentence.strip() for sentence in re.split(r"[;；]\s*", tip) if sentence.strip()]
    if len(sentences) <= 1:
        return sentences[0] if sentences else tip.strip()
    return "\n".join(f"{index + 1}. {sentence}" for index, sentence in enumerate(sentences[:3]))


def _pending_calendar_from_history(history) -> tuple[str, str] | None:
    """최근 봇의 일정 등록 확인 문구에서 제목과 날짜를 찾습니다."""
    text = _latest_bot_text(history)
    match = re.search(r"'(.+?)'\s+일정을\s+(\d{4}-\d{2}-\d{2} \d{2}:\d{2})에\s+등록할까요", text)
    return (match.group(1), match.group(2)) if match else None

def _pending_add_many_from_history(history) -> bool:
    """최근 봇 응답이 여러 식재료 수량을 기다리는지 확인합니다."""
    return "각 식재료의 수량" in _latest_bot_text(history)

def _is_quantity_only_list(text: str) -> bool:
    """여러 재료 추가 대기 중 수량만 나열한 응답인지 확인합니다."""
    parts = [part.strip() for part in re.split(r"[,/]", text) if part.strip()]
    return len(parts) > 1 and all(
        _extract_quantity(part) is not None
        and not _strip_add_name(re.sub(r"\d+(?:\.\d+)?\s*(?:개|g|kg|ml|l)?", " ", part, flags=re.IGNORECASE))
        for part in parts
    )

def _latest_bot_text(history) -> str:
    """가장 최근 봇 응답만 후속 작업 대기 상태로 확인합니다."""
    for message in reversed(history or []):
        if getattr(message, "role", "") == "bot":
            return getattr(message, "text", "")
    return ""

def _extract_storage(text: str) -> str | None:
    """사용자 문장에서 보관 위치를 찾습니다."""
    normalized = text.replace(" ", "")
    aliases = {"냉장실": "냉장", "냉동실": "냉동", "상온": "실온"}
    for alias, storage in aliases.items():
        if alias in normalized:
            return storage
    for storage in STORAGE_KEYS:
        if re.search(rf"(?<![가-힣A-Za-z0-9]){storage}(?![가-힣A-Za-z0-9])", text):
            return storage
    return None

def _pending_add_storage_from_history(history) -> tuple[str, float] | None:
    """최근 봇의 보관 위치 질문에서 추가 대기 중인 식재료명과 수량을 찾습니다."""
    pattern = r"(.+?)\s+(\d+(?:\.\d+)?)개를\s+어디에\s+보관"
    match = re.search(pattern, _latest_bot_text(history))
    return (match.group(1).strip(), float(match.group(2))) if match else None

def _pending_add_from_history(history) -> str | None:
    """최근 봇의 수량 질문에서 추가 대기 중인 식재료명을 찾습니다."""
    patterns = (
        r"(.+?)(?:을|를)\s*몇\s*개.*추가",
        r"(.+?)\s*몇\s*개.*추가",
    )
    text = _latest_bot_text(history)
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip(" \"'.,!?을를")
    return None

def _pending_consume_from_history(history) -> str | None:
    """최근 봇의 수량 질문에서 소비 대기 중인 식재료명을 찾습니다."""
    match = re.search(r"(.+?)(?:을|를) 몇 개 (?:먹|소비)", _latest_bot_text(history))
    return match.group(1).strip() if match else None

def _parse_calendar_date(date_str: str) -> date:
    """챗봇이 뽑은 짧은 날짜 표현을 캘린더 날짜로 변환합니다."""
    text = (date_str or "오늘").strip()
    today = date.today()
    if "모레" in text:
        return today + timedelta(days=2)
    if "내일" in text:
        return today + timedelta(days=1)
    if "오늘" in text:
        return today
    month_day = re.search(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일", text)
    if month_day:
        month, day = map(int, month_day.groups())
        return date(today.year, month, day)
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return today

def _has_calendar_date_text(text: str) -> bool:
    """사용자 원문에 날짜 표현이 있는지 확인합니다."""
    return bool(
        any(word in text for word in ("오늘", "내일", "모레"))
        or re.search(r"\d{1,2}\s*월\s*\d{1,2}\s*일", text)
        or re.search(r"\d{4}-\d{2}-\d{2}", text)
    )

def _calendar_datetime_from_text(text: str, fallback: str) -> datetime:
    """사용자 원문을 우선해 캘린더 일정 시작 시간을 계산합니다."""
    base_date = _parse_calendar_date(text if _has_calendar_date_text(text) else fallback)
    time_match = re.search(r"(오전|오후)?\s*(\d{1,2})\s*시(?:\s*(\d{1,2})\s*분)?", text)
    hour = 9
    minute = 0
    if time_match:
        meridiem, hour_text, minute_text = time_match.groups()
        hour = int(hour_text)
        minute = int(minute_text or 0)
        if meridiem == "오후" and hour < 12:
            hour += 12
        if meridiem == "오전" and hour == 12:
            hour = 0
    elif "T" in fallback:
        try:
            parsed = datetime.fromisoformat(fallback[:19])
            hour, minute = parsed.hour, parsed.minute
        except ValueError:
            pass
    return datetime.combine(base_date, time(hour, minute), timezone(timedelta(hours=9)))

def _calendar_display(value: datetime) -> str:
    """캘린더 확인 문구에 보여줄 날짜와 시간을 만듭니다."""
    return value.strftime("%Y-%m-%d %H:%M")

def _storage_choice_response(name: str, quantity: float, unchecked: bool = False) -> dict:
    """보관 위치 선택 버튼을 만듭니다."""
    text = f"{name} {_quantity_text(quantity)}개를 어디에 보관할까요? 냉장, 냉동, 실온 중에서 알려주세요."
    action = "add_ingredient_unchecked" if unchecked else "add_ingredient"
    return {
        "response_text": text,
        "actions": [
            _confirm_action("냉장", f"확인:{action}:{name}:{quantity}:냉장"),
            _confirm_action("냉동", f"확인:{action}:{name}:{quantity}:냉동"),
            _confirm_action("실온", f"확인:{action}:{name}:{quantity}:실온"),
            _confirm_action("취소", "취소"),
        ],
    }

def _is_login_status_question(text: str) -> bool:
    """사용자가 현재 로그인 상태를 묻는 문장인지 확인합니다."""
    normalized = text.replace(" ", "").lower()
    return "로그인" in normalized and any(word in normalized for word in ("되어", "됐", "되있", "상태", "했", "했어"))

def _requires_login(intent: str, text: str) -> bool:
    """개인 냉장고 데이터가 필요한 챗봇 의도인지 확인합니다."""
    normalized = text.replace(" ", "").lower()
    personal_recipe_words = ("내식재료", "내재료", "보유식재료", "보유재료", "냉장고재료", "있는걸로", "이걸로")
    if intent in ("inventory.list", "inventory.expiring"):
        return True
    if intent == "recipe.recommend" and any(word in normalized for word in personal_recipe_words):
        return True
    if intent == "recipe.recommend" and not _extract_recipe_ingredient(text):
        return True
    return False

def _is_cooking_time_question(text: str) -> bool:
    """조리 시간이나 온도를 묻는 질문인지 확인합니다."""
    normalized = text.replace(" ", "").lower()
    return any(word in normalized for word in ("에어프라이", "몇분", "몇도", "온도", "조리시간", "굽는시간", "익히는시간"))

def _is_expiring_question(text: str) -> bool:
    """소비기한 임박 재료를 묻는 질문인지 먼저 확인합니다."""
    normalized = text.replace(" ", "").lower()
    return any(word in normalized for word in ("상하는", "임박", "소비기한", "유통기한", "기한", "적게남", "남은거", "먼저먹", "먹어야", "다되어", "다돼", "끝나", "d-day", "디데이"))

def _is_relevant_search_result(keyword: str, item: dict[str, Any]) -> bool:
    """검색 결과 제목/본문이 질문 핵심어와 맞는지 확인합니다."""
    tokens = _keyword_tokens(keyword)
    if not tokens:
        return False

    haystack = f"{item.get('title', '')} {item.get('content', '')}".lower()
    words = _keyword_tokens(haystack)
    primary = tokens[0]
    return any(_is_guide_result_match(primary, word) for word in words)
