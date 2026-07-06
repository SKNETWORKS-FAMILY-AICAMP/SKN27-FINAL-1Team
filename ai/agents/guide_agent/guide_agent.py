from typing import Any

from app.backend.services.guide_service.guide_service import guide_service


GUIDE_INTENT = "ingredient.guide"


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
