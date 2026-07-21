import re
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator, Literal, Optional

from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError

from app.backend.core.config import settings


@dataclass(frozen=True)
class IngredientNameMatch:
    standard_name: Optional[str]
    match_type: Literal["exact", "partial", "none"]


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
        return self.find_best_match(raw_name).standard_name

    def search_standard_names(self, keyword: Optional[str], limit: int = 6) -> list[str]:
        keyword_key = self._match_key(keyword)
        if not keyword_key:
            return []

        scored_names: dict[str, int] = {}
        for candidate_key, standard_name in self._load_neo4j_candidates():
            if not candidate_key or keyword_key not in candidate_key:
                continue

            score = 2
            standard_key = self._match_key(standard_name)
            if candidate_key == keyword_key or standard_key == keyword_key:
                score = 0
            elif candidate_key.startswith(keyword_key) or standard_key.startswith(keyword_key):
                score = 1

            scored_names[standard_name] = min(score, scored_names.get(standard_name, score))

        safe_limit = max(1, min(int(limit or 6), 20))
        return [
            name
            for name, _ in sorted(scored_names.items(), key=lambda item: item[1])
        ][:safe_limit]

    def find_best_match(self, raw_name: Optional[str]) -> IngredientNameMatch:
        raw_key = self._match_key(raw_name)
        if not raw_key:
            return IngredientNameMatch(standard_name=None, match_type="none")

        candidates = self._load_neo4j_candidates()
        exact_names = {standard_name for key, standard_name in candidates if key == raw_key}
        if len(exact_names) == 1:
            return IngredientNameMatch(standard_name=exact_names.pop(), match_type="exact")
        if len(exact_names) > 1:
            return IngredientNameMatch(standard_name=None, match_type="none")

        partial_candidates = [
            (key, standard_name)
            for key, standard_name in candidates
            if len(key) >= 2 and (key in raw_key or raw_key in key)
        ]
        if partial_candidates:
            longest_key_length = max(len(key) for key, _ in partial_candidates)
            best_names = {
                standard_name
                for key, standard_name in partial_candidates
                if len(key) == longest_key_length
            }
            if len(best_names) == 1:
                return IngredientNameMatch(standard_name=best_names.pop(), match_type="partial")

        return IngredientNameMatch(standard_name=None, match_type="none")

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
