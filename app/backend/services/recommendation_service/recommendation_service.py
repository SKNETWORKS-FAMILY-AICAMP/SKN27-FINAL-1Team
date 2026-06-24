"""사용자 추천·저장 목록(recommendation_results) + 레시피 추천 엔진."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.backend.db.models import FridgeItem, Ingredient, Recipe, RecipeIngredient, RecommendationResult
from app.backend.services.recommendation_service._recipe_query import build_recipe_query, recipe_to_list_item
from app.backend.services.recommendation_service.ingredient_ownership_service import (
    FridgeItemSnapshot,
    OwnershipResult,
    classify_ingredients,
    compute_match_rates,
)


@dataclass(frozen=True)
class RecipeRecommendConfig:
    query: str | None = None
    category: str | None = None
    difficulty: str | None = None
    cooking_time_label: str | None = None

    require_any_owned: bool = False
    include_maybe_owned: bool = True
    min_display_match_rate: int | None = None

    use_expiry_priority: bool = False
    expiring_soon_days: int = 3
    urgency_base: int = 4
    expiring_ingredient_bonus: int = 2

    limit: int = 9

    @classmethod
    def fridge_consume_preset(cls) -> RecipeRecommendConfig:
        return cls(
            require_any_owned=True,
            include_maybe_owned=True,
            use_expiry_priority=True,
            limit=9,
        )


@dataclass(frozen=True)
class FridgeExpiryRow:
    ingredient_id: int
    fridge_name: str
    expiry_date: date | None
    purchased_date: date | None


class RecommendationService:
    MANUAL_SAVE_TYPE = "manual_save"
    FRIDGE_BASED_TYPE = "fridge_based"

    DEFAULT_LIMIT = 9
    DEFAULT_EXPIRING_SOON_DAYS = 3
    DEFAULT_URGENCY_BASE = 4
    DEFAULT_EXPIRING_INGREDIENT_BONUS = 2
    DEFAULT_EXPIRY_FALLBACK_DAYS = 7

    def save_result(
        self,
        db: Session,
        user_id: int,
        recipe_id: int,
        recommendation_type: str,
        *,
        strict: bool = True,
    ) -> dict[str, Any]:
        """레시피를 recommendation_results에 저장한다. 중복 검사 없이 매번 새 행을 만든다."""
        recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()
        if recipe is None:
            if not strict:
                return {}
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

    def save_manual(
        self,
        db: Session,
        user_id: int,
        recipe_id: int,
        recommendation_type: str = MANUAL_SAVE_TYPE,
    ) -> dict[str, Any]:
        return self.save_result(db, user_id, recipe_id, recommendation_type)

    def save_many(
        self,
        db: Session,
        user_id: int,
        recipe_ids: list[int],
        recommendation_type: str,
    ) -> None:
        for recipe_id in recipe_ids:
            self.save_result(db, user_id, recipe_id, recommendation_type, strict=False)

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
        # ponytail: ~3k full scan; growth → candidate cap or SQL prefilter
        recipes = (
            build_recipe_query(
                db,
                query=config.query,
                category=config.category,
                difficulty=config.difficulty,
                cooking_time_label=config.cooking_time_label,
            )
            .order_by(Recipe.id.desc())
            .all()
        )

        expiry_rows = self._fetch_fridge_items_with_expiry(db, user_id)
        fridge_snapshots = [
            FridgeItemSnapshot(ingredient_id=row.ingredient_id, fridge_name=row.fridge_name)
            for row in expiry_rows
        ]
        fridge_by_id = {row.ingredient_id: row for row in expiry_rows}
        fridge_by_name = {row.fridge_name.strip(): row for row in expiry_rows if row.fridge_name.strip()}

        ingredients_by_recipe = self._load_recipe_ingredients_bulk(db, [recipe.id for recipe in recipes])
        today = date.today()

        ranked: list[dict[str, Any]] = []
        for recipe in recipes:
            recipe_ingredients = ingredients_by_recipe.get(recipe.id, [])
            if not recipe_ingredients:
                continue

            ownership = classify_ingredients(recipe_ingredients, fridge_snapshots)
            counts = self._ownership_counts(ownership, config)
            if not self._passes_ownership_filter(counts, ownership, recipe_ingredients, config):
                continue

            expiry_score, expiring_count = self._score_expiry(
                ownership,
                fridge_by_id,
                fridge_by_name,
                config,
                today,
            )
            reason = self._build_reason(expiring_count, counts["display_match_rate"])

            ranked.append(
                {
                    "recipe_id": recipe.id,
                    "recipe": recipe,
                    "match_rate": ownership.match_rate,
                    "display_match_rate": counts["display_match_rate"],
                    "owned_ingredient_count": counts["owned_ingredient_count"],
                    "missing_ingredient_count": counts["missing_ingredient_count"],
                    "expiry_score": expiry_score,
                    "reason": reason,
                    "_sort_expiry": expiry_score,
                    "_sort_match": counts["display_match_rate"],
                }
            )

        ranked.sort(
            key=lambda row: (
                -row["_sort_expiry"],
                -row["_sort_match"],
                -row["recipe_id"],
            )
        )

        effective_exclude = [] if refresh_pool else (exclude_recipe_ids or [])
        items, has_more = self._rank_and_slice(ranked, effective_exclude, config.limit)

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

    def _fetch_fridge_items_with_expiry(self, db: Session, user_id: int) -> list[FridgeExpiryRow]:
        rows = (
            db.query(FridgeItem, Ingredient)
            .join(Ingredient, FridgeItem.ingredient_id == Ingredient.id)
            .filter(
                FridgeItem.user_id == user_id,
                FridgeItem.status == "normal",
            )
            .all()
        )

        return [
            FridgeExpiryRow(
                ingredient_id=int(fridge_item.ingredient_id),
                fridge_name=fridge_item.display_name or ingredient.name,
                expiry_date=fridge_item.expiry_date,
                purchased_date=fridge_item.purchased_date,
            )
            for fridge_item, ingredient in rows
        ]

    def _load_recipe_ingredients_bulk(
        self,
        db: Session,
        recipe_ids: list[int],
    ) -> dict[int, list[dict[str, Any]]]:
        if not recipe_ids:
            return {}

        rows = (
            db.query(RecipeIngredient)
            .filter(RecipeIngredient.recipe_id.in_(recipe_ids))
            .order_by(RecipeIngredient.is_main_ingredient.desc(), RecipeIngredient.id)
            .all()
        )

        grouped: dict[int, list[dict[str, Any]]] = {}
        for row in rows:
            if not row.raw_ingredient_name:
                continue
            grouped.setdefault(row.recipe_id, []).append(
                {
                    "name": row.raw_ingredient_name or "",
                    "amount": None,
                    "ingredient_id": int(row.ingredient_id) if row.ingredient_id else None,
                }
            )
        return grouped

    def _ownership_counts(
        self,
        ownership: OwnershipResult,
        config: RecipeRecommendConfig,
    ) -> dict[str, int]:
        maybe_count = len(ownership.maybe_owned) if config.include_maybe_owned else 0
        owned_count = len(ownership.owned)
        missing_count = len(ownership.missing)
        if not config.include_maybe_owned:
            missing_count += len(ownership.maybe_owned)

        total_required = owned_count + maybe_count + missing_count
        rates = compute_match_rates(owned_count, maybe_count, total_required)

        return {
            "owned_ingredient_count": owned_count + maybe_count,
            "missing_ingredient_count": missing_count,
            "display_match_rate": rates.display_match_rate,
        }

    def _passes_ownership_filter(
        self,
        counts: dict[str, int],
        ownership: OwnershipResult,
        recipe_ingredients: list[dict[str, Any]],
        config: RecipeRecommendConfig,
    ) -> bool:
        owned_count = len(ownership.owned)
        maybe_count = len(ownership.maybe_owned) if config.include_maybe_owned else 0

        if config.require_any_owned and (owned_count + maybe_count) < 1:
            return False

        if config.min_display_match_rate is not None:
            rates = compute_match_rates(
                owned_count,
                maybe_count,
                len(recipe_ingredients),
            )
            if rates.display_match_rate < config.min_display_match_rate:
                return False

        return True

    @staticmethod
    def _d_day(row: FridgeExpiryRow, today: date, fallback_days: int) -> int:
        target = row.expiry_date
        if target is None and row.purchased_date is not None:
            target = row.purchased_date + timedelta(days=fallback_days)
        if target is None:
            return 999
        return (target - today).days

    @staticmethod
    def _urgency(d_day: int, config: RecipeRecommendConfig) -> int:
        if d_day > config.expiring_soon_days:
            return 0
        return max(0, config.urgency_base - d_day)

    def _score_expiry(
        self,
        ownership: OwnershipResult,
        fridge_by_id: dict[int, FridgeExpiryRow],
        fridge_by_name: dict[str, FridgeExpiryRow],
        config: RecipeRecommendConfig,
        today: date,
    ) -> tuple[int, int]:
        if not config.use_expiry_priority:
            return 0, 0

        matched_rows: list[FridgeExpiryRow] = []
        seen_ids: set[int] = set()

        for ingredient in ownership.owned:
            ingredient_id = ingredient.get("ingredient_id")
            if ingredient_id and ingredient_id in fridge_by_id and ingredient_id not in seen_ids:
                matched_rows.append(fridge_by_id[ingredient_id])
                seen_ids.add(ingredient_id)

        if config.include_maybe_owned:
            for ingredient in ownership.maybe_owned:
                fridge_name = (ingredient.get("fridge_ingredient_name") or "").strip()
                row = fridge_by_name.get(fridge_name)
                if row and row.ingredient_id not in seen_ids:
                    matched_rows.append(row)
                    seen_ids.add(row.ingredient_id)

        total_urgency = 0
        expiring_count = 0
        for row in matched_rows:
            d_day = self._d_day(row, today, self.DEFAULT_EXPIRY_FALLBACK_DAYS)
            total_urgency += self._urgency(d_day, config)
            if d_day <= config.expiring_soon_days:
                expiring_count += 1

        score = total_urgency + config.expiring_ingredient_bonus * expiring_count
        return score, expiring_count

    @staticmethod
    def _build_reason(expiring_count: int, display_match_rate: int) -> str | None:
        if expiring_count > 0:
            return f"임박 재료 {expiring_count}개 활용"
        if display_match_rate >= 80:
            return f"보유 재료 {display_match_rate}%로 활용하기 좋아요"
        return None

    @staticmethod
    def _rank_and_slice(
        candidates: list[dict[str, Any]],
        exclude_recipe_ids: list[int],
        limit: int,
    ) -> tuple[list[dict[str, Any]], bool]:
        exclude = set(exclude_recipe_ids)
        filtered = [candidate for candidate in candidates if candidate["recipe_id"] not in exclude]
        items = filtered[:limit]
        has_more = len(filtered) > limit
        return items, has_more


recommendation_service = RecommendationService()
