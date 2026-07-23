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

  const categoryValues = useDynamicOptions ? categories : RecipeFilterConfig.recipeTypes
  const difficultyValues = useDynamicOptions ? difficulties : RecipeFilterConfig.difficulties
  const availableCookingTimes = useDynamicOptions
    ? RecipeFilterConfig.cookingTimes.filter((option) => cookingTimeLabels.includes(option.value))
    : RecipeFilterConfig.cookingTimes

  return {
    recipeTypes: RecipeFilterConfig.toSelectOptions(categoryValues, RecipeFilterConfig.FILTER_ALL),
    difficulties: [RecipeFilterConfig.FILTER_ALL, ...difficultyValues],
    cookingTimes: [
      { value: RecipeFilterConfig.FILTER_ALL, label: RecipeFilterConfig.FILTER_ALL },
      ...availableCookingTimes,
    ],
  }
}
