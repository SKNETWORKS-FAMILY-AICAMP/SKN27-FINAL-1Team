"""PostgreSQL 레시피 적재용 SQL 정의."""

DELETE_RECOMMENDATION_RESULTS = """
DELETE FROM recommendation_results;
"""

DELETE_RECIPE_INGREDIENTS = """
DELETE FROM recipe_ingredients;
"""

DELETE_RECIPES = """
DELETE FROM recipes;
"""

UPSERT_INGREDIENT = """
INSERT INTO ingredients (name, normalized_name)
VALUES (%(name)s, %(normalized_name)s)
ON CONFLICT (normalized_name) DO UPDATE
SET name = EXCLUDED.name
RETURNING id;
"""

UPSERT_RECIPE = """
INSERT INTO recipes (
    id,
    title,
    description,
    category,
    serving_size,
    cooking_time,
    difficulty,
    image_url,
    source_url
)
VALUES (
    %(id)s,
    %(title)s,
    %(description)s,
    %(category)s,
    %(serving_size)s,
    %(cooking_time)s,
    %(difficulty)s,
    %(image_url)s,
    %(source_url)s
)
ON CONFLICT (id) DO UPDATE SET
    title = EXCLUDED.title,
    description = EXCLUDED.description,
    category = EXCLUDED.category,
    serving_size = EXCLUDED.serving_size,
    cooking_time = EXCLUDED.cooking_time,
    difficulty = EXCLUDED.difficulty,
    image_url = EXCLUDED.image_url,
    source_url = EXCLUDED.source_url;
"""

INSERT_RECIPE_INGREDIENT = """
INSERT INTO recipe_ingredients (
    recipe_id,
    ingredient_id,
    raw_ingredient_name,
    required_quantity,
    unit,
    is_main_ingredient
)
VALUES (
    %(recipe_id)s,
    %(ingredient_id)s,
    %(raw_ingredient_name)s,
    %(required_quantity)s,
    %(unit)s,
    %(is_main_ingredient)s
);
"""

SYNC_RECIPES_ID_SEQUENCE = """
SELECT setval(
    pg_get_serial_sequence('recipes', 'id'),
    COALESCE((SELECT MAX(id) FROM recipes), 1)
);
"""
