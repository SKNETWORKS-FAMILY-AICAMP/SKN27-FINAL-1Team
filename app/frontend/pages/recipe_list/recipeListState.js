import { RecipeFilterConfig } from './recipeFilterConfig.js'

const uniqueNonEmpty = (values) => [
  ...new Set((Array.isArray(values) ? values : []).map((value) => String(value ?? '').trim()).filter(Boolean)),
]

export function mergeRecipePages(previous, incoming, replace = false) {
  const merged = replace ? [] : [...previous]
  const seen = new Set(merged.map((recipe) => String(recipe.recipe_id)))

  for (const recipe of Array.isArray(incoming) ? incoming : []) {
    const key = String(recipe?.recipe_id ?? '')
    if (!key || seen.has(key)) continue
    seen.add(key)
    merged.push(recipe)
  }

  return merged
}

export function buildRecipeFilterOptions(total, facets) {
  const hasFacetPayload = facets
    && Array.isArray(facets.categories)
    && Array.isArray(facets.difficulties)
    && Array.isArray(facets.cooking_time_labels)
  const useDynamicOptions = Number(total) > 0 && hasFacetPayload
  const categories = useDynamicOptions ? uniqueNonEmpty(facets.categories) : []
  const difficulties = useDynamicOptions ? uniqueNonEmpty(facets.difficulties) : []
  const cookingTimeLabels = useDynamicOptions ? uniqueNonEmpty(facets.cooking_time_labels) : []

  const recipeTypeDefs = useDynamicOptions
    ? RecipeFilterConfig.filterByApiValues(RecipeFilterConfig.recipeTypes, categories)
    : [...RecipeFilterConfig.recipeTypes]
  const difficultyDefs = useDynamicOptions
    ? RecipeFilterConfig.filterByApiValues(RecipeFilterConfig.difficulties, difficulties)
    : [...RecipeFilterConfig.difficulties]
  const cookingTimeDefs = useDynamicOptions
    ? RecipeFilterConfig.filterByApiValues(RecipeFilterConfig.cookingTimes, cookingTimeLabels)
    : [...RecipeFilterConfig.cookingTimes]

  return {
    recipeTypes: RecipeFilterConfig.toSelectOptions(recipeTypeDefs),
    difficulties: RecipeFilterConfig.toSelectOptions(difficultyDefs),
    cookingTimes: RecipeFilterConfig.toSelectOptions(cookingTimeDefs),
  }
}
