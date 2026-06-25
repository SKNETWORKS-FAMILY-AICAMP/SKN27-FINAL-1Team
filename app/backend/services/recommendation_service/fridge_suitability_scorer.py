"""냉장고 적합도 ML 점수 — 단일 진입점 (현재 random stub)."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

from app.backend.services.recommendation_service.ingredient_ownership_service import FridgeItemSnapshot


@dataclass(frozen=True)
class FridgeContext:
    user_id: int
    fridge_snapshots: list[FridgeItemSnapshot]
    # upgrade path: embedding vectors, purchase history, etc.


def score_fridge_suitability(
    candidate: dict[str, Any],
    fridge_context: FridgeContext,
    *,
    rng: random.Random | None = None,
) -> float:
    """ponytail: random [0,1); upgrade → ai/recommendation trained model."""
    _ = candidate, fridge_context
    source = rng or random
    return source.random()
