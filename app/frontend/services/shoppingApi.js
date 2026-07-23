import { API_URL } from '../utils/api.js'

function getToken() {
  return window.localStorage.getItem('bobbeori-token')
}

function buildHeaders() {
  const token = getToken()
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  }
}

async function parseJsonResponse(response) {
  const data = await response.json().catch(() => null)

  if (response.status === 401) {
    const error = new Error('로그인이 필요해요.')
    error.status = response.status
    throw error
  }

  if (!response.ok) {
    const error = new Error(data?.detail || data?.message || '장보기 정보를 처리하지 못했어요.')
    error.status = response.status
    throw error
  }

  return data
}

async function requestJson(url, options = {}) {
  try {
    const response = await fetch(url, options)
    return parseJsonResponse(response)
  } catch (error) {
    if (error.status) {
      throw error
    }

    console.error('[Shopping API] request failed', { url, error })

    const networkError = new Error(`장보기 API에 연결하지 못했어요. 요청 주소: ${url}`)
    networkError.status = 0
    networkError.url = url
    throw networkError
  }
}

export function hasShoppingAuth() {
  return Boolean(getToken())
}

export async function createRecipeShoppingList({ recipeId, missingIngredients }) {
  return requestJson(`${API_URL}/api/v1/shopping-list/from-recipe`, {
    method: 'POST',
    headers: buildHeaders(),
    body: JSON.stringify({
      recipe_id: recipeId,
      source: 'recipe',
      missing_ingredients: missingIngredients,
    }),
  })
}

export async function createManualShoppingList({ ingredients }) {
  return requestJson(`${API_URL}/api/v1/shopping-list`, {
    method: 'POST',
    headers: buildHeaders(),
    body: JSON.stringify({
      source: 'manual',
      missing_ingredients: ingredients,
    }),
  })
}

export async function searchShoppingProducts(keyword, display = 5) {
  return requestJson(`${API_URL}/api/v1/shopping-list/search-products`, {
    method: 'POST',
    headers: buildHeaders(),
    body: JSON.stringify({
      keyword,
      display,
    }),
  })
}

export async function searchIngredientSuggestions(keyword) {
  const query = String(keyword || '').trim()
  if (!query) {
    return []
  }

  return requestJson(`${API_URL}/api/v1/inventory/suggestions?q=${encodeURIComponent(query)}`, {
    headers: buildHeaders(),
  })
}

export async function getFridgeIngredients() {
  return requestJson(`${API_URL}/api/v1/inventory`, {
    headers: buildHeaders(),
  })
}

export async function getCurrentShoppingList() {
  return requestJson(`${API_URL}/api/v1/shopping-list/current`, {
    headers: buildHeaders(),
  })
}

export async function getShoppingList(shoppingListId) {
  return requestJson(`${API_URL}/api/v1/shopping-list/${shoppingListId}`, {
    headers: buildHeaders(),
  })
}

export async function updateShoppingListItem(itemId, payload) {
  return requestJson(`${API_URL}/api/v1/shopping-list/items/${itemId}`, {
    method: 'PATCH',
    headers: buildHeaders(),
    body: JSON.stringify(payload),
  })
}

export async function deleteShoppingListItem(itemId) {
  return requestJson(`${API_URL}/api/v1/shopping-list/items/${itemId}`, {
    method: 'DELETE',
    headers: buildHeaders(),
  })
}

export async function deleteShoppingList(shoppingListId) {
  return requestJson(`${API_URL}/api/v1/shopping-list/${shoppingListId}`, {
    method: 'DELETE',
    headers: buildHeaders(),
  })
}

export async function removeShoppingListRecipe(shoppingListId, recipeId) {
  return requestJson(`${API_URL}/api/v1/shopping-list/${shoppingListId}/recipes/${recipeId}`, {
    method: 'DELETE',
    headers: buildHeaders(),
  })
}

export async function completeShoppingPurchase(payload) {
  return requestJson(`${API_URL}/api/v1/shopping-list/purchase`, {
    method: 'POST',
    headers: buildHeaders(),
    body: JSON.stringify(payload),
  })
}

export async function compareShoppingProducts(ingredientNames) {
  return requestJson(`${API_URL}/api/v1/shopping-list/compare`, {
    method: 'POST',
    headers: buildHeaders(),
    body: JSON.stringify({
      missing_ingredients: ingredientNames,
    }),
  })
}
