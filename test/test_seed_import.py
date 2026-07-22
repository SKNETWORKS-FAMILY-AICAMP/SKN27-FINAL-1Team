import pytest

from app.backend.jobs import seed_import


def test_seed_import_s3_key_helpers_keep_manifest_paths_relative():
    assert seed_import._normalize_prefix(" /prod/ ") == "prod/"
    assert seed_import._object_key("prod/", "/postgres/recipes.csv") == "prod/postgres/recipes.csv"
    with pytest.raises(ValueError):
        seed_import._object_key("prod/", "s3://bucket/key.csv")


def test_seed_import_validates_sql_identifiers():
    assert seed_import._table_name("public.recipes") == "public.recipes"
    with pytest.raises(ValueError):
        seed_import._table_name("recipes;drop")


def test_seed_import_splits_cypher_statements():
    assert seed_import._split_cypher_statements(
        """
        // comment
        CREATE (:Ingredient {name: 'tofu'});

        MATCH (n) RETURN count(n)
        """
    ) == [
        "CREATE (:Ingredient {name: 'tofu'})",
        "MATCH (n) RETURN count(n)",
    ]
