const SAVED_RECIPE_KEY = 'bobbeori-saved-recipes'
const TTL_MS = 7 * 24 * 60 * 60 * 1000

function normalizeRecipe(recipe) {
  const savedAt = recipe.savedAt || new Date().toISOString()
  const expiresAt = recipe.expiresAt || new Date(new Date(savedAt).getTime() + TTL_MS).toISOString()
  const recipeId = recipe.recipeId || recipe.recipe_id || recipe.id || recipe.title
  const savedType =
    recipe.savedType ||
    (recipe.source === '저장한 레시피' || recipe.recommendation_type === 'manual_save'
      ? 'saved'
      : 'recommended')

  return {
    ...recipe,
    id: recipeId,
    recipeId,
    recommendationId: recipe.recommendationId || recipe.recommendation_id,
    savedType,
    storageId: recipe.storageId || `${savedType}:${recipeId}`,
    savedAt,
    expiresAt,
  }
}

export function readStoredRecipes() {
  if (typeof window === 'undefined') return []

  let parsed = []
  try {
    parsed = JSON.parse(window.localStorage.getItem(SAVED_RECIPE_KEY) || '[]')
  } catch {
    parsed = []
  }

  const now = Date.now()
  const saved = parsed
    .map(normalizeRecipe)
    .filter((recipe) => new Date(recipe.expiresAt).getTime() > now)

  window.localStorage.setItem(SAVED_RECIPE_KEY, JSON.stringify(saved))
  return saved
}

export function saveStoredRecipe(recipe) {
  const nextRecipe = normalizeRecipe(recipe)
  const next = [
    nextRecipe,
    ...readStoredRecipes().filter((savedRecipe) => savedRecipe.storageId !== nextRecipe.storageId),
  ]

  window.localStorage.setItem(SAVED_RECIPE_KEY, JSON.stringify(next))
  return nextRecipe
}

export function removeStoredRecipe(storageId) {
  const next = readStoredRecipes().filter((recipe) => recipe.storageId !== storageId)
  window.localStorage.setItem(SAVED_RECIPE_KEY, JSON.stringify(next))
  return next
}

export async function saveRecommendationResult(recipe, recommendationType) {
  const recipeId = Number(recipe.recipe_id || recipe.recipeId || recipe.id)
  const token = window.localStorage.getItem('bobbeori-token')
  if (!token) {
    throw new Error('로그인이 필요해요.')
  }
  if (!Number.isInteger(recipeId)) {
    throw new Error('레시피 정보가 올바르지 않아요.')
  }

  const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000'
  const response = await fetch(`${apiUrl}/api/v1/recommendations`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      recipe_id: recipeId,
      recommendation_type: recommendationType,
    }),
  })

  if (!response.ok) {
    throw new Error(`저장 실패 (${response.status})`)
  }

  return response.json()
}
