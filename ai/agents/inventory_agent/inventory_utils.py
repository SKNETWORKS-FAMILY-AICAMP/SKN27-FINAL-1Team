import re

# 확인/취소 액션 키워드
CONFIRM_PREFIX = "확인:"
CANCEL_WORDS = ("취소", "아니", "아니요", "취소할게", "안넣어", "넣지마", "추가하지마")

# 의도 분류용 키워드
DELETE_WORDS = ("삭제", "폐기", "지워", "버려")
CONSUME_WORDS = ("먹었어", "다썼어", "다먹었어", "소비했", "소비해", "소비", "사용했", "썼어")
ADD_WORDS = ("추가", "등록", "넣", "샀", "삿", "사왔", "구매")
INVENTORY_LIST_WORDS = ("뭐있", "뭐가있", "냉장고목록", "재료목록", "내재료")
EXPIRING_WORDS = ("상하는", "임박", "소비기한", "유통기한", "기한", "적게남", "먼저먹", "먹어야", "다되어", "다돼", "끝나", "d-day", "디데이")

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

def _confirm_action(label: str, command: str) -> dict:
    return {"label": label, "data": {"message": command}}

def _inventory_refresh_action() -> dict:
    return {"label": "냉장고 새로고침", "data": {"refreshInventory": True}}

def _quantity_text(quantity: float) -> str:
    number = float(quantity or 1)
    return str(int(number)) if number.is_integer() else str(number)

def _extract_quantity(text: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:개|g|kg|ml|l)?", text, re.IGNORECASE)
    if match:
        return float(match.group(1))
    normalized = text.replace(" ", "")
    for word, quantity in KOREAN_QUANTITIES.items():
        if f"{word}개" in normalized:
            return float(quantity)
    return None

def _extract_delete_name(text: str) -> str:
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
    normalized = text.replace(" ", "")
    aliases = {"냉장실": "냉장", "냉동실": "냉동", "상온": "실온"}
    for alias, storage in aliases.items():
        if alias in normalized:
            return storage
    for storage in STORAGE_KEYS:
        if re.search(rf"(?<![가-힣A-Za-z0-9]){storage}(?![가-힣A-Za-z0-9])", text):
            return storage
    return None

def _strip_add_name(name: str) -> str:
    cleaned = name.strip()
    cleaned = re.sub(r"^(그러면|그럼|그리고|아니면|아|음|자)\s+", "", cleaned)
    for token in ('냉장실에', '냉동실에', '냉장고에서', '냉장고에', '냉장고', '재료', '식재료', '어제', '오늘', '방금'):
        cleaned = cleaned.replace(token, " ")
    for storage in STORAGE_KEYS:
        cleaned = re.sub(rf"(?<![가-힣A-Za-z0-9]){storage}(?![가-힣A-Za-z0-9])", " ", cleaned)
    cleaned = cleaned.strip(" ,/\t\n").rstrip("을를은는이가")
    if cleaned.endswith("도") and (" " in cleaned or (len(cleaned) > 2 and not cleaned.endswith(('포도', '아보카도')))):
        cleaned = cleaned[:-1].rstrip()
    return cleaned

def _extract_add_items(text: str) -> list[dict]:
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

def _latest_bot_text(history) -> str:
    for message in reversed(history or []):
        if getattr(message, "role", "") == "bot":
            return getattr(message, "text", "")
    return ""

def _pending_add_many_from_history(history) -> bool:
    return "각 식재료의 수량" in _latest_bot_text(history)

def _is_quantity_only_list(text: str) -> bool:
    parts = [part.strip() for part in re.split(r"[,/]", text) if part.strip()]
    return len(parts) > 1 and all(
        _extract_quantity(part) is not None
        and not _strip_add_name(re.sub(r"\d+(?:\.\d+)?\s*(?:개|g|kg|ml|l)?", " ", part, flags=re.IGNORECASE))
        for part in parts
    )

def _pending_add_storage_from_history(history) -> tuple[str, float] | None:
    pattern = r"(.+?)\s+(\d+(?:\.\d+)?)개를\s+어디에\s+보관"
    match = re.search(pattern, _latest_bot_text(history))
    return (match.group(1).strip(), float(match.group(2))) if match else None

def _pending_add_from_history(history) -> str | None:
    """직전 봇 질문에서 추가 대기 중인 식재료명을 찾습니다."""
    patterns = (
        (r"(.+?)(?:을|를)\s*몇\s*개.*추가", False),
        (r"(.+?)\s*몇\s*개.*추가", False),
        (r"(.+?)의\s*수량을\s*알려주시겠어요", True),
    )
    text = _latest_bot_text(history)
    for pattern, strip_storage in patterns:
        match = re.search(pattern, text)
        if match:
            name = match.group(1).strip(" \"'.,!?을를")
            return _strip_add_name(name) if strip_storage else name
    return None

def _pending_consume_from_history(history) -> str | None:
    match = re.search(r"(.+?)(?:을|를) 몇 개 (?:먹|소비)", _latest_bot_text(history))
    return match.group(1).strip() if match else None

def _storage_choice_response(name: str, quantity: float, unchecked: bool = False) -> dict:
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

def _extract_expiry_keyword(text: str) -> str:
    match = re.search(r"([가-힣A-Za-z0-9]+)\s*(?:유통기한|소비기한|기한)", text)
    if not match:
        match = re.search(r"^\s*(?:먹다\s*남은|먹다남은|남은)?\s*([가-힣A-Za-z0-9]+?)\s*(?:어디에\s*)?(?:쓸\s*수|쓸수|활용|처리)", text)
    if not match:
        return ""
    keyword = match.group(1).strip()
    if keyword in ("재료", "식재료", "냉장고", "오늘", "소비", "소비기한", "유통기한", "기한", "임박", "임박재료", "소비임박재료"):
        return ""
    return keyword

def _format_d_day(d_day: int) -> str:
    if d_day > 0:
        return f"D-{d_day}"
    if d_day == 0:
        return "D-Day"
    return f"D+{abs(d_day)} 지남"
