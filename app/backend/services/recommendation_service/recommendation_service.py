"""사용자 추천 저장(recommendation_results) + 추천 엔진."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.backend.db.models import Recipe, RecommendationResult
from app.backend.services.recommendation_service.fridge import (
    FridgeExpiryRow,
    FridgeItemSnapshot,
    FridgeMatchResult,
    classify_fridge_match,
    compute_match_rates,
    fetch_fridge_expiry_rows,
    fetch_fridge_snapshots,
)
from app.backend.services.recommendation_service.recipe_query import (
    build_recipe_query,
    filter_candidates_by_id,
    filter_recipes_by_banned,
    load_hard_filter_context,
    load_recipe_ingredients_bulk,
    recipe_to_list_item,
)
from app.backend.services.recommendation_service.recommend_config import RecipeRecommendConfig
from app.backend.services.recommendation_service.recommend_model import score_recipes

__all__ = [
    "RecipeRecommendConfig",
    "RecommendationService",
    "recommendation_service",
]

EXPIRY_WEIGHT_FRIDGE_CONSUME = 1000
DEFAULT_EXPIRY_FALLBACK_DAYS = 7


def _empty_recommend_result() -> dict[str, Any]:
    return {"items": [], "returned_count": 0, "has_more": False}


def _match_counts(fridge_match: FridgeMatchResult, config: RecipeRecommendConfig) -> dict[str, int]:
    maybe_count = len(fridge_match.maybe_owned) if config.include_maybe_owned else 0
    owned_count = len(fridge_match.owned)
    missing_count = len(fridge_match.missing)
    if not config.include_maybe_owned:
        missing_count += len(fridge_match.maybe_owned)

    total_required = owned_count + maybe_count + missing_count
    rates = compute_match_rates(owned_count, maybe_count, total_required)
    return {
        "owned_ingredient_count": owned_count + maybe_count,
        "missing_ingredient_count": missing_count,
        "display_match_rate": rates.display_match_rate,
        "match_rate": rates.match_rate,
    }


def _d_day(row: FridgeExpiryRow, today: date) -> int:
    target = row.expiry_date
    if target is None and row.purchased_date is not None:
        target = row.purchased_date + timedelta(days=DEFAULT_EXPIRY_FALLBACK_DAYS)
    if target is None:
        return 999
    return (target - today).days


def _score_expiry(
    fridge_match: FridgeMatchResult,
    expiry_by_id: dict[int, FridgeExpiryRow],
    expiry_by_name: dict[str, FridgeExpiryRow],
    config: RecipeRecommendConfig,
    today: date,
) -> tuple[int, int]:
    if not config.use_expiry_priority:
        return 0, 0

    matched_rows: list[FridgeExpiryRow] = []
    seen_ids: set[int] = set()

    for ingredient in fridge_match.owned:
        ingredient_id = ingredient.get("ingredient_id")
        if ingredient_id and ingredient_id in expiry_by_id and ingredient_id not in seen_ids:
            matched_rows.append(expiry_by_id[ingredient_id])
            seen_ids.add(ingredient_id)

    if config.include_maybe_owned:
        for ingredient in fridge_match.maybe_owned:
            fridge_name = (ingredient.get("fridge_ingredient_name") or "").strip()
            row = expiry_by_name.get(fridge_name)
            if row and row.ingredient_id not in seen_ids:
                matched_rows.append(row)
                seen_ids.add(row.ingredient_id)

    total_urgency = 0
    expiring_count = 0
    for row in matched_rows:
        d_day_value = _d_day(row, today)
        if d_day_value <= config.expiring_soon_days:
            total_urgency += max(0, config.urgency_base - d_day_value)
            expiring_count += 1

    return total_urgency + config.expiring_ingredient_bonus * expiring_count, expiring_count


def _build_reason(expiring_count: int, display_match_rate: int) -> str | None:
    if expiring_count > 0:
        return f"임박 재료 {expiring_count}개 활용"
    if display_match_rate >= 80:
        return f"보유 재료 {display_match_rate}%로 활용하기 좋아요"
    return None


def _build_final_score(mode: str, display_rate: int, expiry_score: int) -> int:
    if mode == "fridge_consume":
        return expiry_score * EXPIRY_WEIGHT_FRIDGE_CONSUME + display_rate
    return display_rate + expiry_score


def _build_recommend_result(items: list[dict[str, Any]], has_more: bool) -> dict[str, Any]:
    response_items = []
    for row in items:
        base = recipe_to_list_item(row["recipe"])
        response_items.append(
            {
                **base,
                "match_rate": row["match_rate"],
                "display_match_rate": row["display_match_rate"],
                "owned_ingredient_count": row["owned_ingredient_count"],
                "missing_ingredient_count": row["missing_ingredient_count"],
                "expiry_score": row["expiry_score"],
                "reason": row["reason"],
            }
        )

    return {
        "items": response_items,
        "returned_count": len(response_items),
        "has_more": has_more,
    }


class RecommendationService:
    MANUAL_SAVE_TYPE = "manual_save"

    def save_recipe(
        self,
        db: Session,
        user_id: int,
        recipe_id: int,
        recommendation_type: str = MANUAL_SAVE_TYPE,
    ) -> dict[str, Any]:
        """레시피를 recommendation_results에 저장한다. 중복 검사 없이 매번 새 행을 만든다."""
        recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()
        if recipe is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="레시피를 찾을 수 없습니다.",
            )

        row = RecommendationResult(
            user_id=user_id,
            recipe_id=recipe_id,
            recommendation_type=recommendation_type,
        )
        db.add(row)
        db.commit()
        db.refresh(row)

        return {
            "recommendation_id": int(row.id),
            "recipe_id": int(row.recipe_id),
            "recommendation_type": row.recommendation_type or recommendation_type,
            "created_at": row.created_at,
        }

    def list_user_recipes(self, db: Session, user_id: int) -> list[dict[str, Any]]:
        rows = (
            db.query(RecommendationResult)
            .filter(RecommendationResult.user_id == user_id)
            .order_by(RecommendationResult.created_at.desc())
            .all()
        )

        return [
            {
                "recommendation_id": int(row.id),
                "recipe_id": int(row.recipe_id),
                "title": row.recipe.title,
                "description": row.recipe.description,
                "category": row.recipe.category,
                "cooking_time_min": row.recipe.cooking_time,
                "difficulty": row.recipe.difficulty,
                "image_url": row.recipe.image_url,
                "recommendation_type": row.recommendation_type or self.MANUAL_SAVE_TYPE,
                "created_at": row.created_at,
            }
            for row in rows
            if row.recipe is not None
        ]

    def delete_user_recipe(self, db: Session, user_id: int, recommendation_id: int) -> None:
        row = (
            db.query(RecommendationResult)
            .filter(
                RecommendationResult.id == recommendation_id,
                RecommendationResult.user_id == user_id,
            )
            .first()
        )
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="저장 레시피를 찾을 수 없습니다.")

        db.delete(row)
        db.commit()

    def recommend_recipes(
        self,
        db: Session,
        user_id: int,
        config: RecipeRecommendConfig,
        *,
        exclude_recipe_ids: list[int] | None = None,
        refresh_pool: bool = False,
    ) -> dict[str, Any]:
        hard_ctx = load_hard_filter_context(db, user_id)
        exclude = [] if refresh_pool else (exclude_recipe_ids or [])

        # ── 하드필터: 레시피 ID 확정 ──
        recipes = self._generate_candidates(db, config)
        recipes = filter_candidates_by_id(recipes, exclude)
        if not recipes:
            return _empty_recommend_result()

        ingredients_by_recipe = load_recipe_ingredients_bulk(db, [recipe.id for recipe in recipes])
        recipes = filter_recipes_by_banned(recipes, ingredients_by_recipe, hard_ctx)
        if not recipes:
            return _empty_recommend_result()

        recipes = recipes[: config.pool_size]

        # ── 추론 ──
        model_scores = score_recipes([r.id for r in recipes], str(user_id))

        # ── 후처리: fridge 매칭 + 정렬 + 응답 ──
        expiry_rows = fetch_fridge_expiry_rows(db, user_id)
        fridge_snapshots = fetch_fridge_snapshots(db, user_id)
        expiry_by_id = {row.ingredient_id: row for row in expiry_rows}
        expiry_by_name = {
            row.fridge_name.strip(): row for row in expiry_rows if row.fridge_name.strip()
        }

        scored = self._evaluate_candidates(
            recipes,
            ingredients_by_recipe,
            fridge_snapshots,
            expiry_by_id,
            expiry_by_name,
            config,
            date.today(),
            model_scores=model_scores,
        )
        if not scored:
            return _empty_recommend_result()

        self._rank_candidates(scored)
        items = scored[: config.limit]
        has_more = len(scored) > config.limit
        return _build_recommend_result(items, has_more)

    @staticmethod
    def _generate_candidates(db: Session, config: RecipeRecommendConfig) -> list[Recipe]:
        query_recipes = build_recipe_query(
            db,
            query=config.query,
            category=config.category,
            difficulty=config.difficulty,
            cooking_time_label=config.cooking_time_label,
        ).order_by(Recipe.id.desc())

        return query_recipes.all()

    @staticmethod
    def _evaluate_candidates(
        recipes: list[Recipe],
        ingredients_by_recipe: dict[int, list[dict[str, Any]]],
        fridge_snapshots: list[FridgeItemSnapshot],
        expiry_by_id: dict[int, FridgeExpiryRow],
        expiry_by_name: dict[str, FridgeExpiryRow],
        config: RecipeRecommendConfig,
        today: date,
        *,
        model_scores: dict[int, float],
    ) -> list[dict[str, Any]]:
        ranked: list[dict[str, Any]] = []

        for recipe in recipes:
            recipe_ingredients = ingredients_by_recipe.get(recipe.id, [])
            if not recipe_ingredients:
                continue

            fridge_match = classify_fridge_match(recipe_ingredients, fridge_snapshots)
            counts = _match_counts(fridge_match, config)
            expiry_score, expiring_count = _score_expiry(
                fridge_match,
                expiry_by_id,
                expiry_by_name,
                config,
                today,
            )
            display_rate = counts["display_match_rate"]
            reason = _build_reason(expiring_count, display_rate)
            final_score = _build_final_score(config.mode, display_rate, expiry_score)

            ranked.append(
                {
                    "recipe_id": recipe.id,
                    "recipe": recipe,
                    "match_rate": counts["match_rate"],
                    "display_match_rate": display_rate,
                    "owned_ingredient_count": counts["owned_ingredient_count"],
                    "missing_ingredient_count": counts["missing_ingredient_count"],
                    "expiry_score": expiry_score,
                    "reason": reason,
                    "final_score": final_score,
                    "model_score": model_scores.get(recipe.id, 0.0),
                }
            )

        return ranked

    @staticmethod
    def _rank_candidates(ranked: list[dict[str, Any]]) -> None:
        ranked.sort(
            key=lambda row: (
                -row["model_score"],
                -row["final_score"],
                -row["display_match_rate"],
                -row["recipe_id"],
            )
        )


recommendation_service = RecommendationService()
