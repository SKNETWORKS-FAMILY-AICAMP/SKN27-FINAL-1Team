"""레시피 추천 파이프라인 (Hard Filter → CG → EV → RK → Preference)."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.backend.db.models import Recipe
from app.backend.services.recommendation_service._fridge_loader import fetch_fridge_items_with_expiry
from app.backend.services.recommendation_service._recipe_query import build_recipe_query, load_recipe_ingredients_bulk
from app.backend.services.recommendation_service.expiry_scorer import build_reason, score_expiry
from app.backend.services.recommendation_service.hard_filter import (
    filter_candidates_by_id,
    filter_scored_by_banned,
    load_hard_filter_context,
)
from app.backend.services.recommendation_service.ingredient_ownership_service import (
    FridgeItemSnapshot,
    classify_ingredients,
    ownership_counts,
)
from app.backend.services.recommendation_service.preference_scorer import (
    build_final_score,
    preference_score_for_rank,
)
from app.backend.services.recommendation_service.preference_slice import (
    build_recommend_result,
    empty_recommend_result,
    preference_tiers,
    slice_by_preference_tiers,
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
        exclude = [] if refresh_pool else (exclude_recipe_ids or [])
        hard_ctx = load_hard_filter_context(db, user_id)

        recipes = self._generate_candidates(db, config)
        recipes = filter_candidates_by_id(recipes, exclude)
        if not recipes:
            return empty_recommend_result("no_sql_match")

        expiry_rows = fetch_fridge_items_with_expiry(db, user_id)
        fridge_snapshots = [
            FridgeItemSnapshot(ingredient_id=row.ingredient_id, fridge_name=row.fridge_name)
            for row in expiry_rows
        ]
        fridge_by_id = {row.ingredient_id: row for row in expiry_rows}
        fridge_by_name = {row.fridge_name.strip(): row for row in expiry_rows if row.fridge_name.strip()}

        ingredients_by_recipe = load_recipe_ingredients_bulk(db, [recipe.id for recipe in recipes])
        scored = self._evaluate_candidates(
            recipes,
            ingredients_by_recipe,
            fridge_snapshots,
            fridge_by_id,
            fridge_by_name,
            config,
            date.today(),
        )
        scored = filter_scored_by_banned(scored, hard_ctx)
        if not scored:
            return empty_recommend_result("no_scorable_recipes")

        self._rank_candidates(scored, config)

        items, has_more, applied_tier, fallback_used, empty_reason = slice_by_preference_tiers(
            scored,
            preference_tiers(config),
            config.limit,
        )

        return build_recommend_result(items, has_more, applied_tier, fallback_used, empty_reason)

    @staticmethod
    def _generate_candidates(db: Session, config: RecipeRecommendConfig) -> list[Recipe]:
        # ponytail: global_recipe_pool provider hook
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

    def _evaluate_candidates(
        self,
        recipes: list[Recipe],
        ingredients_by_recipe: dict[int, list[dict[str, Any]]],
        fridge_snapshots: list[FridgeItemSnapshot],
        fridge_by_id: dict[int, FridgeExpiryRow],
        fridge_by_name: dict[str, FridgeExpiryRow],
        config: RecipeRecommendConfig,
        today: date,
    ) -> list[dict[str, Any]]:
        ranked: list[dict[str, Any]] = []

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
            fridge_score = counts["display_match_rate"]
            preference_score = preference_score_for_rank(ownership, recipe_ingredients, config)
            missing_penalty = 0
            final_score = build_final_score(
                config.mode,
                fridge_score,
                expiry_score,
                preference_score,
                missing_penalty,
            )

            ranked.append(
                {
                    "recipe_id": recipe.id,
                    "recipe": recipe,
                    "match_rate": ownership.match_rate,
                    "display_match_rate": fridge_score,
                    "owned_ingredient_count": counts["owned_ingredient_count"],
                    "missing_ingredient_count": counts["missing_ingredient_count"],
                    "expiry_score": expiry_score,
                    "reason": reason,
                    "_ownership": ownership,
                    "_recipe_ingredients": recipe_ingredients,
                    "fridge_score": fridge_score,
                    "preference_score": preference_score,
                    "missing_penalty": missing_penalty,
                    "final_score": final_score,
                }
            )

        return ranked

    @staticmethod
    def _rank_candidates(ranked: list[dict[str, Any]], config: RecipeRecommendConfig) -> None:
        del config
        ranked.sort(
            key=lambda row: (
                -row["final_score"],
                -row["display_match_rate"],
                -row["recipe_id"],
            )
        )


recipe_recommend_engine = RecipeRecommendEngine()
