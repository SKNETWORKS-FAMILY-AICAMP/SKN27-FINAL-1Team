"""추천 엔진 설정."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

# ponytail: 기본재료 — 냉장고 없이 owned 처리. normalized_name 또는 ingredient_id 직접 지정.
BASIC_INGREDIENT_NORMALIZED_NAMES: frozenset[str] = frozenset({"물"})
BASIC_INGREDIENT_IDS: frozenset[int] = frozenset()

_EMBEDDED_QUANTITY = re.compile(r"(?:\s+\d|(?<=[가-힣])\d)")


def basic_ingredient_normalized(raw_name: str) -> str | None:
    """기본재료 판정용 최소 정규화. ETL loader 전체 규칙 아님 — 분량 숫자 제거만."""
    text = str(raw_name).strip()
    if not text:
        return None
    text = re.sub(r"^[\s?]+", "", text)
    text = re.sub(r"[\s?]+$", "", text)
    if not text or text == "?":
        return None
    text = _EMBEDDED_QUANTITY.split(text, maxsplit=1)[0].strip()
    if not text:
        return None
    normalized = re.sub(r"\s+", "", text.lower())
    return normalized or None


def is_basic_ingredient(raw_name: str) -> bool:
    normalized = basic_ingredient_normalized(raw_name)
    return normalized is not None and normalized in BASIC_INGREDIENT_NORMALIZED_NAMES


@dataclass(frozen=True)
class RecipeRecommendConfig:
    FRIDGE_CONSUME_LIMIT = 9
    LIMIT_MIN = 1
    LIMIT_MAX = 50
    POOL_SIZE_DEFAULT = 100

    mode: Literal["fridge_consume", "menu_custom"] = "fridge_consume"

    # Request / Candidate Generation (검색 필터)
    query: str | None = None
    category: str | None = None
    difficulty: str | None = None
    cooking_time_label: str | None = None

    # Preference
    require_any_owned: bool = False
    include_maybe_owned: bool = True
    min_display_match_rate: int | None = None
    use_expiry_priority: bool = False
    expiring_soon_days: int = 3
    urgency_base: int = 4
    expiring_ingredient_bonus: int = 2

    # Pagination
    limit: int = 9
    pool_size: int = POOL_SIZE_DEFAULT

    @classmethod
    def fridge_consume_preset(cls) -> RecipeRecommendConfig:
        return cls(
            mode="fridge_consume",
            require_any_owned=True,
            include_maybe_owned=True,
            use_expiry_priority=True,
            limit=cls.FRIDGE_CONSUME_LIMIT,
        )

    @classmethod
    def menu_custom_preset(cls, limit: int, **filters: Any) -> RecipeRecommendConfig:
        return cls(
            mode="menu_custom",
            include_maybe_owned=True,
            limit=cls.clamp_limit(limit),
            **filters,
        )

    @classmethod
    def clamp_limit(cls, value: int) -> int:
        return max(cls.LIMIT_MIN, min(cls.LIMIT_MAX, value))

    @classmethod
    def for_mode(cls, mode: str, *, request_limit: int) -> RecipeRecommendConfig | None:
        if mode == "fridge_consume":
            return cls.fridge_consume_preset()
        if mode == "menu_custom":
            return cls.menu_custom_preset(request_limit)
        return None
