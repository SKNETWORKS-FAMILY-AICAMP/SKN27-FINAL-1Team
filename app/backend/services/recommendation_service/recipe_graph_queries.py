"""Whitelisted read-only Cypher for recipe-agent graph search.

Every query returns a single ``recipeIds`` list of numeric RDB-compatible ids.
Keep user values in parameters; never interpolate them into Cypher text.
"""

INGREDIENT_COVERAGE_QUERY = """
UNWIND $ingredientNames AS inputName
MATCH (owned:Ingredient)
WHERE owned.name = inputName OR EXISTS {
  MATCH (owned)-[:HAS_ALIAS]->(alias:Alias) WHERE alias.name = inputName
}
WITH collect(DISTINCT owned) AS ownedIngredients
MATCH (recipe:Recipe)-[:REQUIRES_INGREDIENT]->(required:Ingredient)
WITH recipe, ownedIngredients, collect(DISTINCT required) AS requiredIngredients
WITH recipe, requiredIngredients,
     [i IN requiredIngredients WHERE i IN ownedIngredients] AS matched
WHERE size(matched) > 0
WITH recipe.recipeId AS recipeId, size(matched) AS matchedCount,
     toFloat(size(matched)) / size(requiredIngredients) AS coverage
ORDER BY coverage DESC, matchedCount DESC
LIMIT $limit
RETURN collect(recipeId) AS recipeIds
"""

INGREDIENT_JACCARD_QUERY = """
MATCH (seed:Recipe {recipeId: $recipeId})-[:REQUIRES_INGREDIENT]->(shared:Ingredient)
      <-[:REQUIRES_INGREDIENT]-(candidate:Recipe)
WHERE candidate <> seed
WITH seed, candidate, count(DISTINCT shared) AS intersection
MATCH (seed)-[:REQUIRES_INGREDIENT]->(si:Ingredient)
WITH seed, candidate, intersection, count(DISTINCT si) AS seedCount
MATCH (candidate)-[:REQUIRES_INGREDIENT]->(ci:Ingredient)
WITH candidate, intersection, seedCount, count(DISTINCT ci) AS candidateCount
WITH candidate.recipeId AS recipeId, intersection,
     toFloat(intersection) / (seedCount + candidateCount - intersection) AS score
ORDER BY score DESC, intersection DESC
LIMIT $limit
RETURN collect(recipeId) AS recipeIds
"""

GRAPH_EMBEDDING_SIMILARITY_QUERY = """
MATCH (seed:Recipe {recipeId: $recipeId})
WHERE seed.graphEmbedding IS NOT NULL
MATCH (node:Recipe)
  SEARCH node IN (
    VECTOR INDEX recipe_graph_embedding_index
    FOR seed.graphEmbedding
    LIMIT $candidateCount
  ) SCORE AS score
WHERE node <> seed
WITH node.recipeId AS recipeId, score
ORDER BY score DESC
LIMIT $limit
RETURN collect(recipeId) AS recipeIds
"""

SEASONAL_QUERY = """
MATCH (recipe:Recipe)-[need:REQUIRES_INGREDIENT]->(ingredient:Ingredient)
      -[:IN_SEASON]->(:SeasonMonth {month: $month})
WITH recipe, count(DISTINCT ingredient) AS seasonalCount,
     count(DISTINCT CASE WHEN need.isMain THEN ingredient END) AS mainCount
WITH recipe.recipeId AS recipeId, seasonalCount, mainCount
ORDER BY mainCount DESC, seasonalCount DESC
LIMIT $limit
RETURN collect(recipeId) AS recipeIds
"""

GUIDE_QUERY = """
MATCH (recipe:Recipe)-[:REQUIRES_INGREDIENT]->(ingredient:Ingredient)-[:HAS_GUIDE]->(guide:Guide)
WHERE guide.type = $guideType AND guide.content CONTAINS $keyword
WITH recipe.recipeId AS recipeId, count(DISTINCT ingredient) AS matchedCount
ORDER BY matchedCount DESC
LIMIT $limit
RETURN collect(recipeId) AS recipeIds
"""

TAXONOMY_QUERY = """
MATCH (category:MiddleCategory)-[:HAS_INGREDIENT]->(ingredient:Ingredient)
      <-[:REQUIRES_INGREDIENT]-(recipe:Recipe)
WHERE category.name IN $categoryNames
WITH recipe, count(DISTINCT category) AS matchedCount
WHERE matchedCount >= $minimumCategoryCount
WITH recipe.recipeId AS recipeId, matchedCount
ORDER BY matchedCount DESC
LIMIT $limit
RETURN collect(recipeId) AS recipeIds
"""

NUTRITION_QUERY = """
MATCH (recipe:Recipe)-[:REQUIRES_INGREDIENT]->(ingredient:Ingredient)
      -[:HAS_NUTRITION]->(nutrition:Nutrition)
WITH recipe, avg(nutrition.proteinG) AS proteinAvg,
     avg(nutrition.energyKcal) AS energyAvg, count(DISTINCT ingredient) AS covered
WHERE covered >= $minimumCoveredIngredients
WITH recipe.recipeId AS recipeId, proteinAvg, energyAvg, covered
ORDER BY proteinAvg DESC
LIMIT $limit
RETURN collect(recipeId) AS recipeIds
"""

# Deliberately not exposed through QUERY_REGISTRY until semantic embeddings
# have been generated and recipe_semantic_embedding_index exists.
SEMANTIC_EMBEDDING_QUERY = """
MATCH (recipe:Recipe)
  SEARCH recipe IN (
    VECTOR INDEX recipe_semantic_embedding_index
    FOR $queryEmbedding
    LIMIT $candidateCount
  ) SCORE AS score
WITH recipe.recipeId AS recipeId, score
WHERE score >= $minimumScore
ORDER BY score DESC
LIMIT $limit
RETURN collect(recipeId) AS recipeIds
"""

QUERY_REGISTRY = {
    "ingredient_coverage": INGREDIENT_COVERAGE_QUERY,
    "ingredient_jaccard": INGREDIENT_JACCARD_QUERY,
    "graph_embedding": GRAPH_EMBEDDING_SIMILARITY_QUERY,
    "seasonal": SEASONAL_QUERY,
    "guide": GUIDE_QUERY,
    "taxonomy": TAXONOMY_QUERY,
    "nutrition": NUTRITION_QUERY,
}


def run_recipe_graph_query(session, query_name: str, parameters: dict) -> list[int]:
    """Execute one whitelisted query and normalize its numeric recipe ids."""
    try:
        query = QUERY_REGISTRY[query_name]
    except KeyError as exc:
        raise ValueError(f"unsupported recipe graph query: {query_name}") from exc
    record = session.run(query, parameters).single()
    return [int(value) for value in (record["recipeIds"] if record else [])]
