const RECIPE_FILTER_PREFIX = 'recipe:'
const MANUAL_FILTER_OPTION = { key: 'manual', label: '직접 추가', type: 'manual' }

function normalizeSourceRefs(item) {
  return Array.isArray(item?.source_refs) ? item.source_refs : []
}

function getOwnedSelectionKey(item) {
  const normalizedName = String(item?.name || '').trim().replace(/\s+/g, ' ').toLowerCase()
  if (normalizedName) {
    return `name:${normalizedName}`
  }
  return item?.ingredient_id != null ? `id:${item.ingredient_id}` : ''
}

function getRecipeSources(list) {
  const sources = []
  const addSource = (source) => {
    if (source?.type && source.type !== 'recipe') {
      return
    }

    const recipeId = source?.recipe_id == null ? null : String(source.recipe_id)
    const recipeTitle = String(source?.recipe_title || '').trim()
    const existing = sources.find((candidate) => (
      (recipeId && candidate.recipeId === recipeId)
      || (!recipeId && recipeTitle && candidate.recipeTitle === recipeTitle)
    ))

    if (existing) {
      if (!existing.recipeTitle && recipeTitle) {
        existing.recipeTitle = recipeTitle
      }
      return
    }

    if (recipeId || recipeTitle) {
      sources.push({ recipeId, recipeTitle })
    }
  }

  ;(list?.source_recipes || []).forEach(addSource)
  addSource({ recipe_id: list?.recipe_id, recipe_title: list?.recipe_title })

  ;(list?.items || []).forEach((item) => {
    normalizeSourceRefs(item).forEach((ref) => {
      if (ref?.type === 'recipe') {
        addSource(ref)
      }
    })
  })

  ;(list?.owned_ingredients || []).forEach((item) => {
    normalizeSourceRefs(item).forEach((ref) => {
      if (ref?.type === 'recipe') {
        addSource(ref)
      }
    })
  })

  return sources.filter((source) => source.recipeTitle)
}

export function getSourceRecipeTitles(list) {
  return getRecipeSources(list).map((source) => source.recipeTitle)
}

export function buildSourceFilterOptions(list, activeItems) {
  const items = Array.isArray(activeItems) ? activeItems : []
  const options = getRecipeSources(list).map((source) => ({
    key: source.recipeId
      ? `${RECIPE_FILTER_PREFIX}id:${source.recipeId}`
      : `${RECIPE_FILTER_PREFIX}title:${source.recipeTitle}`,
    label: source.recipeTitle,
    type: 'recipe',
    recipeId: source.recipeId,
    recipeTitle: source.recipeTitle,
  }))

  const hasManualSource = items.some((item) => (
    item?.source_type === 'manual'
    || normalizeSourceRefs(item).some((ref) => ref?.type === 'manual')
  ))
  if (hasManualSource) {
    options.push(MANUAL_FILTER_OPTION)
  }

  return options
}

export function itemMatchesSourceOption(item, option, recipeOptionCount) {
  if (!option) {
    return true
  }

  const refs = normalizeSourceRefs(item)
  if (option.type === 'recipe') {
    const recipeRefs = refs.filter((ref) => ref?.type === 'recipe')
    if (recipeRefs.some((ref) => (
      (option.recipeId && String(ref?.recipe_id || '') === option.recipeId)
      || String(ref?.recipe_title || '').trim() === option.recipeTitle
    ))) {
      return true
    }

    // 구버전 데이터는 source_type만 있고 source_refs가 비어 있을 수 있다.
    // 레시피 필터가 하나뿐이면 해당 레거시 항목을 그 출처에 포함한다.
    return recipeRefs.length === 0 && item?.source_type === 'recipe' && recipeOptionCount === 1
  }

  return item?.source_type === option.type || refs.some((ref) => ref?.type === option.type)
}

export function areAllSourceItemsSelected(activeItems, ownedItems, selectedOwnedKeys) {
  const active = Array.isArray(activeItems) ? activeItems : []
  const owned = Array.isArray(ownedItems) ? ownedItems : []
  if (active.length + owned.length === 0) {
    return false
  }

  const ownedKeys = new Set(Array.isArray(selectedOwnedKeys) ? selectedOwnedKeys : [])
  return active.every((item) => item?.is_checked)
    && owned.every((item) => {
      const key = getOwnedSelectionKey(item)
      return key && ownedKeys.has(key)
    })
}

export function getShoppingSelectionState(activeItems, ownedItems, selectedOwnedKeys) {
  const active = Array.isArray(activeItems) ? activeItems : []
  const owned = Array.isArray(ownedItems) ? ownedItems : []
  const ownedKeys = new Set(Array.isArray(selectedOwnedKeys) ? selectedOwnedKeys : [])
  const selectedActiveItems = active.filter((item) => item?.is_checked)
  const selectedOwnedItems = owned.filter((item) => ownedKeys.has(getOwnedSelectionKey(item)))

  return {
    selectedActiveItems,
    selectedOwnedItems,
    selectedCount: selectedActiveItems.length + selectedOwnedItems.length,
  }
}

export function getSelectedDeleteCount({
  selectedActiveItems,
  recipeActiveItems,
  recipeOwnedItems,
  isEntireRecipeSelected,
}) {
  if (isEntireRecipeSelected) {
    return (recipeActiveItems?.length || 0) + (recipeOwnedItems?.length || 0)
  }
  return selectedActiveItems?.length || 0
}

export function findExactSelectedRecipe(recipeCandidates, selectedCount, selectedOwnedKeys) {
  const matches = (Array.isArray(recipeCandidates) ? recipeCandidates : []).filter((candidate) => {
    const active = candidate?.recipeItems?.active || []
    const owned = candidate?.recipeItems?.owned || []
    return active.length + owned.length === selectedCount
      && areAllSourceItemsSelected(active, owned, selectedOwnedKeys)
  })

  return matches.length === 1 ? matches[0] : null
}
