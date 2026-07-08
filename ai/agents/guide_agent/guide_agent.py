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


GUIDE_INTENT = "ingredient.guide"
NUTRITION_WORDS = ("영양", "영양성분", "칼로리", "열량", "탄수화물", "단백질", "지방", "당류", "나트륨")
GUIDE_STOPWORDS = (
    "영양성분", "영양", "칼로리", "열량", "탄수화물", "단백질", "지방", "당류", "나트륨",
    "제철", "보관법", "보관", "손질법", "손질", "세척법", "세척", "신선도", "확인법",
    "알려줘", "조회해줘", "조회", "식재료", "재료", "가이드", "언제야", "뭐야",
)
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
GUIDE_TYPE_LABELS = {
    "storage": "보관법",
    "prep": "손질법",
    "washing": "세척법",
    "freshness": "신선도 확인법",
}


def build_guide_response(
    *,
    message: str,
    action: str = "lookup_ingredient",
    data: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
    requires_confirmation: bool = False,
    actions: list[dict[str, Any]] | None = None,
    cards: list[dict[str, Any]] | None = None,
    sources: list[dict[str, Any]] | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Guide Agent의 기존 처리 결과를 공통 최종 응답으로 감쌉니다."""
    return {
        "ok": error is None,
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


def _source(name: str | None, url: str | None) -> dict[str, str | None] | None:
    return {"title": name, "url": url} if name else None


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
    for word in GUIDE_STOPWORDS:
        keyword = keyword.replace(word, " ")
    return re.sub(r"\s+", " ", keyword).strip()


def _normalize_match_text(value: str | None) -> str:
    value = unicodedata.normalize("NFKC", value or "").lower()
    return re.sub(r"[^0-9a-z가-힣]", "", value)


def _match_score(query: str, candidate: str) -> float:
    query_norm = _normalize_match_text(query)
    candidate_norm = _normalize_match_text(candidate)
    if not query_norm or not candidate_norm:
        return 0.0
    if query_norm == candidate_norm:
        return 1.0
    if query_norm in candidate_norm or candidate_norm in query_norm:
        return 0.94
    return difflib.SequenceMatcher(None, query_norm, candidate_norm).ratio()


def _guide_fuzzy_candidates(ingredient: str, *, limit: int = 5) -> list[dict[str, Any]]:
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
            if score >= 0.72:
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


def _needs_confirmation(candidates: list[dict[str, Any]]) -> bool:
    if not candidates:
        return False
    if candidates[0]["score"] < 0.88:
        return True
    return len(candidates) > 1 and candidates[0]["score"] - candidates[1]["score"] < 0.04


def _confirm_ingredient_response(ingredient: str, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return build_guide_response(
        action="confirm_ingredient",
        message=f"'{ingredient}'와 비슷한 식재료를 찾았어요. 어떤 재료를 조회할까요?",
        data={"input": ingredient, "candidates": candidates},
        requires_confirmation=True,
        actions=[
            {
                "type": "select_candidate",
                "label": f"{candidate['name']}로 조회",
                "value": candidate["name"],
            }
            for candidate in candidates
        ],
        meta={"match_type": "fuzzy", "candidate_count": len(candidates)},
    )


def _lookup_guide_detail(ingredient: str) -> tuple[dict[str, Any] | None, list[dict[str, str | None]]]:
    search = guide_service.search_guides(keyword=ingredient, page=1, page_size=1)
    if not search["items"]:
        return None, []
    detail = guide_service.get_guide_detail(search["items"][0]["code"])
    return _detail_data(detail) if detail else (None, [])


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
                           source_name, source_ref, reference_year, source_priority
                    FROM food_nutrition_facts
                    WHERE food_name = :name OR representative_name = :name
                    ORDER BY source_priority, CASE WHEN representative_name = :name THEN 0 ELSE 1 END, food_name
                    LIMIT 1
                    """
                ),
                {"name": name},
            ).mappings().first()
            if row:
                return dict(row)

        like_name = f"%{candidates[0]}%"
        row = db.execute(
            text(
                """
                SELECT food_code, food_name, representative_name,
                       major_category, middle_category, minor_category,
                       base_amount, energy_kcal, carbohydrate_g, protein_g,
                       fat_g, sugar_g, sodium_mg,
                       source_name, source_ref, reference_year, source_priority
                FROM food_nutrition_facts
                WHERE food_name ILIKE :name OR representative_name ILIKE :name
                ORDER BY source_priority, food_name
                LIMIT 1
                """
            ),
            {"name": like_name},
        ).mappings().first()
        return dict(row) if row else None
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
    if OpenAI is None or not app_settings.OPENAI_API_KEY:
        return content[:600]

    label = GUIDE_TYPE_LABELS.get(guide_type, "식재료 가이드")
    client_ai = OpenAI(api_key=app_settings.OPENAI_API_KEY)
    response = client_ai.chat.completions.create(
        model=app_settings.OPENAI_MODEL,
        messages=[
            {
                "role": "system",
                "content": "검색 결과 안에서만 한국어로 3문장 이내 요약해. 추측하지 말고, 식품 안전상 단정이 어려우면 보수적으로 말해.",
            },
            {"role": "user", "content": f"식재료: {ingredient}\n요청: {label}\n검색 결과:\n{content}"},
        ],
        temperature=0.2,
    )
    return response.choices[0].message.content.strip()


def _web_results(ingredient: str, guide_type: str, *, trusted_only: bool) -> tuple[str | None, list[dict[str, str]]]:
    if TavilyClient is None or not app_settings.TAVILY_API_KEY:
        return None, []

    label = GUIDE_TYPE_LABELS.get(guide_type, "식재료 가이드")
    query = f"{ingredient} {label} 식품안전 농촌진흥청 식약처"
    client = TavilyClient(api_key=app_settings.TAVILY_API_KEY)
    result = client.search(query=query, search_depth="basic", max_results=8)
    picked = []
    for item in result.get("results", []):
        url = item.get("url") or ""
        host = urlparse(url).netloc.lower()
        if any(domain in host for domain in LOW_PRIORITY_BLOCKED_DOMAINS):
            continue
        is_trusted = any(domain in host for domain in TRUSTED_WEB_DOMAINS)
        if trusted_only and not is_trusted:
            continue
        picked.append(item)
    if not picked:
        return None, []

    sources = [
        {"title": item.get("title") or item.get("url") or "공신력 외부 자료", "url": item.get("url") or ""}
        for item in picked[:3]
    ]
    content = "\n".join(item.get("content", "") for item in picked[:3] if item.get("content"))[:1800]
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
    try:
        content, sources = _web_results(ingredient, guide_type, trusted_only=True)
        data_source = "trusted_external"
        source_type = "trusted_external"
        source_label = "외부 공신력 자료"
        if not content:
            content, sources = _web_results(ingredient, guide_type, trusted_only=False)
            data_source = "general_web"
            source_type = "general_web"
            source_label = "후순위 웹 자료"
    except Exception:
        content, sources = None, []

    if not content:
        return build_guide_response(
            message=f"{ingredient} {label}은 내부 공공데이터와 외부 자료에서 찾지 못했어요.",
            data={
                "ingredient": ingredient_info or _ingredient_from_nutrition(nutrition, ingredient),
                "nutrition": nutrition,
                "guide_type": guide_type,
            },
            error={"code": "WEB_GUIDE_NOT_FOUND"},
            meta={
                "data_source": "web",
                "fallback_used": True,
                "internal_data_available": False,
            },
        )

    source = sources[0] if sources else None
    return build_guide_response(
        message=f"내부 공공데이터에는 {ingredient} {label}이 없어, {source_label}를 기준으로 안내드릴게요.",
        data={
            "ingredient": ingredient_info or _ingredient_from_nutrition(nutrition, ingredient),
            "nutrition": nutrition,
            "guides": {
                guide_type: {
                    "status": "available",
                    "content": content,
                    "source": source,
                    "source_type": source_type,
                }
            },
        },
        sources=sources,
        meta={
            "data_source": data_source,
            "fallback_used": True,
            "internal_data_available": False,
        },
    )


def _guide_type_from_query(query: str) -> str:
    normalized = query.replace(" ", "").lower()
    if "손질" in normalized:
        return "prep"
    if "세척" in normalized or "씻" in normalized:
        return "washing"
    if "신선" in normalized or "상한" in normalized:
        return "freshness"
    return "storage"


def list_guide_ingredients(
    *,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 24,
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


def lookup_ingredient_guide(ingredient: str) -> dict[str, Any]:
    """기존 검색과 상세 조회를 이어 전체 식재료 가이드를 반환합니다."""
    try:
        search = guide_service.search_guides(keyword=ingredient, page=1, page_size=1)
        if not search["items"]:
            return build_guide_response(
                message=f"{ingredient} 식재료 가이드를 찾지 못했어요.",
                error={"code": "GUIDE_NOT_FOUND"},
            )
        detail = guide_service.get_guide_detail(search["items"][0]["code"])
        if not detail:
            return build_guide_response(
                message=f"{ingredient} 식재료 가이드를 찾지 못했어요.",
                error={"code": "GUIDE_NOT_FOUND"},
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
            action="list_seasonal_ingredients",
            message="제철 월은 1월부터 12월 사이여야 해요.",
            error={"code": "INVALID_SEASON_MONTH"},
        )
    try:
        items, page = [], 1
        while True:
            result = guide_service.search_guides(page=page, page_size=60)
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
        guide_data, _ = _lookup_guide_detail(ingredient)
        ingredient_info = (guide_data or {}).get("ingredient", {})
        names = [
            ingredient_info.get("name"),
            ingredient_info.get("representative_name"),
            ingredient_info.get("raw_name"),
            *ingredient_info.get("aliases", []),
            ingredient,
        ]
        nutrition = _query_nutrition(names)
        if not nutrition:
            return build_guide_response(
                action="lookup_nutrition",
                message=f"{ingredient} 영양성분 정보를 찾지 못했어요.",
                data={"ingredient": ingredient_info or {"name": ingredient}},
                error={"code": "NUTRITION_NOT_FOUND"},
                meta={"data_source": "postgresql", "fallback_used": False},
            )

        source = _source(nutrition.get("source_name"), nutrition.get("source_ref"))
        return build_guide_response(
            action="lookup_nutrition",
            message=f"{nutrition['representative_name'] or nutrition['food_name']} 영양성분을 조회했어요.",
            data={
                "ingredient": ingredient_info or {"name": ingredient},
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
    month = re.search(r"(\d{1,2})\s*월", query)
    if month and "제철" in query:
        return list_seasonal_ingredients(int(month.group(1)))

    keyword = _clean_query_keyword(query)
    if any(word in query for word in NUTRITION_WORDS):
        result = lookup_ingredient_nutrition(keyword)
        if result.get("ok"):
            return result

        candidates = _guide_fuzzy_candidates(keyword)
        if candidates:
            if _needs_confirmation(candidates):
                return _confirm_ingredient_response(keyword, candidates)

            corrected = candidates[0]["name"]
            result = lookup_ingredient_nutrition(corrected)
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
    guide_type = _guide_type_from_query(query)
    data = result.get("data", {})
    guide = (data.get("guides") or {}).get(guide_type) or {}
    if result.get("ok") and guide.get("status") != "missing":
        return result

    if not result.get("ok") and (result.get("error") or {}).get("code") == "GUIDE_NOT_FOUND":
        candidates = _guide_fuzzy_candidates(ingredient)
        if candidates:
            if _needs_confirmation(candidates):
                return _confirm_ingredient_response(ingredient, candidates)

            corrected = candidates[0]["name"]
            result = lookup_ingredient_guide(corrected)
            result["meta"].update(
                {
                    "match_type": "fuzzy_auto",
                    "original_ingredient": ingredient,
                    "matched_ingredient": corrected,
                    "match_score": candidates[0]["score"],
                }
            )
            data = result.get("data", {})
            guide = (data.get("guides") or {}).get(guide_type) or {}
            if result.get("ok") and guide.get("status") != "missing":
                return result

    ingredient_info = data.get("ingredient")
    nutrition = None
    if not ingredient_info:
        nutrition = _query_nutrition([ingredient])
        ingredient_info = _ingredient_from_nutrition(nutrition, ingredient)

    fallback_name = (ingredient_info or {}).get("name") or ingredient
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
    assert result["ui"]["sources"][0]["title"] == "농촌진흥청"
