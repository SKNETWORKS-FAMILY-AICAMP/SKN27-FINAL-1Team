import json
import re
from typing import Any

# 챗봇 기본 응답 문구
LOGIN_REQUIRED_REPLY = "로그인이 필요한 질문이에요. 비회원 상태에서는 보관법이나 일반 레시피 검색을 이용할 수 있어요."
GENERAL_REPLY = "음식과 관련된 대화만 지원하고 있어요! 요리 레시피, 식재료 보관법, 냉장고 재료 관리 등을 물어봐주세요!"

# 확인/취소 액션 키워드
CONFIRM_PREFIX = "확인:"
CANCEL_WORDS = ("취소", "아니", "아니요", "아니다", "아니야", "취소할게", "안넣어", "넣지마", "추가하지마")

# 규칙 기반 라우터에서 사용하는 문맥 및 대표 표현입니다.
_CONTEXT_INTENTS = {"ingredient.guide", "inventory.list", "inventory.expiring"}
_RECIPE_RECOMMEND_PHRASES = (
    "뭐해먹", "뭐먹", "뭐하지", "만들지", "만들요리", "만들어먹",
    "요리추천", "메뉴추천", "추천메뉴", "만들수", "냉장고파먹",
    "어디에쓸", "활용할",
)
_RECIPE_SEARCH_PHRASES = ("레시피", "요리법", "요리방법")
_GUIDE_PHRASES = (
    "보관법", "보관방법", "보관해", "어떻게보관", "보관어떻게", "손질법", "손질방법",
    "손질해", "어떻게손질", "세척법", "세척방법", "세척해", "씻는법", "어떻게씻", "신선하게", "식재료가이드", "먹다남은",
    "영양", "영양성분", "칼로리", "열량", "단백질", "탄수화물", "지방",
    "당류", "나트륨", "맛있게먹", "먹는법", "섭취", "제철",
)

# LLM fallback이 반환할 수 있는 읽기 전용 intent입니다.
_LLM_ROUTE_INTENTS = (
    "receipt.guide", "recipe.recommend", "recipe.pairing", "recipe.search",
    "ingredient.guide", "inventory.expiring", "inventory.list",
    "shopping.current", "shopping.history", "shopping.compare", "alarm.notification", "alarm.calendar", "general",
)


def _normalize_text(text: str) -> str:
    """사용자 문장을 간단 비교할 수 있도록 정리합니다."""
    return text.replace(" ", "").lower()

def _extract_keyword(text: str) -> str:
    cleaned = re.sub(
        r"(냉장고|냉동고|냉장실|냉동실|실온|냉장|냉동|상온|먹다\s*남은|먹다남은|남은|먹다|어떡하지|어떡해|어떻게하지|보관법|보관방법|보관해|보관|세척법|세척방법|세척|씻|손질법|손질방법|손질|신선도|확인법|확인|어떻게|가이드|레시피|요리|추천|알려줘|찾아줘|해줘|좀|해먹을|만들|영양성분|영양|칼로리|열량|단백질|탄수화물|지방|당류|나트륨|제철)",
        " ",
        text,
    )
    words = [word.strip() for word in cleaned.split() if word.strip() and word.strip() not in ("내", "제", "나", "어떤", "무슨", "이", "그", "저", "이런", "그런", "저런", "수", "있어", "있어?", "있나요", "있나요?")]
    return words[0] if words else ""

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

def _is_relevant_search_result(keyword: str, item: dict[str, Any]) -> bool:
    """검색 결과 제목/본문이 질문 핵심어와 맞는지 확인합니다."""
    tokens = _keyword_tokens(keyword)
    if not tokens:
        return False
    haystack = f"{item.get('title', '')} {item.get('content', '')}".lower()
    words = _keyword_tokens(haystack)
    primary = tokens[0]
    return any(_is_guide_result_match(primary, word) for word in words)


def _latest_bot_intent(history) -> str | None:
    """이전 봇 응답에 저장된 마지막 intent를 반환합니다."""
    for message in reversed(history or []):
        role = message.get("role") if isinstance(message, dict) else getattr(message, "role", "")
        intent = message.get("intent") if isinstance(message, dict) else getattr(message, "intent", None)
        if role == "bot" and intent:
            return intent
    return None


def _latest_bot_slots(history) -> dict:
    """이전 봇 응답에 저장된 마지막 슬롯을 반환합니다."""
    for message in reversed(history or []):
        role = message.get("role") if isinstance(message, dict) else getattr(message, "role", "")
        slots = message.get("slots") if isinstance(message, dict) else getattr(message, "slots", None)
        if role == "bot" and isinstance(slots, dict):
            return slots
    return {}


def _latest_bot_pending_action(history) -> dict | None:
    """이전 봇 응답에 저장된 실행 대기 작업을 반환합니다."""
    for message in reversed(history or []):
        role = message.get("role") if isinstance(message, dict) else getattr(message, "role", "")
        pending = message.get("pending_action") if isinstance(message, dict) else getattr(message, "pending_action", None)
        if role == "bot" and isinstance(pending, dict):
            return pending
    return None


def _rewrite_context_switch(text: str, has_pending: bool = False) -> str:
    """기존 작업을 번복한 문장에서 새로 실행할 명령만 남깁니다."""
    stripped = text.strip()
    if has_pending:
        switch_match = re.search(r"(?:말고|대신)\s*(.+)$", stripped)
        if switch_match:
            return switch_match.group(1).strip()
    replacement = re.sub(r"^(?:아니다|아니야|아니|잠깐|취소하고)(?:\s+|,\s*)", "", stripped).strip()
    return replacement or stripped


def _is_context_follow_up(text: str) -> bool:
    """직전 응답 없이는 의미가 부족한 짧은 후속 질문인지 확인합니다."""
    normalized = _normalize_text(text)
    return (
        bool(re.match(r"^외\d+개", normalized))
        or bool(re.fullmatch(r"(?:냉장|냉동|실온)(?:은|는|으로|에)?", normalized.rstrip("?")))
        or any(word in normalized for word in ("나머지", "그중", "그거", "그걸", "그건", "이거", "이걸", "이건", "첫번째", "두번째", "더알려", "더보여", "전부", "다말해", "다보여"))
    )


def _route_result(intent: str, confidence: float = 1.0, slots: dict | None = None) -> dict:
    """라우터 결과를 공통 dict 형식으로 반환합니다."""
    payload = {"intent": intent, "confidence": confidence, "slots": slots or {}}
    return {"intent": intent, "intent_payload": payload, "slots": payload["slots"]}


def _format_calendar_events(data: dict) -> str | None:
    """캘린더 조회 결과를 챗봇 말풍선에 보여줄 문장으로 바꿉니다."""
    events = data.get("events") if isinstance(data, dict) else None
    if events is None:
        return None
    if not events:
        return "조회한 기간에 등록된 일정이 없어요."
    lines = ["등록된 일정이에요."]
    for event in events[:5]:
        date_key = event.get("dateKey") or "날짜 미정"
        title = event.get("title") or "제목 없는 일정"
        lines.append(f"{date_key} - {title}")
    if len(events) > 5:
        lines.append(f"외 {len(events) - 5}개가 더 있어요.")
    return "\n".join(lines)


def _extract_pending_action(final_state: dict[str, Any], actions: list[dict[str, Any]]) -> dict[str, Any] | None:
    """에이전트 결과나 확인 버튼에서 실행 대기 작업을 추출합니다."""
    pending = final_state.get("pending_action")
    if isinstance(pending, dict):
        return pending
    if pending:
        return {"action": str(pending)}
    for action in actions:
        command = (action.get("data") or {}).get("message")
        if isinstance(command, str) and command.startswith("확인:"):
            return {"command": command}
    return None


def _parse_llm_route_payload(content: str) -> dict[str, Any]:
    """LLM이 반환한 JSON 라우팅 결과를 안전한 dict로 변환합니다."""
    raw = (content or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.IGNORECASE | re.DOTALL).strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    slots = payload.get("slots") if isinstance(payload.get("slots"), dict) else {}
    try:
        confidence = float(payload.get("confidence", 0))
    except (TypeError, ValueError):
        confidence = 0.0
    return {
        "intent": str(payload.get("intent", "")).strip(),
        "confidence": max(0.0, min(confidence, 1.0)),
        "slots": slots,
    }


def _route_payload(intent: str, confidence: float = 1.0, slots: dict[str, Any] | None = None) -> dict[str, Any]:
    """LLM 라우팅 결과를 Supervisor 공통 dict 형식으로 반환합니다."""
    return {"intent": intent, "confidence": confidence, "slots": slots or {}}


def _rewrite_guide_query(text: str) -> str:
    """정정 표현이 포함된 가이드 질문에서 마지막 식재료 질문만 남깁니다."""
    return re.sub(r"^.+?(?:말고|대신)\s+", "", text).strip()


def _strip_shopping_compare_suffix(text: str) -> str:
    """가격 비교 후속 표현을 제거하고 실제 상품명만 반환합니다."""
    return re.sub(
        r"\s*더\s*(?:싼|저렴한)\s*(?:곳|데)(?:은|는)?(?:\s*없어(?:요)?)?\s*\??$",
        "",
        text,
    ).strip()
