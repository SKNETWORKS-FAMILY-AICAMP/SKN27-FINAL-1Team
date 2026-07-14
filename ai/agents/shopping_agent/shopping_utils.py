from __future__ import annotations

import re
from typing import Any

AGENT_NAME = "shopping"

SHOPPING_CONFIRM_ACTIONS = {
    "shopping_create",
    "shopping_purchase",
    "shopping_delete_item",
}

SHOPPING_CONTEXT_WORDS = (
    "장보기",
    "장보",
    "장볼",
    "장봐",
    "쇼핑",
    "구매목록",
    "구매리스트",
    "살것",
    "살거",
    "사야할",
    "사야하는",
    "사야될",
    "구매할",
)

SHOPPING_COMPARE_WORDS = ("가격비교", "비교", "가격", "최저가", "얼마", "상품", "마켓")
SHOPPING_HISTORY_WORDS = ("내역", "히스토리", "지난", "이전", "완료된")
SHOPPING_PURCHASE_WORDS = ("구매완료", "구매 완료", "샀어", "샀어요", "구매했어", "구매했어요")
SHOPPING_CREATE_WORDS = ("만들", "생성", "추가", "담아", "넣어", "등록")
SHOPPING_DELETE_WORDS = ("삭제", "지워", "빼", "제외")
SHOPPING_CHECK_WORDS = ("체크", "선택")
SHOPPING_LIST_WORDS = ("보여", "조회", "확인", "알려", "있어", "목록", "리스트")
SHOPPING_OWNED_WORDS = ("보유", "가지고있는", "가진", "있는재료", "내재료", "내가보유")

_COMMAND_PHRASES = (
    "장보기",
    "쇼핑",
    "구매목록",
    "구매리스트",
    "살것",
    "살거",
    "사야할",
    "사야하는",
    "사야될",
    "구매할",
    "목록",
    "리스트",
    "가격비교",
    "가격",
    "최저가",
    "상품",
    "마켓",
    "만들어줘",
    "만들어",
    "생성해줘",
    "생성",
    "추가해줘",
    "추가",
    "담아줘",
    "담아",
    "넣어줘",
    "넣어",
    "등록해줘",
    "등록",
    "보여줘",
    "보여",
    "조회해줘",
    "조회",
    "확인해줘",
    "확인",
    "알려줘",
    "알려",
    "비교해줘",
    "비교",
    "해줘",
    "해주세요",
    "해",
)

_STOPWORDS = {
    "나",
    "내",
    "좀",
    "그리고",
    "그럼",
    "그러면",
    "오늘",
    "지금",
    "현재",
    "전체",
    "전부",
    "모두",
}


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", text or "").lower()


def contains_shopping_context(text: str) -> bool:
    normalized = normalize_text(text)
    return any(word.replace(" ", "") in normalized for word in SHOPPING_CONTEXT_WORDS)


def analyze_shopping_intent(text: str) -> str | None:
    """장보기 문맥일 때만 shopping.* intent를 반환합니다."""
    normalized = normalize_text(text)
    has_context = contains_shopping_context(text)

    if any(word.replace(" ", "") in normalized for word in SHOPPING_COMPARE_WORDS) and (
        has_context or "비교" in normalized or "최저가" in normalized
    ):
        return "shopping.compare"
    if any(word.replace(" ", "") in normalized for word in SHOPPING_PURCHASE_WORDS) and has_context:
        return "shopping.purchase"
    if not has_context:
        return None
    if any(word.replace(" ", "") in normalized for word in SHOPPING_OWNED_WORDS):
        return "shopping.owned"
    if any(word in normalized for word in SHOPPING_HISTORY_WORDS):
        return "shopping.history"
    if any(word in normalized for word in SHOPPING_DELETE_WORDS):
        return "shopping.delete_item"
    if any(word in normalized for word in SHOPPING_CHECK_WORDS):
        return "shopping.check_item"
    if any(word in normalized for word in SHOPPING_CREATE_WORDS):
        return "shopping.create"
    if any(word in normalized for word in SHOPPING_LIST_WORDS):
        return "shopping.current"
    return "shopping.current"


def build_shopping_response(
    *,
    message: str,
    intent: str = "unknown",
    ok: bool = True,
    actions: list[dict[str, Any]] | None = None,
    sources: list[dict[str, Any]] | None = None,
    error: dict[str, Any] | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "ok": ok and error is None,
        "agent": AGENT_NAME,
        "intent": intent,
        "message": message,
        "error": error,
        "ui": {
            "actions": list(actions or []),
            "sources": list(sources or []),
        },
        "meta": meta or {},
    }


def to_supervisor_state(agent_result: dict[str, Any]) -> dict[str, Any]:
    ui = agent_result.get("ui") or {}
    return {
        "response_text": agent_result.get("message", ""),
        "actions": list(ui.get("actions") or []),
        "sources": list(ui.get("sources") or []),
    }


def confirm_action(label: str, command: str) -> dict[str, Any]:
    return {"label": label, "data": {"message": command}}


def shopping_list_action(shopping_list_id: int | None = None, label: str = "장보기 목록 보기") -> dict[str, Any]:
    url = "/shopping-list"
    data: dict[str, Any] = {}
    if shopping_list_id:
        url = f"/shopping-list?shoppingListId={shopping_list_id}"
        data["shopping_list_id"] = shopping_list_id
    return {"label": label, "url": url, "data": data}


def format_price(price: int | None) -> str:
    return f"{price:,}원" if price else "가격 정보 없음"


def format_amount(item: dict[str, Any]) -> str:
    quantity = item.get("required_quantity")
    unit = item.get("unit")
    if quantity is None:
        return ""
    number = float(quantity)
    quantity_text = str(int(number)) if number.is_integer() else str(number)
    return f" {quantity_text}{unit or ''}"


def extract_ingredient_names(text: str) -> list[str]:
    target = text or ""
    for phrase in sorted(_COMMAND_PHRASES, key=len, reverse=True):
        target = target.replace(phrase, " ")
    target = re.sub(r"\d+(?:\.\d+)?\s*(?:개|g|kg|ml|l|봉|팩|묶음)?", " ", target, flags=re.IGNORECASE)
    target = re.sub(r"[?!.]", " ", target)
    target = re.sub(r"\s*(?:랑|하고|와|과|및)\s*", ",", target)

    names: list[str] = []
    seen: set[str] = set()
    for raw_part in re.split(r"[,/]", target):
        name = raw_part.strip(" \t\n을를은는이가도")
        if not name or name in _STOPWORDS:
            continue
        if len(name) > 20:
            words = [word for word in name.split() if word not in _STOPWORDS]
            name = words[-1] if words else ""
        normalized = normalize_text(name)
        if not name or normalized in seen:
            continue
        seen.add(normalized)
        names.append(name)
    return names


def find_item_by_name(shopping_list: dict[str, Any] | None, text: str) -> dict[str, Any] | None:
    if not shopping_list:
        return None
    items = shopping_list.get("items") or []
    names = extract_ingredient_names(text)
    candidates = [normalize_text(name) for name in names]
    if not candidates:
        return None

    for item in items:
        item_name = normalize_text(item.get("name") or "")
        if any(candidate and (candidate in item_name or item_name in candidate) for candidate in candidates):
            return item
    return None


def summarize_shopping_list(shopping_list: dict[str, Any] | None, *, max_items: int = 5) -> str:
    if not shopping_list:
        return "진행 중인 장보기 목록이 없어요."

    items = [item for item in shopping_list.get("items", []) if not item.get("is_purchased")]
    if not items:
        return "현재 장보기 목록에 구매할 재료가 없어요."

    lines = ["현재 장보기 목록이에요."]
    for index, item in enumerate(items[:max_items], start=1):
        price_text = format_price(item.get("price"))
        lines.append(f"{index}. {item.get('name')}{format_amount(item)} - {price_text}")
    if len(items) > max_items:
        lines.append(f"외 {len(items) - max_items}개가 더 있어요.")
    total_price = shopping_list.get("total_price") or 0
    if total_price:
        lines.append(f"예상 합계는 {format_price(total_price)}이에요.")
    return "\n".join(lines)


def summarize_owned_ingredients(shopping_list: dict[str, Any] | None, *, max_items: int = 8) -> str:
    if not shopping_list:
        return "진행 중인 장보기 목록이 없어요."

    owned_items = shopping_list.get("owned_ingredients") or []
    if not owned_items:
        return "현재 장보기 목록에 연결된 보유 재료 정보가 없어요. 레시피에서 만든 장보기 목록이면 다시 열어 동기화해보세요."

    lines = ["이 장보기 목록에서 이미 보유한 재료예요."]
    for index, item in enumerate(owned_items[:max_items], start=1):
        name = item.get("name") or "이름 없는 재료"
        amount = item.get("amount")
        amount_text = f" {amount}" if amount else ""
        lines.append(f"{index}. {name}{amount_text}")
    if len(owned_items) > max_items:
        lines.append(f"외 {len(owned_items) - max_items}개가 더 있어요.")
    return "\n".join(lines)
