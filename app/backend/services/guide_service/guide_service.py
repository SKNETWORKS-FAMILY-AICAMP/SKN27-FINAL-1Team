from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError

from app.backend.core.config import settings


class GuideService:
    def __init__(self) -> None:
        self._driver = None

    @property
    def driver(self):
        if self._driver is None:
            self._driver = GraphDatabase.driver(
                settings.NEO4J_URI,
                auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
            )
        return self._driver

    @contextmanager
    def session(self) -> Iterator[Any]:
        session = self.driver.session(database=settings.NEO4J_DATABASE)
        try:
            yield session
        finally:
            session.close()

    def search_guides(self, keyword: str | None = None, limit: int = 60) -> dict[str, Any]:
        normalized_keyword = (keyword or "").strip().lower()
        safe_limit = max(1, min(limit, 100))
        where_clause = """
        WHERE coalesce(g.rawName, g.representativeName, g.name) IS NOT NULL
          AND NOT coalesce(g.rawName, g.representativeName, g.name) STARTS WITH "food-guide-"
        """
        params: dict[str, Any] = {"limit": safe_limit}

        if normalized_keyword:
            where_clause = """
            WHERE coalesce(g.rawName, g.representativeName, g.name) IS NOT NULL
              AND NOT coalesce(g.rawName, g.representativeName, g.name) STARTS WITH "food-guide-"
              AND (
                  toLower(g.name) CONTAINS $keyword
               OR toLower(coalesce(g.representativeName, "")) CONTAINS $keyword
               OR toLower(coalesce(g.rawName, "")) CONTAINS $keyword
               OR any(alias IN coalesce(g.aliases, []) WHERE toLower(alias) CONTAINS $keyword)
              )
            """
            params["keyword"] = normalized_keyword

        count_query = f"""
        MATCH (g:FoodGuide)
        {where_clause}
        RETURN count(g) AS total
        """

        list_query = f"""
        MATCH (g:FoodGuide)
        {where_clause}
        RETURN g.code AS code,
               coalesce(g.rawName, g.representativeName, g.name) AS name,
               g.representativeName AS representative_name,
               g.rawName AS raw_name,
               g.majorCategory AS major_category,
               g.middleCategory AS middle_category,
               g.minorCategory AS minor_category,
               coalesce(g.seasonalMonths, []) AS seasonal_months
        ORDER BY name
        LIMIT $limit
        """

        try:
            with self.session() as session:
                total = int(session.run(count_query, params).single()["total"])
                items = [dict(record) for record in session.run(list_query, params)]
        except Neo4jError as exc:
            raise RuntimeError(f"Neo4j guide search failed: {exc}") from exc

        return {
            "items": items,
            "total": total,
            "returned_count": len(items),
        }

    def get_guide_detail(self, code: str) -> dict[str, Any] | None:
        query = """
        MATCH (g:FoodGuide {code: $code})
        RETURN g.code AS code,
               coalesce(g.rawName, g.representativeName, g.name) AS name,
               g.representativeName AS representative_name,
               g.rawName AS raw_name,
               g.majorCategory AS major_category,
               g.middleCategory AS middle_category,
               g.minorCategory AS minor_category,
               coalesce(g.seasonalMonths, []) AS seasonal_months,
               coalesce(g.aliases, []) AS aliases,
               g.existingDisplayName AS existing_display_name,
               g.storageTip AS storage_tips,
               g.horticulturalStorageTip AS horticultural_storage_tips,
               g.prepTip AS prep_tips,
               g.washingTip AS washing_tips,
               g.freshnessTip AS freshness_tips,
               g.intakeTip AS intake_tips,
               g.nutritionBaseAmount AS nutrition_base_amount,
               g.energyKcal AS energy_kcal,
               g.proteinG AS protein_g,
               g.fatG AS fat_g,
               g.carbohydrateG AS carbohydrate_g,
               g.calciumMg AS calcium_mg,
               g.potassiumMg AS potassium_mg,
               g.sodiumMg AS sodium_mg,
               g.storageSourceName AS storage_source_name,
               g.storageSourceUrl AS storage_source_url,
               g.prepSourceName AS prep_source_name,
               g.prepSourceUrl AS prep_source_url,
               g.washingSourceName AS washing_source_name,
               g.washingSourceUrl AS washing_source_url,
               g.freshnessSourceName AS freshness_source_name,
               g.freshnessSourceUrl AS freshness_source_url,
               g.nutritionSourceName AS nutrition_source_name
        """
        try:
            with self.session() as session:
                record = session.run(query, {"code": code}).single()
        except Neo4jError as exc:
            raise RuntimeError(f"Neo4j guide detail failed: {exc}") from exc

        return dict(record) if record else None


guide_service = GuideService()
