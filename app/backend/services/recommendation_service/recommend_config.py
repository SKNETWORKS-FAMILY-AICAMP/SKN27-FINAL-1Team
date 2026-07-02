"""추천 엔진 설정."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class RecipeRecommendConfig:
    FRIDGE_CONSUME_LIMIT = 9
    LIMIT_MIN = 1
    LIMIT_MAX = 50
    DEFAULT_POOL_MULTIPLIER = 10
    POOL_MULTIPLIER_MIN = 1
    POOL_MULTIPLIER_MAX = 10
    MIN_REVIEW_RANK_SCORE = 0.0

    mode: Literal["fridge_consume", "menu_custom"] = "fridge_consume"

    # Request / Candidate Generation (검색 필터)
    query: str | None = None
    category: str | None = None
    difficulty: str | None = None
    cooking_time_label: str | None = None

    # Preference (tier fallback 대상)
    require_any_owned: bool = False
    include_maybe_owned: bool = True
    min_display_match_rate: int | None = None
    use_expiry_priority: bool = False
    expiring_soon_days: int = 3
    urgency_base: int = 4
    expiring_ingredient_bonus: int = 2

    # Pagination
    limit: int = 9
    pool_multiplier: int = DEFAULT_POOL_MULTIPLIER

    @classmethod
    def fridge_consume_preset(cls) -> RecipeRecommendConfig:
        return cls(
            mode="fridge_consume",
            require_any_owned=True,
            include_maybe_owned=True,
            use_expiry_priority=True,
            limit=cls.FRIDGE_CONSUME_LIMIT,
            pool_multiplier=cls.DEFAULT_POOL_MULTIPLIER,
        )

    @classmethod
    def menu_custom_preset(cls, limit: int, **filters: Any) -> RecipeRecommendConfig:
        pool_multiplier = filters.pop("pool_multiplier", cls.DEFAULT_POOL_MULTIPLIER)
        return cls(
            mode="menu_custom",
            include_maybe_owned=True,
            limit=cls.clamp_limit(limit),
            pool_multiplier=cls.clamp_pool_multiplier(pool_multiplier),
            **filters,
        )

    @classmethod
    def clamp_limit(cls, value: int) -> int:
        return max(cls.LIMIT_MIN, min(cls.LIMIT_MAX, value))

    @classmethod
    def clamp_pool_multiplier(cls, value: int) -> int:
        return max(cls.POOL_MULTIPLIER_MIN, min(cls.POOL_MULTIPLIER_MAX, value))

    @property
    def pool_size(self) -> int:
        return self.limit * self.pool_multiplier

    @classmethod
    def for_mode(cls, mode: str, *, request_limit: int) -> RecipeRecommendConfig | None:
        if mode == "fridge_consume":
            return cls.fridge_consume_preset()
        if mode == "menu_custom":
            return cls.menu_custom_preset(request_limit)
        return None
