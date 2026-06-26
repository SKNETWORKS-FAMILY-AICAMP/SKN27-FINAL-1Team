"""레시피 추천 파이프라인 (fridge_consume / menu_custom)."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.backend.db.models import Recipe
from app.backend.services.recommendation_service._fridge_loader import fetch_fridge_items_with_expiry
from app.backend.services.recommendation_service._recipe_query import build_recipe_query, load_recipe_ingredients_bulk
from app.backend.services.recommendation_service.expiry_scorer import build_reason, score_expiry
from app.backend.services.recommendation_service.fridge_suitability_scorer import FridgeContext, score_fridge_suitability
from app.backend.services.recommendation_service.ingredient_ownership_service import (
    FridgeItemSnapshot,
    classify_ingredients,
    ownership_counts,
)
from app.backend.services.recommendation_service.ownership_tier_service import (
    build_recommend_result,
    empty_recommend_result,
    fill_by_ownership_tiers,
    ownership_tiers,
)
from app.backend.services.recommendation_service.recommend_config import FridgeExpiryRow, RecipeRecommendConfig


class RecipeRecommendEngine:
    def recommend(
        self,
        db: Session,
        user_id: int,
        config: RecipeRecommendConfig,
        *,
        exclude_recipe_ids: list[int] | None = None,
        refresh_pool: bool = False,
    ) -> dict[str, Any]:
        recipes = self._fetch_candidates(db, config)
        if not recipes:
            return empty_recommend_result("no_sql_match")

        expiry_rows = fetch_fridge_items_with_expiry(db, user_id)
        fridge_snapshots = [
            FridgeItemSnapshot(ingredient_id=row.ingredient_id, fridge_name=row.fridge_name)
            for row in expiry_rows
        ]
        fridge_by_id = {row.ingredient_id: row for row in expiry_rows}
        fridge_by_name = {row.fridge_name.strip(): row for row in expiry_rows if row.fridge_name.strip()}
        fridge_context = FridgeContext(user_id=user_id, fridge_snapshots=fridge_snapshots)

        ingredients_by_recipe = load_recipe_ingredients_bulk(db, [recipe.id for recipe in recipes])
        ranked = self._score_candidates(
            recipes,
            ingredients_by_recipe,
            fridge_snapshots,
            fridge_by_id,
            fridge_by_name,
            fridge_context,
            config,
            date.today(),
        )

        if not ranked:
            return empty_recommend_result("no_scorable_recipes")

        self._sort_ranked(ranked, config.mode)

        effective_exclude = [] if refresh_pool else (exclude_recipe_ids or [])
        tiers = ownership_tiers(config)
        items, has_more, applied_tier, fallback_used, empty_reason = fill_by_ownership_tiers(
            ranked,
            tiers,
            effective_exclude,
            config.limit,
        )

        return build_recommend_result(items, has_more, applied_tier, fallback_used, empty_reason)

    @staticmethod
    def _fetch_candidates(db: Session, config: RecipeRecommendConfig) -> list[Recipe]:
        query_recipes = build_recipe_query(
            db,
            query=config.query,
            category=config.category,
            difficulty=config.difficulty,
            cooking_time_label=config.cooking_time_label,
        ).order_by(Recipe.id.desc())

        # ponytail: fridge_consume ~3k full scan; growth → candidate cap or SQL prefilter
        if config.mode == "menu_custom":
            return query_recipes.limit(config.pool_size).all()
        return query_recipes.all()

    def _score_candidates(
        self,
        recipes: list[Recipe],
        ingredients_by_recipe: dict[int, list[dict[str, Any]]],
        fridge_snapshots: list[FridgeItemSnapshot],
        fridge_by_id: dict[int, FridgeExpiryRow],
        fridge_by_name: dict[str, FridgeExpiryRow],
        fridge_context: FridgeContext,
        config: RecipeRecommendConfig,
        today: date,
    ) -> list[dict[str, Any]]:
        ranked: list[dict[str, Any]] = []
        use_ml = config.mode == "menu_custom"

        for recipe in recipes:
            recipe_ingredients = ingredients_by_recipe.get(recipe.id, [])
            if not recipe_ingredients:
                continue

            ownership = classify_ingredients(recipe_ingredients, fridge_snapshots)
            counts = ownership_counts(ownership, config)
            expiry_score, expiring_count = score_expiry(
                ownership,
                fridge_by_id,
                fridge_by_name,
                config,
                today,
            )
            reason = build_reason(expiring_count, counts["display_match_rate"])

            candidate_row: dict[str, Any] = {
                "recipe_id": recipe.id,
                "recipe": recipe,
                "match_rate": ownership.match_rate,
                "display_match_rate": counts["display_match_rate"],
                "owned_ingredient_count": counts["owned_ingredient_count"],
                "missing_ingredient_count": counts["missing_ingredient_count"],
                "expiry_score": expiry_score,
                "reason": reason,
                "_ownership": ownership,
                "_counts": counts,
                "_recipe_ingredients": recipe_ingredients,
            }

            if use_ml:
                weight_score = counts["display_match_rate"] + expiry_score
                candidate_row["_weight_score"] = weight_score
                ml_score = score_fridge_suitability(candidate_row, fridge_context)
                candidate_row["_total_score"] = weight_score + ml_score * 100
            else:
                candidate_row["_sort_expiry"] = expiry_score
                candidate_row["_sort_match"] = counts["display_match_rate"]

            ranked.append(candidate_row)

        return ranked

    @staticmethod
    def _sort_ranked(ranked: list[dict[str, Any]], mode: str) -> None:
        if mode == "menu_custom":
            ranked.sort(
                key=lambda row: (
                    -row["_total_score"],
                    -row["display_match_rate"],
                    -row["recipe_id"],
                )
            )
            return

        ranked.sort(
            key=lambda row: (
                -row["_sort_expiry"],
                -row["_sort_match"],
                -row["recipe_id"],
            )
        )


recipe_recommend_engine = RecipeRecommendEngine()
