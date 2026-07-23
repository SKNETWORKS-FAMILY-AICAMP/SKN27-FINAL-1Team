const RECIPE_FILTER_PREFIX = 'recipe:'
const MANUAL_FILTER_OPTION = { key: 'manual', label: '직접 추가', type: 'manual' }

function normalizeSourceRefs(item) {
  return Array.isArray(item?.source_refs) ? item.source_refs : []
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
