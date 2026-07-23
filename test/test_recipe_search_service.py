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


def test_search_text_normalization_and_minimum_ingredient_matches():
    assert search_module.normalize_recipe_search_text("  소고기, 양파 요리  ") == "소고기 양파"
    assert search_module.normalize_recipe_search_text("소고기 와 양파로 만든 요리") == "소고기 양파"
    assert search_module.normalize_recipe_search_text("요리용 소고기") == "요리용 소고기"
    assert [search_module.minimum_ingredient_matches(count) for count in range(1, 6)] == [1, 2, 2, 2, 3]


class IngredientRowsQuery:
    def __init__(self, rows):
        self.rows = rows

    def outerjoin(self, *_args):
        return self

    def all(self):
        return self.rows


class IngredientRowsDb:
    def __init__(self, rows):
        self.rows = rows

    def query(self, *_args):
        return IngredientRowsQuery(self.rows)


def test_ingredient_recognition_prefers_canonical_names_and_tracks_coverage():
    db = IngredientRowsDb(
        [
            (1, "소고기", "소고기", None),
            (2, "쇠고기", "쇠고기", "소고기"),
            (3, "양파", "양파", None),
        ]
    )

    recognition = search_module.RecipeSearchService._recognize_ingredients(
        db,
        "소고기와 양파 요리",
    )

    assert recognition.normalized_text == "소고기 양파"
    assert recognition.ingredient_ids == (1, 3)
    assert recognition.fully_recognized is True
    assert recognition.unmatched_text == ""


def test_ingredient_recognition_rejects_ambiguous_aliases_and_partial_text():
    db = IngredientRowsDb(
        [
            (1, "쇠고기", "쇠고기", "고기"),
            (2, "돼지고기", "돼지고기", "고기"),
            (3, "양파", "양파", None),
        ]
    )

    ambiguous = search_module.RecipeSearchService._recognize_ingredients(db, "고기 요리")
    partial = search_module.RecipeSearchService._recognize_ingredients(db, "매콤한 양파 요리")

    assert ambiguous.ingredient_ids == ()
    assert ambiguous.fully_recognized is False
    assert ambiguous.unmatched_text == "고기"
    assert partial.ingredient_ids == (3,)
    assert partial.fully_recognized is False
    assert partial.unmatched_text == "매콤한"


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


class StageQuery:
    def __init__(self, tag):
        self.tag = tag

    def count(self):
        raise AssertionError("fallback selection must not call count()")

    def join(self, *_args):
        return StageQuery("ingredient")

    def filter(self, *_args):
        return self


class FakeClause:
    def __eq__(self, _other):
        return self

    def desc(self):
        return self


class AggregateQuery:
    def filter(self, *_args):
        return self

    def group_by(self, *_args):
        return self

    def having(self, *_args):
        return self

    def subquery(self):
        return SimpleNamespace(
            c=SimpleNamespace(
                recipe_id=FakeClause(),
                matched_count=FakeClause(),
            )
        )


class AggregateDb:
    def query(self, *_args):
        return AggregateQuery()


class ExistsCandidate:
    def __init__(self):
        self.order_was_cleared = False

    def order_by(self, value):
        self.order_was_cleared = value is None
        return self

    def exists(self):
        return "exists-expression"


class ExistsScalarQuery:
    def scalar(self):
        return True


class ExistsDb:
    def __init__(self):
        self.expression = None

    def query(self, expression):
        self.expression = expression
        return ExistsScalarQuery()


class ZeroResultQuery:
    def count(self):
        return 0

    def order_by(self, *_args):
        raise AssertionError("empty final query must not load a result page")


def test_query_exists_clears_ordering_and_uses_select_exists():
    db = ExistsDb()
    candidate = ExistsCandidate()

    assert search_module.RecipeSearchService._query_exists(db, candidate) is True
    assert candidate.order_was_cleared is True
    assert db.expression == "exists-expression"


def test_final_zero_count_returns_empty_result_without_page_or_facets(monkeypatch):
    service = search_module.RecipeSearchService()
    monkeypatch.setattr(
        service,
        "_select_query_builder",
        lambda **_kwargs: (lambda *_args: ZeroResultQuery(), ()),
    )

    result = service.search_recipes(db=object(), query="없는 검색어", page=2, page_size=5)

    assert result == {
        "items": [],
        "total": 0,
        "page": 2,
        "page_size": 5,
        "has_next": False,
        "facets": {
            "categories": [],
            "difficulties": [],
            "cooking_time_labels": [],
        },
    }


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


def select_query_builder(service, db, *, query, ingredient=None):
    return service._select_query_builder(
        db=db,
        query=query,
        ingredient=ingredient,
        category=None,
        difficulty=None,
        max_cooking_time_min=None,
        cooking_time_label=None,
        main_ingredient_only=False,
    )


def test_normalized_title_search_handles_short_generic_query(monkeypatch):
    checked_stages = []
    service = search_module.RecipeSearchService()
    monkeypatch.setattr(
        search_module,
        "build_recipe_query",
        lambda _db=None, **kwargs: StageQuery(kwargs.get("query") or "base"),
    )
    monkeypatch.setattr(
        service,
        "_recognize_ingredients",
        lambda *_args: search_module.IngredientRecognition("닭", (), 0, 1, "닭"),
    )
    monkeypatch.setattr(
        service,
        "_query_exists",
        lambda _db, candidate: checked_stages.append(candidate.tag) or candidate.tag == "닭",
    )

    builder, _order = select_query_builder(service, object(), query="닭 요리")

    assert checked_stages == ["닭 요리", "닭"]
    assert builder(None, None, None).tag == "닭"


def test_original_title_match_stops_before_normalization(monkeypatch):
    checked_stages = []
    service = search_module.RecipeSearchService()
    monkeypatch.setattr(
        search_module,
        "build_recipe_query",
        lambda _db=None, **kwargs: StageQuery(kwargs.get("query") or "base"),
    )
    monkeypatch.setattr(
        service,
        "_query_exists",
        lambda _db, candidate: checked_stages.append(candidate.tag) or True,
    )
    monkeypatch.setattr(
        service,
        "_recognize_ingredients",
        lambda *_args: (_ for _ in ()).throw(AssertionError("must not normalize")),
    )

    builder, _order = select_query_builder(service, object(), query="닭 요리 특선")

    assert checked_stages == ["닭 요리 특선"]
    assert builder(None, None, None).tag == "닭 요리 특선"


def test_fully_recognized_query_checks_ingredient_before_normalized_title(monkeypatch):
    checked_stages = []
    service = search_module.RecipeSearchService()
    monkeypatch.setattr(
        search_module,
        "build_recipe_query",
        lambda _db=None, **kwargs: StageQuery(kwargs.get("query") or "base"),
    )
    monkeypatch.setattr(
        service,
        "_recognize_ingredients",
        lambda *_args: search_module.IngredientRecognition(
            "소고기 양파",
            (1, 2),
            5,
            5,
            "",
        ),
    )
    monkeypatch.setattr(
        service,
        "_query_exists",
        lambda _db, candidate: checked_stages.append(candidate.tag) or candidate.tag == "ingredient",
    )

    builder, _order = select_query_builder(service, AggregateDb(), query="소고기 양파 요리")

    assert checked_stages == ["소고기 양파 요리", "ingredient"]
    assert builder(None, None, None).tag == "ingredient"


def test_partial_recognition_checks_normalized_title_before_ingredient(monkeypatch):
    checked_stages = []
    service = search_module.RecipeSearchService()
    monkeypatch.setattr(
        search_module,
        "build_recipe_query",
        lambda _db=None, **kwargs: StageQuery(kwargs.get("query") or "base"),
    )
    monkeypatch.setattr(
        service,
        "_recognize_ingredients",
        lambda *_args: search_module.IngredientRecognition(
            "매콤한 소고기",
            (1,),
            3,
            6,
            "매콤한",
        ),
    )
    monkeypatch.setattr(
        service,
        "_query_exists",
        lambda _db, candidate: checked_stages.append(candidate.tag) or candidate.tag == "ingredient",
    )

    builder, _order = select_query_builder(service, AggregateDb(), query="매콤한 소고기 요리")

    assert checked_stages == ["매콤한 소고기 요리", "매콤한 소고기", "ingredient"]
    assert builder(None, None, None).tag == "ingredient"


def test_similarity_is_selected_without_an_extra_existence_check(monkeypatch):
    checked_stages = []
    service = search_module.RecipeSearchService()
    monkeypatch.setattr(
        search_module,
        "build_recipe_query",
        lambda _db=None, **kwargs: StageQuery(kwargs.get("query") or "base"),
    )
    monkeypatch.setattr(
        service,
        "_recognize_ingredients",
        lambda *_args: search_module.IngredientRecognition("스태이크", (), 0, 4, "스태이크"),
    )
    monkeypatch.setattr(
        service,
        "_query_exists",
        lambda _db, candidate: checked_stages.append(candidate.tag) or False,
    )

    builder, _order = select_query_builder(service, object(), query="스태이크")

    assert checked_stages == ["스태이크"]
    assert builder is not None


def test_query_with_explicit_ingredient_keeps_existing_path(monkeypatch):
    service = search_module.RecipeSearchService()
    monkeypatch.setattr(
        search_module,
        "build_recipe_query",
        lambda _db=None, **kwargs: StageQuery("existing"),
    )
    monkeypatch.setattr(
        service,
        "_query_exists",
        lambda *_args: (_ for _ in ()).throw(AssertionError("must not check fallback stages")),
    )

    builder, _order = select_query_builder(service, object(), query="닭", ingredient="양파")

    assert builder(None, None, None).tag == "existing"


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
