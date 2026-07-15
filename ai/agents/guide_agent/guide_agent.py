import difflib
import re
import unicodedata
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import text

from app.backend.core.config import settings as app_settings
from app.backend.db.session import SessionLocal
from app.backend.services.guide_service.guide_service import guide_service

try:
    from tavily import TavilyClient
except ImportError:
    TavilyClient = None

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


# =========================================================
# 1. Guide Agent 설정값
# =========================================================

GUIDE_INTENT = "ingredient.guide"
NUTRITION_WORDS = ("영양", "영양성분", "칼로리", "열량", "탄수화물", "단백질", "지방", "당류", "나트륨")

# 자연어 전처리 규칙
GUIDE_STOPWORDS = (
    "영양성분", "영양", "칼로리", "열량", "탄수화물", "단백질", "지방", "당류", "나트륨",
    "제철시기", "제철이야", "제철인가요", "제철인가", "맞나요", "맞아",
    "제철", "시기", "보관법", "보관", "손질법", "손질", "세척법", "세척", "신선도", "확인법",
    "설명해줘", "알려줘", "조회해줘", "조회", "식재료", "재료", "가이드", "언제야", "뭐야",
    "에 대해", "대해", "정보",
)

# 구어체 요청 표현 제거 규칙
QUERY_REQUEST_PATTERNS = (
    r"어떻게\s*보관(?:해|하나요|해야\s*해)?",
    r"어떻게\s*손질(?:해|하나요|해야\s*해)?",
    r"어떻게\s*세척(?:해|하나요|해야\s*해)?",
    r"어떻게\s*씻(?:어|나요|어야\s*해)?",
    r"오래\s*두는\s*법",
    r"냉동해도\s*괜찮아",
    r"깨끗하게\s*닦(?:으려면|는\s*법)?",
    r"물러졌는데\s*괜찮아",
    r"씻는\s*법",
    r"먹어도\s*돼",
    r"먹어도\s*되나요",
    r"상했는지\s*확인하는\s*법",
    r"상했는지\s*확인하는\s*방법",
    r"상한\s*것\s*같아",
    r"상한\s*건지\s*확인하는\s*법",
    r"상했는지",
    r"상한\s*건지",
    r"몇\s*칼로리(?:야|예요)?",
    r"칼로리\s*몇(?:이야|인가요)?",
    r"얼마나\s*들어\s*있어",
    r"얼마나\s*들었어",
    r"어떻게\s*해",
    r"어떻게\s*하나요",
    r"어떻게\s*해야\s*해",
)

# 관련 식재료 목록 질문 표현 제거 규칙
RELATED_QUERY_PATTERNS = (
    r"뭐가\s*있(?:어|나요)?",
    r"어떤\s*(?:식재료|재료)",
    r"무슨\s*(?:식재료|재료)",
    r"종류가\s*뭐(?:야|예요)?",
    r"목록\s*보여줘",
    r"리스트\s*보여줘",
)

RELATED_LIST_WORDS = (
    "종류", "목록", "분류", "리스트",
    "어떤재료", "무슨재료", "어떤식재료", "무슨식재료",
)

# 외부 검색 정책
TRUSTED_WEB_DOMAINS = (
    "foodsafetykorea.go.kr",
    "mfds.go.kr",
    "rda.go.kr",
    "nongsaro.go.kr",
    "nics.go.kr",
    "mafra.go.kr",
    "data.go.kr",
)
LOW_PRIORITY_BLOCKED_DOMAINS = (
    "kin.naver.com",
    "shopping.naver.com",
    "coupang.com",
    "youtube.com",
    "instagram.com",
    "facebook.com",
)

SAFETY_SENSITIVE_GUIDE_TYPES = {
    "freshness",
}

GUIDE_TYPE_LABELS = {
    "storage": "보관법",
    "prep": "손질법",
    "washing": "세척법",
    "freshness": "신선도 확인법",
    "seasonality": "제철 정보",
}


# =========================================================
# 2. Guide Agent 임계값 및 조회 설정
# =========================================================

QUERY_MAX_LENGTH = 100

GUIDE_SEARCH_PAGE_SIZE = 10
GUIDE_LIST_PAGE_SIZE = 24
SEASONAL_PAGE_SIZE = 60

GUIDE_MATCH_MIN_SCORE = 0.88
FUZZY_CANDIDATE_MIN_SCORE = 0.72
FUZZY_AUTO_MATCH_SCORE = 0.88
FUZZY_SCORE_GAP = 0.04
FUZZY_CANDIDATE_LIMIT = 5
CONFIRM_CANDIDATE_DISPLAY_LIMIT = 5

NUTRITION_PARTIAL_MATCH_LIMIT = 10
RELATED_INGREDIENT_LIMIT = 30
RELATED_CARD_LIMIT = 8

WEB_SEARCH_MAX_RESULTS = 8
WEB_SOURCE_LIMIT = 3
WEB_CONTENT_LIMIT = 1800
WEB_FALLBACK_CONTENT_LIMIT = 600
WEB_SUMMARY_MAX_SENTENCES = 3
WEB_SUMMARY_TEMPERATURE = 0.2

UNHELPFUL_WEB_PHRASES = (
    "정보는 포함되어 있지 않습니다",
    "정보가 포함되어 있지 않습니다",
    "포함되어 있지 않습니다",
    "제공할 수 없습니다",
    "찾을 수 없습니다",
    "찾지 못했습니다",
    "확인할 수 없습니다",
    "구체적인 지침",
    "다른 신뢰할 수 있는 출처",
    "다른 출처를 참조",
)


# =========================================================
# 3. 응답 생성 함수
# =========================================================

def build_guide_response(
    *,
    message: str,
    action: str = "lookup_ingredient",
    data: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
    status: str = "success",
    requires_confirmation: bool = False,
    actions: list[dict[str, Any]] | None = None,
    cards: list[dict[str, Any]] | None = None,
    sources: list[dict[str, Any]] | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Guide Agent의 기존 처리 결과를 공통 최종 응답으로 감쌉니다."""
    if error is not None and status == "success":
        status = "error"
    return {
        "ok": error is None,
        "status": status,
        "agent": "guide",
        "action": action,
        "intent": GUIDE_INTENT,
        "message": message,
        "data": data or {},
        "error": error,
        "requires_confirmation": requires_confirmation,
        "ui": {
            "actions": actions or [],
            "cards": cards or [],
            "sources": sources or [],
        },
        "meta": meta or {},
    }


def _invalid_query_response(message: str, code: str) -> dict[str, Any]:
    return build_guide_response(
        action="request_ingredient",
        message=message,
        status="needs_input",
        requires_confirmation=True,
        actions=[
            {
                "type": "request_input",
                "label": "식재료명 입력",
                "value": None,
            }
        ],
        meta={
            "result_code": code,
            "required_parameter": "ingredient",
        },
    )


def _request_season_month_response() -> dict[str, Any]:
    return build_guide_response(
        action="request_season_month",
        message="몇 월의 제철 식재료를 조회할까요? 1월부터 12월 사이로 입력해주세요.",
        status="needs_input",
        requires_confirmation=True,
        actions=[
            {
                "type": "request_input",
                "label": "제철 월 입력",
                "value": None,
            }
        ],
        meta={
            "result_code": "SEASON_MONTH_REQUIRED",
            "required_parameter": "month",
        },
    )


def _source(name: str | None, url: str | None) -> dict[str, str | None] | None:
    return {"title": name, "url": url} if name else None


# =========================================================
# 4. 데이터 변환 및 전처리 함수
# =========================================================

def _detail_data(detail: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, str | None]]]:
    sources = [
        _source(detail.get("seasonal_source_name"), detail.get("seasonal_source_url")),
        _source(detail.get("storage_source_name"), detail.get("storage_source_url")),
        _source(detail.get("prep_source_name"), detail.get("prep_source_url")),
        _source(detail.get("washing_source_name"), detail.get("washing_source_url")),
        _source(detail.get("freshness_source_name"), detail.get("freshness_source_url")),
        _source(detail.get("nutrition_source_name"), None),
    ]
    unique_sources = list({(source["title"], source["url"]): source for source in sources if source}.values())

    def guide(content_key: str, source_prefix: str | None = None) -> dict[str, Any]:
        content = detail.get(content_key)
        source = _source(
            detail.get(f"{source_prefix}_source_name"),
            detail.get(f"{source_prefix}_source_url"),
        ) if source_prefix else None
        return {"status": "available" if content else "missing", "content": content, "source": source}

    nutrition_keys = (
        "nutrition_base_amount", "energy_kcal", "protein_g", "fat_g", "carbohydrate_g",
        "sugar_g", "saturated_fat_g", "trans_fat_g", "fiber_g", "water_g",
        "calcium_mg", "potassium_mg", "sodium_mg",
    )
    nutrition = {key: detail.get(key) for key in nutrition_keys}
    nutrition["status"] = "available" if any(value is not None for value in nutrition.values()) else "missing"
    nutrition["source"] = _source(detail.get("nutrition_source_name"), None)

    return {
        "ingredient": {
            "code": detail.get("code"),
            "name": detail.get("name"),
            "representative_name": detail.get("representative_name"),
            "raw_name": detail.get("raw_name"),
            "display_name": detail.get("existing_display_name"),
            "aliases": detail.get("aliases") or [],
            "category": {
                "major": detail.get("major_category"),
                "middle": detail.get("middle_category"),
                "minor": detail.get("minor_category"),
            },
        },
        "seasonality": {
            "status": "available" if detail.get("seasonal_months") else "missing",
            "months": detail.get("seasonal_months") or [],
            "source": _source(detail.get("seasonal_source_name"), detail.get("seasonal_source_url")),
        },
        "guides": {
            "storage": guide("storage_tips", "storage"),
            "horticultural_storage": guide("horticultural_storage_tips"),
            "prep": guide("prep_tips", "prep"),
            "washing": guide("washing_tips", "washing"),
            "freshness": guide("freshness_tips", "freshness"),
            "intake": guide("intake_tips"),
        },
        "nutrition": nutrition,
    }, unique_sources


def _clean_query_keyword(text_value: str) -> str:
    keyword = re.sub(r"\d{1,2}\s*월", " ", text_value)
    keyword = re.sub(r"(에\s*대해|에\s*대한)", " ", keyword)
    for pattern in QUERY_REQUEST_PATTERNS:
        keyword = re.sub(pattern, " ", keyword)
    for word in GUIDE_STOPWORDS:
        keyword = keyword.replace(word, " ")
    keyword = re.sub(r"[?!.,~]", " ", keyword)
    keyword = re.sub(r"\b[은는이가을를에의]\b", " ", keyword)
    keyword = re.sub(r"\s+", " ", keyword).strip()
    return re.sub(r"[은는이가을를에의]$", "", keyword).strip()


def _is_related_list_query(query: str) -> bool:
    normalized = query.replace(" ", "").lower()
    explicit_words = ("종류", "목록", "리스트", "분류")
    patterns = (
        "어떤재료",
        "무슨재료",
        "어떤식재료",
        "무슨식재료",
        "뭐가있",
    )
    return (
        any(word in normalized for word in explicit_words)
        or any(pattern in normalized for pattern in patterns)
    )


def _clean_related_keyword(query: str) -> str:
    keyword = _clean_query_keyword(query)
    for pattern in RELATED_QUERY_PATTERNS:
        keyword = re.sub(pattern, " ", keyword)
    for word in RELATED_LIST_WORDS:
        keyword = keyword.replace(word, " ")
    for word in ("어떤", "무슨", "있어", "있나요"):
        keyword = keyword.replace(word, " ")
    keyword = re.sub(r"[?!.,~]", " ", keyword)
    keyword = re.sub(r"\s+", " ", keyword).strip()
    return re.sub(r"[은는이가을를에의]$", "", keyword).strip()


def _normalize_match_text(value: str | None) -> str:
    value = unicodedata.normalize("NFKC", value or "").lower()
    return re.sub(r"[^0-9a-z가-힣]", "", value)


def _hangul_initial(value: str) -> int | None:
    code = ord(value)
    if not 0xAC00 <= code <= 0xD7A3:
        return None
    return (code - 0xAC00) // 588


def _host_matches_domain(host: str, domain: str) -> bool:
    host = (host or "").split(":")[0].lower().strip(".")
    domain = domain.lower().strip(".")
    return host == domain or host.endswith(f".{domain}")


def _match_score(query: str, candidate: str) -> float:
    query_norm = _normalize_match_text(query)
    candidate_norm = _normalize_match_text(candidate)
    if not query_norm or not candidate_norm:
        return 0.0
    if query_norm == candidate_norm:
        return 1.0
    if query_norm in candidate_norm or candidate_norm in query_norm:
        return 0.94
    query_second_initial = _hangul_initial(query_norm[1]) if len(query_norm) == 2 else None
    candidate_second_initial = _hangul_initial(candidate_norm[1]) if len(candidate_norm) == 2 else None
    if (
        len(query_norm) == len(candidate_norm) == 2
        and query_norm[0] == candidate_norm[0]
        and query_second_initial is not None
        and query_second_initial == candidate_second_initial
    ):
        return 0.9
    return difflib.SequenceMatcher(None, query_norm, candidate_norm).ratio()


def _select_guide_item(
    ingredient: str,
    items: list[dict[str, Any]],
    *,
    minimum_score: float = GUIDE_MATCH_MIN_SCORE,
) -> dict[str, Any] | None:
    if not items:
        return None

    query_norm = _normalize_match_text(ingredient)
    for item in items:
        names = [
            item.get("name"),
            item.get("representative_name"),
            item.get("raw_name"),
            *(item.get("aliases") or []),
        ]
        if any(_normalize_match_text(name) == query_norm for name in names if name):
            return item

    scored_items = []
    for item in items:
        names = [
            item.get("name"),
            item.get("representative_name"),
            item.get("raw_name"),
            *(item.get("aliases") or []),
        ]
        score = max(
            (
                _match_score(ingredient, name)
                for name in names
                if name
            ),
            default=0.0,
        )
        scored_items.append((score, item))

    best_score, best_item = max(
        scored_items,
        key=lambda value: value[0],
    )
    if best_score < minimum_score:
        return None

    return best_item


def _guide_fuzzy_candidates(ingredient: str, *, limit: int = FUZZY_CANDIDATE_LIMIT) -> list[dict[str, Any]]:
    query = """
    MATCH (g)
    WHERE (g:FoodGuide OR g:Ingredient)
      AND coalesce(g.name, g.rawName, g.representativeName) IS NOT NULL
      AND NOT coalesce(g.name, g.rawName, g.representativeName) STARTS WITH "food-guide-"
    OPTIONAL MATCH (g)-[:HAS_ALIAS]->(alias:Alias)
    WITH g, [name IN collect(DISTINCT alias.name) WHERE name IS NOT NULL] AS relation_aliases
    RETURN g.key AS code,
           coalesce(g.name, g.rawName, g.representativeName) AS name,
           g.representativeName AS representative_name,
           g.rawName AS raw_name,
           coalesce(g.aliases, []) + relation_aliases AS aliases
    """
    scored: list[dict[str, Any]] = []
    with guide_service.session() as session:
        for record in session.run(query):
            row = dict(record)
            names = [
                row.get("name"),
                row.get("representative_name"),
                row.get("raw_name"),
                *(row.get("aliases") or []),
            ]
            score = max(_match_score(ingredient, name) for name in names if name)
            if score >= FUZZY_CANDIDATE_MIN_SCORE:
                scored.append(
                    {
                        "code": row.get("code"),
                        "name": row.get("name"),
                        "representative_name": row.get("representative_name"),
                        "raw_name": row.get("raw_name"),
                        "aliases": row.get("aliases") or [],
                        "score": round(score, 3),
                    }
                )
    return sorted(scored, key=lambda item: item["score"], reverse=True)[:limit]


def _safe_guide_fuzzy_candidates(
    ingredient: str,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    try:
        return _guide_fuzzy_candidates(ingredient), None
    except Exception:
        return [], build_guide_response(
            message=f"{ingredient} 유사 식재료를 조회하지 못했어요.",
            error={"code": "GUIDE_FUZZY_ERROR"},
            meta={"data_source": "neo4j"},
        )


def _needs_confirmation(candidates: list[dict[str, Any]]) -> bool:
    if not candidates:
        return False
    if candidates[0]["score"] < FUZZY_AUTO_MATCH_SCORE:
        return True
    return len(candidates) > 1 and candidates[0]["score"] - candidates[1]["score"] < FUZZY_SCORE_GAP


def _candidate_query_value(candidate_name: str, guide_type: str) -> str:
    if guide_type == "nutrition":
        return f"{candidate_name} 영양성분 알려줘"
    if guide_type == "all":
        return f"{candidate_name} 알려줘"
    label = GUIDE_TYPE_LABELS.get(guide_type, "가이드")
    return f"{candidate_name} {label} 알려줘"


def _candidate_display_label(candidate_name: str, guide_type: str) -> str:
    if guide_type == "nutrition":
        return f"{candidate_name} 영양성분"
    if guide_type == "all":
        return candidate_name
    label = GUIDE_TYPE_LABELS.get(guide_type, "가이드")
    return f"{candidate_name} {label}"


def _confirm_ingredient_response(
    ingredient: str,
    candidates: list[dict[str, Any]],
    *,
    guide_type: str = "all",
    original_query: str | None = None,
) -> dict[str, Any]:
    candidate_names = [
        _candidate_display_label(candidate["name"], guide_type)
        for candidate in candidates[:CONFIRM_CANDIDATE_DISPLAY_LIMIT]
    ]
    return build_guide_response(
        action="confirm_ingredient",
        message=(
            f"'{ingredient}'와 비슷한 식재료를 찾았어요. "
            f"후보: {', '.join(candidate_names)}. 어떤 재료를 조회할까요?"
        ),
        status="needs_input",
        data={"input": ingredient, "candidates": candidates},
        requires_confirmation=True,
        actions=[
            {
                "type": "select_guide_candidate",
                "label": _candidate_display_label(candidate["name"], guide_type),
                "value": _candidate_query_value(candidate["name"], guide_type),
                "data": {
                    "message": _candidate_query_value(candidate["name"], guide_type),
                },
                "intent": GUIDE_INTENT,
                "guide_type": guide_type,
                "original_query": original_query or ingredient,
            }
            for candidate in candidates
        ],
        cards=[
            {
                "title": _candidate_display_label(candidate["name"], guide_type),
                "subtitle": f"유사도 {candidate.get('score', 0):.2f}",
                "value": _candidate_query_value(candidate["name"], guide_type),
            }
            for candidate in candidates[:CONFIRM_CANDIDATE_DISPLAY_LIMIT]
        ],
        meta={
            "result_code": "INGREDIENT_CONFIRMATION_REQUIRED",
            "match_type": "fuzzy",
            "candidate_count": len(candidates),
        },
    )


# =========================================================
# 5. 내부 DB 및 외부 검색 조회 함수
# =========================================================

def _lookup_guide_detail(ingredient: str) -> tuple[dict[str, Any] | None, list[dict[str, str | None]]]:
    search = guide_service.search_guides(keyword=ingredient, page=1, page_size=GUIDE_SEARCH_PAGE_SIZE)
    selected = _select_guide_item(ingredient, search.get("items") or [])
    if not selected:
        return None, []
    detail = guide_service.get_guide_detail(selected["code"])
    return _detail_data(detail) if detail else (None, [])


def _normalize_nutrition_match_text(value: Any) -> str:
    return re.sub(r"[^0-9a-zA-Z가-힣]+", "", str(value or "")).lower()


def _is_safe_nutrition_partial_match(keyword: str, row: dict[str, Any]) -> bool:
    normalized_keyword = _normalize_nutrition_match_text(keyword)
    normalized_representative = _normalize_nutrition_match_text(row.get("representative_name"))
    normalized_food_name = _normalize_nutrition_match_text(row.get("food_name"))
    if len(normalized_keyword) < 2:
        return False
    return (
        normalized_representative.startswith(normalized_keyword)
        or normalized_food_name.startswith(normalized_keyword)
    )


def _wants_representative_nutrition(value: str) -> bool:
    return any(word in value for word in ("대표", "기본", "일반", "아무거나"))


def _nutrition_lookup_name(value: str) -> str:
    return re.sub(r"(대표|기본|일반|아무거나)", " ", value or "").strip()


def _nutrition_display_name(food_name: str) -> str:
    return " · ".join(part.strip() for part in str(food_name or "").split("_") if part.strip())


def _nutrition_candidate_response(ingredient: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = [
        {
            "name": row["food_name"],
            "label": _nutrition_display_name(row["food_name"]),
            "food_code": row.get("food_code"),
            "representative_name": row.get("representative_name"),
            "base_amount": row.get("base_amount"),
            "energy_kcal": row.get("energy_kcal"),
            "score": row.get("representative_nutrition_score"),
        }
        for row in rows[:CONFIRM_CANDIDATE_DISPLAY_LIMIT]
    ]
    return build_guide_response(
        action="confirm_nutrition",
        message=f"{ingredient} 영양정보는 여러 기준이 있어요. 어떤 기준으로 볼까요?",
        status="needs_input",
        data={"input": ingredient, "candidates": candidates},
        requires_confirmation=True,
        actions=[
            {
                "type": "select_nutrition_candidate",
                "label": candidate["label"],
                "value": f"{candidate['food_code']} 영양성분 알려줘",
                "data": {"message": f"{candidate['food_code']} 영양성분 알려줘"},
                "intent": GUIDE_INTENT,
                "guide_type": "nutrition",
                "food_code": candidate["food_code"],
                "food_name": candidate["name"],
            }
            for candidate in candidates
        ],
        cards=[
            {
                "title": candidate["label"],
                "subtitle": f"{candidate.get('base_amount') or ''} {candidate.get('energy_kcal') or '-'}kcal".strip(),
                "value": f"{candidate['food_code']} 영양성분 알려줘",
            }
            for candidate in candidates
        ],
        meta={"result_code": "NUTRITION_CONFIRMATION_REQUIRED", "candidate_count": len(rows)},
    )


def _query_nutrition(names: list[str]) -> dict[str, Any] | None:
    candidates = [name for name in dict.fromkeys(names) if name]
    if not candidates:
        return None

    db = SessionLocal()
    try:
        for name in candidates:
            row = db.execute(
                text(
                    """
                    SELECT food_code, food_name, representative_name,
                           major_category, middle_category, minor_category,
                           base_amount, energy_kcal, carbohydrate_g, protein_g,
                           fat_g, sugar_g, sodium_mg,
                           source_name, source_ref, reference_year, source_priority,
                           is_representative_nutrition, representative_nutrition_score
                    FROM food_nutrition_facts
                    WHERE food_code = :name OR food_name = :name OR representative_name = :name
                    ORDER BY is_representative_nutrition DESC,
                             representative_nutrition_score DESC,
                             source_priority,
                             CASE WHEN food_code = :name THEN 0 ELSE 1 END,
                             CASE WHEN representative_name = :name THEN 0 ELSE 1 END,
                             food_name
                    LIMIT 1
                    """
                ),
                {"name": name},
            ).mappings().first()
            if row:
                return dict(row)

        keyword = candidates[0]
        like_name = f"%{keyword}%"
        rows = db.execute(
            text(
                """
                SELECT food_code, food_name, representative_name,
                       major_category, middle_category, minor_category,
                       base_amount, energy_kcal, carbohydrate_g, protein_g,
                       fat_g, sugar_g, sodium_mg,
                       source_name, source_ref, reference_year, source_priority,
                       is_representative_nutrition, representative_nutrition_score
                FROM food_nutrition_facts
                WHERE food_name ILIKE :name OR representative_name ILIKE :name
                ORDER BY
                    is_representative_nutrition DESC,
                    representative_nutrition_score DESC,
                    CASE
                        WHEN representative_name = :exact_name THEN 0
                        WHEN food_name = :exact_name THEN 1
                        WHEN representative_name ILIKE :prefix_name THEN 2
                        WHEN food_name ILIKE :prefix_name THEN 3
                        ELSE 4
                    END,
                    source_priority,
                    food_name
                LIMIT :limit
                """
            ),
            {
                "name": like_name,
                "exact_name": keyword,
                "prefix_name": f"{keyword}%",
                "limit": NUTRITION_PARTIAL_MATCH_LIMIT,
            },
        ).mappings().all()
        if not rows:
            return None
        safe_rows = [
            dict(row)
            for row in rows
            if _is_safe_nutrition_partial_match(keyword, dict(row))
        ]
        return safe_rows[0] if len(safe_rows) == 1 else None
    finally:
        db.close()


def _nutrition_options(name: str) -> list[dict[str, Any]]:
    tokens = [token for token in re.split(r"[\s_]+", name.strip()) if token]
    db = SessionLocal()
    try:
        rows = [
            dict(row)
            for row in db.execute(
                text(
                    """
                    SELECT food_code, food_name, representative_name, base_amount, energy_kcal,
                           is_representative_nutrition, representative_nutrition_score
                    FROM food_nutrition_facts
                    WHERE food_code = :name OR representative_name = :name OR food_name = :name
                    ORDER BY is_representative_nutrition DESC,
                             representative_nutrition_score DESC,
                             source_priority,
                             food_name
                    LIMIT :limit
                    """
                ),
                {"name": name, "limit": CONFIRM_CANDIDATE_DISPLAY_LIMIT},
            ).mappings().all()
        ]
        if rows:
            return rows
        if not tokens:
            return []
        conditions = " AND ".join(f"food_name ILIKE :token_{index}" for index, _ in enumerate(tokens[:4]))
        params = {f"token_{index}": f"%{token}%" for index, token in enumerate(tokens[:4])}
        params["limit"] = CONFIRM_CANDIDATE_DISPLAY_LIMIT
        return [
            dict(row)
            for row in db.execute(
                text(
                    f"""
                    SELECT food_code, food_name, representative_name, base_amount, energy_kcal,
                           is_representative_nutrition, representative_nutrition_score
                    FROM food_nutrition_facts
                    WHERE {conditions}
                    ORDER BY is_representative_nutrition DESC,
                             representative_nutrition_score DESC,
                             source_priority,
                             food_name
                    LIMIT :limit
                    """
                ),
                params,
            ).mappings().all()
        ]
    finally:
        db.close()


def _ingredient_from_nutrition(nutrition: dict[str, Any] | None, fallback_name: str) -> dict[str, Any]:
    if not nutrition:
        return {"name": fallback_name}
    return {
        "code": nutrition.get("food_code"),
        "name": nutrition.get("representative_name") or nutrition.get("food_name") or fallback_name,
        "representative_name": nutrition.get("representative_name"),
        "raw_name": nutrition.get("food_name"),
        "display_name": None,
        "aliases": [],
        "category": {
            "major": nutrition.get("major_category"),
            "middle": nutrition.get("middle_category"),
            "minor": nutrition.get("minor_category"),
        },
    }


def _summarize_web_content(ingredient: str, guide_type: str, content: str) -> str:
    fallback_content = content[:WEB_FALLBACK_CONTENT_LIMIT]
    if OpenAI is None or not app_settings.OPENAI_API_KEY:
        return fallback_content

    try:
        label = GUIDE_TYPE_LABELS.get(guide_type, "식재료 가이드")
        client_ai = OpenAI(api_key=app_settings.OPENAI_API_KEY)
        response = client_ai.chat.completions.create(
            model=app_settings.OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"검색 결과 안에서만 한국어로 {WEB_SUMMARY_MAX_SENTENCES}문장 이내 요약해. "
                        "추측하지 말고, 식품 안전상 단정이 어려우면 보수적으로 말해."
                    ),
                },
                {
                    "role": "user",
                    "content": f"식재료: {ingredient}\n요청: {label}\n검색 결과:\n{content}",
                },
            ],
            temperature=WEB_SUMMARY_TEMPERATURE,
        )
        summarized = response.choices[0].message.content
        return summarized.strip() if summarized else fallback_content
    except Exception:
        return fallback_content


def _is_unhelpful_web_content(content: str | None) -> bool:
    normalized = (content or "").replace(" ", "")
    return any(phrase.replace(" ", "") in normalized for phrase in UNHELPFUL_WEB_PHRASES)


def _web_results(ingredient: str, guide_type: str, *, trusted_only: bool) -> tuple[str | None, list[dict[str, str]]]:
    if TavilyClient is None or not app_settings.TAVILY_API_KEY:
        return None, []

    label = GUIDE_TYPE_LABELS.get(guide_type, "식재료 가이드")
    query = f"{ingredient} {label} 식품안전 농촌진흥청 식약처"
    client = TavilyClient(api_key=app_settings.TAVILY_API_KEY)
    result = client.search(query=query, search_depth="basic", max_results=WEB_SEARCH_MAX_RESULTS)
    picked = []
    for item in result.get("results", []):
        url = item.get("url") or ""
        host = urlparse(url).netloc.lower()
        if any(_host_matches_domain(host, domain) for domain in LOW_PRIORITY_BLOCKED_DOMAINS):
            continue
        is_trusted = any(_host_matches_domain(host, domain) for domain in TRUSTED_WEB_DOMAINS)
        if trusted_only and not is_trusted:
            continue
        picked.append(item)
    if not picked:
        return None, []

    sources = [
        {"title": item.get("title") or item.get("url") or "공신력 외부 자료", "url": item.get("url") or ""}
        for item in picked[:WEB_SOURCE_LIMIT]
    ]
    content = "\n".join(item.get("content", "") for item in picked[:WEB_SOURCE_LIMIT] if item.get("content"))[:WEB_CONTENT_LIMIT]
    if not content:
        return None, sources

    return _summarize_web_content(ingredient, guide_type, content), sources


def _fallback_guide_response(
    ingredient: str,
    guide_type: str,
    ingredient_info: dict[str, Any] | None = None,
    nutrition: dict[str, Any] | None = None,
) -> dict[str, Any]:
    label = GUIDE_TYPE_LABELS.get(guide_type, "가이드")
    label_josa = "가" if label.endswith("정보") else "이"
    try:
        content, sources = _web_results(ingredient, guide_type, trusted_only=True)
        data_source = "trusted_external"
        source_type = "trusted_external"
        source_label = "외부 공신력 자료"
        if _is_unhelpful_web_content(content):
            content = None
        if not content and guide_type not in SAFETY_SENSITIVE_GUIDE_TYPES:
            content, sources = _web_results(ingredient, guide_type, trusted_only=False)
            data_source = "general_web"
            source_type = "general_web"
            source_label = "후순위 웹 자료"
            if _is_unhelpful_web_content(content):
                content = None
    except Exception as exc:
        print("[Guide Web Fallback 오류]", exc)
        content, sources = None, []

    if not content:
        if guide_type in SAFETY_SENSITIVE_GUIDE_TYPES:
            message = (
                f"{ingredient} {label}{label_josa} 공식 자료에서 찾지 못했어요. "
                "상했는지 판단하기 어렵거나 상태가 의심되면 섭취하지 않는 것이 안전해요."
            )
        else:
            message = f"{ingredient} {label}{label_josa} 내부 공공데이터와 외부 자료에서 찾지 못했어요."

        return build_guide_response(
            message=message,
            status="not_found",
            data={
                "ingredient": ingredient_info or _ingredient_from_nutrition(nutrition, ingredient),
                "nutrition": nutrition,
                "guide_type": guide_type,
            },
            meta={
                "result_code": "WEB_GUIDE_NOT_FOUND",
                "data_source": "web",
                "fallback_used": True,
                "internal_data_available": False,
                "general_web_allowed": guide_type not in SAFETY_SENSITIVE_GUIDE_TYPES,
            },
        )

    source = sources[0] if sources else None
    fallback_data = {
        "ingredient": ingredient_info or _ingredient_from_nutrition(nutrition, ingredient),
        "nutrition": nutrition,
    }
    if guide_type == "seasonality":
        fallback_data["seasonality"] = {
            "status": "available",
            "content": content,
            "source": source,
            "source_type": source_type,
        }
    else:
        fallback_data["guides"] = {
            guide_type: {
                "status": "available",
                "content": content,
                "source": source,
                "source_type": source_type,
            }
        }

    return build_guide_response(
        message=f"내부 공공데이터에는 {ingredient} {label}{label_josa} 없어, {source_label}를 기준으로 안내드릴게요.",
        data=fallback_data,
        sources=sources,
        meta={
            "data_source": data_source,
            "fallback_used": True,
            "internal_data_available": False,
        },
    )


# =========================================================
# 6. 의도 분류 및 응답 필터링 함수
# =========================================================

def _guide_type_from_query(query: str) -> str:
    normalized = query.replace(" ", "").lower()
    if "제철" in normalized:
        return "seasonality"
    if any(word in normalized for word in ("신선", "상한", "상했", "먹어도", "물러졌")):
        return "freshness"
    if "손질" in normalized:
        return "prep"
    if "세척" in normalized or "씻" in normalized or "닦" in normalized:
        return "washing"
    if any(word in normalized for word in ("보관", "오래두", "냉동")):
        return "storage"
    return "all"


def _get_requested_guide(data: dict[str, Any], guide_type: str) -> dict[str, Any]:
    if guide_type == "seasonality":
        return data.get("seasonality") or {}
    if guide_type == "all":
        return {"status": "available"} if data else {}
    return (data.get("guides") or {}).get(guide_type) or {}


def _label_object_josa(label: str) -> str:
    return "를" if label.endswith("정보") else "을"


def _filter_guide_response(result: dict[str, Any], guide_type: str) -> dict[str, Any]:
    if guide_type == "all":
        return result

    data = result.get("data") or {}
    ingredient = data.get("ingredient") or {}
    ingredient_name = ingredient.get("name") or "식재료"
    label = GUIDE_TYPE_LABELS.get(guide_type, "가이드")

    if guide_type == "seasonality":
        seasonality = data.get("seasonality") or {}
        months = seasonality.get("months") or []
        result["action"] = "lookup_seasonality"
        result["data"] = {
            "ingredient": ingredient,
            "seasonality": seasonality,
        }
        if months:
            month_text = ", ".join(f"{month}월" for month in months)
            result["message"] = f"{ingredient_name} 제철은 {month_text}이에요."
            return result
    else:
        result["action"] = f"lookup_{guide_type}"
        result["data"] = {
            "ingredient": ingredient,
            "guides": {
                guide_type: (data.get("guides") or {}).get(guide_type),
            },
        }

    result["message"] = f"{ingredient_name} {label}{_label_object_josa(label)} 조회했어요."
    return result


# =========================================================
# 7. 공개 조회 함수
# =========================================================

def list_guide_ingredients(
    *,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = GUIDE_LIST_PAGE_SIZE,
    major_category: str | None = None,
    middle_category: str | None = None,
    minor_category: str | None = None,
    ) -> dict[str, Any]:
    """기존 목록 조회를 공통 Guide Agent 응답으로 반환합니다."""
    try:
        data = guide_service.search_guides(
            keyword=keyword,
            page=page,
            page_size=page_size,
            major_category=major_category,
            middle_category=middle_category,
            minor_category=minor_category,
        )
        return build_guide_response(action="list_ingredients", message="식재료 가이드 목록을 조회했어요.", data=data)
    except Exception:
        return build_guide_response(
            action="list_ingredients",
            message="식재료 가이드 목록을 조회하지 못했어요.",
            error={"code": "GUIDE_LIST_ERROR"},
        )


def list_guide_categories(
    *,
    keyword: str | None = None,
    major_category: str | None = None,
    middle_category: str | None = None,
) -> dict[str, Any]:
    """기존 분류 조회를 공통 Guide Agent 응답으로 반환합니다."""
    try:
        data = guide_service.get_category_options(keyword, major_category, middle_category)
        return build_guide_response(action="list_categories", message="식재료 분류를 조회했어요.", data=data)
    except Exception:
        return build_guide_response(
            action="list_categories",
            message="식재료 분류를 조회하지 못했어요.",
            error={"code": "GUIDE_CATEGORY_ERROR"},
        )


def list_related_ingredients(keyword: str, *, limit: int = RELATED_INGREDIENT_LIMIT) -> dict[str, Any]:
    """원재료명/별칭/분류명으로 관련 식재료 목록을 조회합니다."""
    keyword = (keyword or "").strip()
    if not keyword:
        return build_guide_response(
            action="list_related_ingredients",
            message="조회할 식재료명이나 분류명을 입력해주세요.",
            status="needs_input",
            requires_confirmation=True,
            actions=[
                {
                    "type": "request_input",
                    "label": "식재료명 또는 분류명 입력",
                    "value": None,
                }
            ],
            meta={
                "result_code": "INVALID_RELATED_KEYWORD",
                "required_parameter": "keyword",
            },
        )

    query = """
    MATCH (g)
    WHERE (g:FoodGuide OR g:Ingredient)
      AND coalesce(g.name, g.rawName, g.representativeName) IS NOT NULL
      AND NOT coalesce(g.name, g.rawName, g.representativeName) STARTS WITH "food-guide-"
    OPTIONAL MATCH (g)-[:HAS_ALIAS]->(alias:Alias)
    WITH g, [name IN collect(DISTINCT alias.name) WHERE name IS NOT NULL] AS relation_aliases
    WITH g, coalesce(g.aliases, []) + relation_aliases AS aliases
    WHERE toLower(coalesce(g.name, "")) CONTAINS $keyword
       OR toLower(coalesce(g.rawName, "")) CONTAINS $keyword
       OR toLower(coalesce(g.representativeName, "")) CONTAINS $keyword
       OR toLower(coalesce(g.majorCategory, "")) CONTAINS $keyword
       OR toLower(coalesce(g.middleCategory, "")) CONTAINS $keyword
       OR toLower(coalesce(g.minorCategory, "")) CONTAINS $keyword
       OR any(alias IN aliases WHERE toLower(alias) CONTAINS $keyword)
    RETURN g.key AS code,
           coalesce(g.name, g.rawName, g.representativeName) AS name,
           g.representativeName AS representative_name,
           g.rawName AS raw_name,
           g.majorCategory AS major_category,
           g.middleCategory AS middle_category,
           g.minorCategory AS minor_category,
           aliases AS aliases
    ORDER BY
      CASE
        WHEN toLower(coalesce(g.middleCategory, "")) = $keyword THEN 0
        WHEN toLower(coalesce(g.name, "")) CONTAINS $keyword THEN 1
        WHEN any(alias IN aliases WHERE toLower(alias) CONTAINS $keyword) THEN 2
        ELSE 3
      END,
      name
    LIMIT $limit
    """
    try:
        with guide_service.session() as session:
            rows = [
                {
                    "code": record["code"],
                    "name": record["name"],
                    "representative_name": record["representative_name"],
                    "raw_name": record["raw_name"],
                    "aliases": record["aliases"] or [],
                    "category": {
                        "major": record["major_category"],
                        "middle": record["middle_category"],
                        "minor": record["minor_category"],
                    },
                }
                for record in session.run(query, {"keyword": keyword.lower(), "limit": limit})
            ]
    except Exception:
        return build_guide_response(
            action="list_related_ingredients",
            message=f"{keyword} 관련 식재료 목록을 조회하지 못했어요.",
            error={"code": "GUIDE_RELATED_LIST_ERROR"},
        )

    if not rows:
        return build_guide_response(
            action="list_related_ingredients",
            message=f"{keyword} 관련 식재료를 찾지 못했어요.",
            status="not_found",
            data={"keyword": keyword, "items": [], "total": 0},
            meta={
                "result_code": "RELATED_INGREDIENT_NOT_FOUND",
                "data_source": "neo4j",
            },
        )

    names = [row["name"] for row in rows[:RELATED_CARD_LIMIT]]
    suffix = " 등이 있어요." if len(rows) > RELATED_CARD_LIMIT else "가 있어요."
    return build_guide_response(
        action="list_related_ingredients",
        message=f"{keyword} 관련 식재료로는 {', '.join(names)}{suffix}",
        data={"keyword": keyword, "items": rows, "total": len(rows)},
        cards=[
            {
                "title": row["name"],
                "subtitle": " > ".join(
                    value for value in row["category"].values() if value
                ),
            }
            for row in rows[:RELATED_CARD_LIMIT]
        ],
        meta={"data_source": "neo4j", "matched_fields": ["name", "alias", "category"]},
    )


def lookup_ingredient_guide(ingredient: str) -> dict[str, Any]:
    """기존 검색과 상세 조회를 이어 전체 식재료 가이드를 반환합니다."""
    try:
        search = guide_service.search_guides(keyword=ingredient, page=1, page_size=GUIDE_SEARCH_PAGE_SIZE)
        selected = _select_guide_item(ingredient, search.get("items") or [])
        if not selected:
            return build_guide_response(
                message=f"{ingredient} 식재료 가이드를 찾지 못했어요.",
                status="not_found",
                data={"ingredient": {"name": ingredient}},
                meta={"result_code": "GUIDE_NOT_FOUND"},
            )
        detail = guide_service.get_guide_detail(selected["code"])
        if not detail:
            return build_guide_response(
                message=f"{ingredient} 식재료 가이드를 찾지 못했어요.",
                status="not_found",
                data={"ingredient": {"name": ingredient}},
                meta={"result_code": "GUIDE_NOT_FOUND"},
            )
        data, sources = _detail_data(detail)
        return build_guide_response(
            message=f"{detail['name']} 식재료 가이드를 조회했어요.",
            data=data,
            sources=sources,
        )
    except Exception:
        return build_guide_response(
            message=f"{ingredient} 식재료 가이드를 조회하지 못했어요.",
            error={"code": "GUIDE_LOOKUP_ERROR"},
        )


def list_seasonal_ingredients(month: int) -> dict[str, Any]:
    """기존 목록 조회 결과에서 지정한 월의 제철 식재료를 반환합니다."""
    if not 1 <= month <= 12:
        return build_guide_response(
            action="request_season_month",
            message="제철 월은 1월부터 12월 사이여야 해요.",
            status="needs_input",
            requires_confirmation=True,
            actions=[
                {
                    "type": "request_input",
                    "label": "제철 월 입력",
                    "value": None,
                }
            ],
            meta={
                "result_code": "INVALID_SEASON_MONTH",
                "required_parameter": "month",
            },
        )
    try:
        items, page = [], 1
        while True:
            result = guide_service.search_guides(page=page, page_size=SEASONAL_PAGE_SIZE)
            items.extend(item for item in result["items"] if month in (item.get("seasonal_months") or []))
            if not result["has_next"]:
                break
            page += 1
        return build_guide_response(
            action="list_seasonal_ingredients",
            message=f"{month}월 제철 식재료를 조회했어요.",
            data={"month": month, "items": items, "total": len(items)},
        )
    except Exception:
        return build_guide_response(
            action="list_seasonal_ingredients",
            message=f"{month}월 제철 식재료를 조회하지 못했어요.",
            error={"code": "GUIDE_SEASON_ERROR"},
        )

def lookup_ingredient_nutrition(ingredient: str) -> dict[str, Any]:
    """PostgreSQL 영양DB에서 식재료 영양성분을 조회합니다."""
    try:
        lookup_name = _nutrition_lookup_name(ingredient) or ingredient
        guide_data, _ = _lookup_guide_detail(lookup_name)
        ingredient_info = (guide_data or {}).get("ingredient", {})
        names = [
            ingredient_info.get("name"),
            ingredient_info.get("representative_name"),
            ingredient_info.get("raw_name"),
            *ingredient_info.get("aliases", []),
            lookup_name,
        ]
        if not _wants_representative_nutrition(ingredient):
            options = _nutrition_options(lookup_name)
            if len(options) == 1:
                nutrition = _query_nutrition([options[0]["food_code"]])
                if nutrition:
                    source = _source(nutrition.get("source_name"), nutrition.get("source_ref"))
                    return build_guide_response(
                        action="lookup_nutrition",
                        message=f"{nutrition['food_name']} 영양성분을 조회했어요.",
                        data={
                            "ingredient": _ingredient_from_nutrition(nutrition, lookup_name),
                            "nutrition": nutrition,
                        },
                        sources=[source] if source else [],
                        meta={"data_source": "postgresql", "match_type": "food_code"},
                    )
            if len(options) > 1:
                return _nutrition_candidate_response(lookup_name, options)
        nutrition = _query_nutrition(names)
        if not nutrition:
            return build_guide_response(
                action="lookup_nutrition",
                message=f"{ingredient} 영양성분 정보를 찾지 못했어요.",
                status="not_found",
                data={"ingredient": ingredient_info or {"name": ingredient}},
                meta={
                    "result_code": "NUTRITION_NOT_FOUND",
                    "data_source": "postgresql",
                    "fallback_used": False,
                },
            )

        source = _source(nutrition.get("source_name"), nutrition.get("source_ref"))
        display_ingredient = dict(ingredient_info or {"name": ingredient})
        if _normalize_match_text(ingredient) == _normalize_match_text(nutrition.get("representative_name")):
            display_ingredient["name"] = nutrition.get("representative_name")
        return build_guide_response(
            action="lookup_nutrition",
            message=f"{nutrition['representative_name'] or nutrition['food_name']} 영양성분을 조회했어요.",
            data={
                "ingredient": display_ingredient,
                "nutrition": nutrition,
            },
            sources=[source] if source else [],
            meta={"data_source": "postgresql", "fallback_used": False},
        )
    except Exception:
        return build_guide_response(
            action="lookup_nutrition",
            message=f"{ingredient} 영양성분을 조회하지 못했어요.",
            error={"code": "GUIDE_NUTRITION_ERROR"},
            meta={"data_source": "postgresql"},
        )


def answer_guide_query(query: str) -> dict[str, Any]:
    """Guide Agent 내부용 최소 라우터: 월 제철/영양/일반 가이드."""
    print("[Guide Agent 호출]", query)
    query = unicodedata.normalize("NFKC", query or "").strip()
    if not query:
        return _invalid_query_response(
            "조회할 식재료명을 입력해주세요.",
            "EMPTY_GUIDE_QUERY",
        )
    if len(query) > QUERY_MAX_LENGTH:
        return _invalid_query_response(
            "질문이 너무 길어요. 식재료명과 궁금한 정보를 짧게 입력해주세요.",
            "GUIDE_QUERY_TOO_LONG",
        )

    month = re.search(r"(\d{1,2})\s*월", query)
    keyword = _clean_query_keyword(query)

    if month and "제철" in query and not keyword:
        return list_seasonal_ingredients(int(month.group(1)))

    if "제철" in query and not month and not keyword:
        return _request_season_month_response()

    if _is_related_list_query(query):
        related_keyword = _clean_related_keyword(query)
        return list_related_ingredients(related_keyword)

    if not keyword:
        return _invalid_query_response(
            "어떤 식재료를 조회할까요? 예: 감자 보관법, 딸기 제철",
            "INGREDIENT_REQUIRED",
        )

    if any(word in query for word in NUTRITION_WORDS):
        result = lookup_ingredient_nutrition(keyword)
        if result.get("status") == "error":
            return result
        if result.get("status") == "success":
            return result

        candidates, fuzzy_error = _safe_guide_fuzzy_candidates(keyword)
        if fuzzy_error:
            return fuzzy_error
        if candidates:
            if _needs_confirmation(candidates):
                return _confirm_ingredient_response(
                    keyword,
                    candidates,
                    guide_type="nutrition",
                    original_query=query,
                )

            corrected = candidates[0]["name"]
            result = lookup_ingredient_nutrition(corrected)
            if result.get("status") == "error":
                return result
            result["meta"].update(
                {
                    "match_type": "fuzzy_auto",
                    "original_ingredient": keyword,
                    "matched_ingredient": corrected,
                    "match_score": candidates[0]["score"],
                }
            )
            return result
        return result

    ingredient = keyword or query
    result = lookup_ingredient_guide(ingredient)
    if result.get("status") == "error":
        return result
    guide_type = _guide_type_from_query(query)
    data = result.get("data", {})
    guide = _get_requested_guide(data, guide_type)
    if result.get("status") == "success" and guide.get("status") != "missing":
        return _filter_guide_response(result, guide_type)

    if (
        result.get("status") == "not_found"
        and (result.get("meta") or {}).get("result_code") == "GUIDE_NOT_FOUND"
    ):
        candidates, fuzzy_error = _safe_guide_fuzzy_candidates(ingredient)
        if fuzzy_error:
            return fuzzy_error
        if candidates:
            if _needs_confirmation(candidates):
                return _confirm_ingredient_response(
                    ingredient,
                    candidates,
                    guide_type=guide_type,
                    original_query=query,
                )

            corrected = candidates[0]["name"]
            result = lookup_ingredient_guide(corrected)
            if result.get("status") == "error":
                return result
            result["meta"].update(
                {
                    "match_type": "fuzzy_auto",
                    "original_ingredient": ingredient,
                    "matched_ingredient": corrected,
                    "match_score": candidates[0]["score"],
                }
            )
            data = result.get("data", {})
            guide = _get_requested_guide(data, guide_type)
            if result.get("status") == "success" and guide.get("status") != "missing":
                return _filter_guide_response(result, guide_type)

    ingredient_info = data.get("ingredient")
    nutrition = None
    if not ingredient_info:
        nutrition = _query_nutrition([ingredient])
        ingredient_info = _ingredient_from_nutrition(nutrition, ingredient)

    fallback_name = (ingredient_info or {}).get("name") or ingredient
    if guide_type == "all":
        return build_guide_response(
            message=(
                f"{fallback_name} 식재료 가이드를 찾지 못했어요. "
                "보관법, 손질법, 세척법, 신선도 또는 제철 정보를 구체적으로 질문해주세요."
            ),
            status="not_found",
            data={
                "ingredient": ingredient_info or {"name": fallback_name},
            },
            actions=[
                {
                    "type": "suggest_query",
                    "label": f"{fallback_name} 보관법",
                    "value": f"{fallback_name} 보관법 알려줘",
                },
                {
                    "type": "suggest_query",
                    "label": f"{fallback_name} 손질법",
                    "value": f"{fallback_name} 손질법 알려줘",
                },
                {
                    "type": "suggest_query",
                    "label": f"{fallback_name} 제철",
                    "value": f"{fallback_name} 제철 알려줘",
                },
            ],
            meta={
                "result_code": "GUIDE_NOT_FOUND",
                "fallback_used": False,
            },
        )
    return _fallback_guide_response(fallback_name, guide_type, ingredient_info, nutrition)


def finalize_guide_response(
    reply: str,
    *,
    data: dict[str, Any] | None = None,
    actions: list[dict[str, Any]] | None = None,
    sources: list[dict[str, Any]] | None = None,
    error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """기존 Guide Agent의 reply/actions/sources 결과를 최종 계약으로 변환합니다."""
    return build_guide_response(
        message=reply,
        data=data,
        error=error,
        actions=actions,
        sources=sources,
    )


if __name__ == "__main__":
    result = finalize_guide_response(
        "식재료 가이드를 조회했어요.",
        sources=[{"title": "농촌진흥청", "url": "https://www.nics.go.kr"}],
    )
    assert list(result) == [
        "ok",
        "status",
        "agent",
        "action",
        "intent",
        "message",
        "data",
        "error",
        "requires_confirmation",
        "ui",
        "meta",
    ]
    assert result["ok"] is True
    assert result["status"] == "success"
    assert result["error"] is None
    assert result["ui"]["sources"][0]["title"] == "농촌진흥청"

    not_found_result = build_guide_response(
        message="감자 가이드를 찾지 못했어요.",
        status="not_found",
        meta={"result_code": "GUIDE_NOT_FOUND"},
    )
    assert not_found_result["ok"] is True
    assert not_found_result["status"] == "not_found"
    assert not_found_result["error"] is None
    assert not_found_result["meta"]["result_code"] == "GUIDE_NOT_FOUND"

    needs_input_result = _invalid_query_response("조회할 식재료명을 입력해주세요.", "EMPTY_GUIDE_QUERY")
    assert needs_input_result["ok"] is True
    assert needs_input_result["status"] == "needs_input"
    assert needs_input_result["error"] is None

    assert _clean_query_keyword("딸기 5월에 제철이야?") == "딸기"
    assert _clean_query_keyword("고추 냉동해도 괜찮아?") == "고추"
    assert _clean_query_keyword("닭고기 상했는지 확인하는 법 알려줘") == "닭고기"
    assert _clean_query_keyword("닭고기가 상한 것 같아 먹어도 돼?") == "닭고기"
    assert _clean_related_keyword("어떤 식재료가 있어?") == ""
    assert _guide_type_from_query("고추 오래 두는 법") == "storage"
    assert _guide_type_from_query("고추를 깨끗하게 닦으려면?") == "washing"
    assert _guide_type_from_query("고추가 물러졌는데 괜찮아?") == "freshness"
    assert _candidate_query_value("닭가슴살", "freshness") == "닭가슴살 신선도 확인법 알려줘"
    assert _candidate_query_value("닭가슴살", "nutrition") == "닭가슴살 영양성분 알려줘"
    assert _candidate_display_label("닭가슴살", "freshness") == "닭가슴살 신선도 확인법"
    assert _is_unhelpful_web_content("검색 결과에는 우동사리의 보관법에 대한 정보는 포함되어 있지 않습니다.")
