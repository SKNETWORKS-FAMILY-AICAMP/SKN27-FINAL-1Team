import re
from typing import Optional

from sqlalchemy.orm import Session

from app.backend.db.models import Ingredient, IngredientAlias


class IngredientNameMatcher:
    def find_best_ingredient(self, db: Session, raw_name: Optional[str]) -> Optional[Ingredient]:
        raw_key = self._match_key(raw_name)
        if not raw_key:
            return None

        candidates = self._load_candidates(db)
        for key, ingredient in candidates:
            if key == raw_key:
                return ingredient

        for key, ingredient in sorted(candidates, key=lambda item: len(item[0]), reverse=True):
            if len(key) < 2:
                continue
            if key in raw_key or raw_key in key:
                return ingredient

        return None

    def _load_candidates(self, db: Session) -> list[tuple[str, Ingredient]]:
        candidates: list[tuple[str, Ingredient]] = []

        for ingredient in db.query(Ingredient).all():
            for value in (ingredient.name, ingredient.normalized_name):
                key = self._match_key(value)
                if key:
                    candidates.append((key, ingredient))

        aliases = (
            db.query(IngredientAlias, Ingredient)
            .join(Ingredient, IngredientAlias.ingredient_id == Ingredient.id)
            .all()
        )
        for alias, ingredient in aliases:
            key = self._match_key(alias.alias_name)
            if key:
                candidates.append((key, ingredient))

        return candidates

    def _match_key(self, value: Optional[str]) -> str:
        if not value:
            return ""

        text = str(value).strip().lower()
        text = re.sub(r"\([^)]*\)|\[[^\]]*\]|（[^）]*）", "", text)
        text = re.sub(r"\d+(?:\.\d+)?\s*(?:kg|g|ml|l|개입|개|입|봉|팩|병|캔)", "", text, flags=re.IGNORECASE)
        text = re.sub(r"[^0-9a-z가-힣]+", "", text)
        return text


ingredient_name_matcher = IngredientNameMatcher()
