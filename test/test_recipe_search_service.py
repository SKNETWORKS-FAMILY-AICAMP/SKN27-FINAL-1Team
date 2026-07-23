from types import SimpleNamespace

from app.backend.services.recommendation_service import recipe_search_service as search_module


RECIPES = [
    SimpleNamespace(
        id=1,
        title="빠른 국",
        category="국·탕",
        difficulty="쉬움",
        cooking_time=10,
        serving_size=2,
    ),
    SimpleNamespace(
        id=2,
        title="든든한 밥",
        category="밥·덮밥",
        difficulty="보통",
        cooking_time=25,
        serving_size=2,
    ),
    SimpleNamespace(
        id=3,
        title="오래 끓인 국",
        category="국·탕",
        difficulty="보통",
        cooking_time=45,
        serving_size=4,
    ),
    SimpleNamespace(
        id=4,
        title="속성 반찬",
        category=" ",
        difficulty=None,
        cooking_time=None,
        serving_size=1,
    ),
]


class FakeQuery:
    def __init__(self, rows, selected_key=None):
        self.rows = list(rows)
        self.selected_key = selected_key

    def count(self):
        return len(self.rows)

    def order_by(self, *_args):
        if self.selected_key:
            self.rows.sort(key=lambda row: str(getattr(row, self.selected_key) or ""))
        else:
            self.rows.sort(key=lambda row: row.id, reverse=True)
        return self

    def offset(self, amount):
        self.rows = self.rows[amount:]
        return self

    def limit(self, amount):
        self.rows = self.rows[:amount]
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def with_entities(self, column):
        return FakeQuery(self.rows, column.key)

    def filter(self, *_args):
        return self

    def distinct(self):
        if self.selected_key:
            seen = set()
            self.rows = [
                row
                for row in self.rows
                if not (getattr(row, self.selected_key) in seen or seen.add(getattr(row, self.selected_key)))
            ]
        return self

    def all(self):
        if self.selected_key:
            return [(getattr(row, self.selected_key),) for row in self.rows]
        return self.rows


def fake_build_recipe_query(_db=None, **kwargs):
    rows = list(RECIPES)
    category = kwargs.get("category")
    difficulty = kwargs.get("difficulty")
    cooking_time_label = kwargs.get("cooking_time_label")

    if category:
        rows = [row for row in rows if row.category == category]
    if difficulty:
        rows = [row for row in rows if row.difficulty == difficulty]
    if cooking_time_label == "15분이내":
        rows = [row for row in rows if row.cooking_time is not None and row.cooking_time <= 15]
    elif cooking_time_label == "30분이내":
        rows = [row for row in rows if row.cooking_time is not None and row.cooking_time <= 30]
    elif cooking_time_label == "30분이상":
        rows = [row for row in rows if row.cooking_time is not None and row.cooking_time >= 30]
    return FakeQuery(rows)


def test_search_facets_exclude_only_their_own_axis(monkeypatch):
    monkeypatch.setattr(search_module, "build_recipe_query", fake_build_recipe_query)
    monkeypatch.setattr(
        search_module,
        "recipe_to_list_item",
        lambda recipe: {"recipe_id": recipe.id, "title": recipe.title},
    )

    result = search_module.RecipeSearchService().search_recipes(
        db=object(),
        category="국·탕",
        difficulty="보통",
        page=1,
        page_size=1,
    )

    assert result["total"] == 1
    assert result["has_next"] is False
    assert result["facets"] == {
        "categories": ["국·탕", "밥·덮밥"],
        "difficulties": ["보통", "쉬움"],
        "cooking_time_labels": ["30분이상"],
    }


def test_search_returns_empty_facets_when_no_recipe_matches(monkeypatch):
    monkeypatch.setattr(search_module, "build_recipe_query", fake_build_recipe_query)

    result = search_module.RecipeSearchService().search_recipes(
        db=object(),
        category="없는 카테고리",
    )

    assert result["items"] == []
    assert result["total"] == 0
    assert result["has_next"] is False
    assert result["facets"] == {
        "categories": [],
        "difficulties": [],
        "cooking_time_labels": [],
    }
