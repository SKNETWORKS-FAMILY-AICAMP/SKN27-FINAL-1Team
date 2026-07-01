import re
from contextlib import contextmanager
from typing import Any, Iterator, Optional

from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError

from app.backend.core.config import settings


class IngredientNameMatcher:
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

    def find_best_name(self, raw_name: Optional[str]) -> Optional[str]:
        raw_key = self._match_key(raw_name)
        if not raw_key:
            return None

        candidates = self._load_neo4j_candidates()
        for key, standard_name in candidates:
            if key == raw_key:
                return standard_name

        for key, standard_name in sorted(candidates, key=lambda item: len(item[0]), reverse=True):
            if len(key) < 2:
                continue
            if key in raw_key or raw_key in key:
                return standard_name

        return None

    def _load_neo4j_candidates(self) -> list[tuple[str, str]]:
        query = """
        MATCH (g:FoodGuide)
        WHERE coalesce(g.name, g.representativeName, g.rawName) IS NOT NULL
          AND NOT coalesce(g.name, g.rawName, g.representativeName) STARTS WITH "food-guide-"
        RETURN coalesce(g.name, g.representativeName, g.rawName) AS standard_name,
               [value IN [
                 g.name,
                 g.representativeName,
                 g.rawName,
                 g.existingDisplayName
               ] WHERE value IS NOT NULL] + coalesce(g.aliases, []) AS names
        """
        try:
            with self.session() as session:
                records = session.run(query)
                candidates: list[tuple[str, str]] = []
                for record in records:
                    standard_name = (record["standard_name"] or "").strip()
                    if not standard_name:
                        continue
                    for value in record["names"] or []:
                        key = self._match_key(value)
                        if key:
                            candidates.append((key, standard_name))
                return candidates
        except Neo4jError:
            return []

    def _match_key(self, value: Optional[str]) -> str:
        if not value:
            return ""

        text = str(value).strip().lower()
        text = re.sub(r"\([^)]*\)|\[[^\]]*\]|\uff08[^\uff09]*\uff09|<[^>]*>", "", text)
        text = re.sub(
            r"\d+(?:\.\d+)?\s*(?:kg|g|ml|l|\uac1c\uc785|\uac1c|\uc785|\ubd09|\ud329|\ubcd1|\uce94)",
            "",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(r"[^0-9a-z\uac00-\ud7a3]+", "", text)
        return text


ingredient_name_matcher = IngredientNameMatcher()
