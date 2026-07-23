import React, { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import './ShoppingList.css'

import imageShop from '../../assets/extracted/images/image_shop.png'
import { useAppDialog } from '../../components/AppDialog.jsx'
import {
  buildSourceFilterOptions,
  getSourceRecipeTitles,
  itemMatchesSourceOption,
} from './shoppingSourceFilters.js'
import {
  compareShoppingProducts,
  completeShoppingPurchase,
  createManualShoppingList,
  deleteShoppingList,
  deleteShoppingListItem,
  getFridgeIngredients,
  getCurrentShoppingList,
  getShoppingList,
  hasShoppingAuth,
  removeShoppingListRecipe,
  searchIngredientSuggestions,
  searchShoppingProducts,
  updateShoppingListItem,
} from '../../services/shoppingApi.js'

const SHOPPING_CONTEXT_KEY = 'bobbeori-recipe-shopping-context'
const SHOPPING_STATUS_FILTERS = [
  { key: 'all', label: '전체' },
  { key: 'need_buy', label: '구매 필요' },
  { key: 'owned', label: '보유 재료' },
]

function ImageSlot({ src, alt = '', className = '' }) {
  return (
    <span className={`shopping-image-slot ${src ? 'is-filled' : ''} ${className}`}>
      {src ? <img src={src} alt={alt} /> : null}
    </span>
  )
}

function readShoppingContext() {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(SHOPPING_CONTEXT_KEY) || 'null')
    if (!parsed || parsed.type !== 'recipe') {
      return null
    }
    return {
      ...parsed,
      ownedIngredients: Array.isArray(parsed.ownedIngredients) ? parsed.ownedIngredients : [],
      missingIngredients: Array.isArray(parsed.missingIngredients) ? parsed.missingIngredients : [],
    }
  } catch {
    return null
  }
}

function formatCreatedAt(value) {
  if (!value) {
    return '최근 장보기'
  }

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return '최근 장보기'
  }

  return date.toLocaleString('ko-KR', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatPrice(value) {
  if (value == null) {
    return '가격 확인 필요'
  }
  return `${Number(value).toLocaleString('ko-KR')}원`
}

function formatQuantity(item) {
  if (item.amount) {
    return item.amount
  }

  if (item.required_quantity == null && !item.unit) {
    return '필요 수량 확인'
  }

  const quantity = item.required_quantity == null ? '' : Number(item.required_quantity).toLocaleString('ko-KR')
  return `${quantity}${item.unit || ''}`.trim()
}

function parseDateOnly(value) {
  if (!value) {
    return null
  }

  const [year, month, day] = String(value).slice(0, 10).split('-').map(Number)
  if (!year || !month || !day) {
    return null
  }

  return new Date(year, month - 1, day)
}

function isOwnedIngredientExpired(item) {
  if (item?.is_expired || item?.status === 'expired') {
    return true
  }

  const expiryDate = parseDateOnly(item?.expiry_date || item?.expiration_date)
  if (!expiryDate) {
    return false
  }

  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return expiryDate < today
}

function resolveOwnedIngredients(shoppingList, storedContext, isFallbackList) {
  if (shoppingList?.recipe_id && !isFallbackList) {
    return Array.isArray(shoppingList.owned_ingredients) ? shoppingList.owned_ingredients : []
  }

  if (storedContext?.recipeId && Number(storedContext.recipeId) === Number(shoppingList?.recipe_id)) {
    return storedContext.ownedIngredients
  }

  return []
}

function normalizeIngredientName(value) {
  return String(value || '').trim().replace(/\s+/g, ' ').toLowerCase()
}

function getIngredientDisplayKey(item) {
  const normalizedName = normalizeIngredientName(item?.name)
  if (normalizedName) {
    return `name:${normalizedName}`
  }

  if (item?.ingredient_id != null) {
    return `id:${item.ingredient_id}`
  }

  return ''
}

function dedupeIngredientsForDisplay(items) {
  const seenKeys = new Set()
  return (Array.isArray(items) ? items : []).filter((item) => {
    const key = getIngredientDisplayKey(item)
    if (!key || seenKeys.has(key)) {
      return false
    }
    seenKeys.add(key)
    return true
  })
}

function findOwnedFridgeIngredient(name, ingredientId, fridgeIngredients) {
  const normalizedName = normalizeIngredientName(name)
  return (Array.isArray(fridgeIngredients) ? fridgeIngredients : []).find((ingredient) => {
    if (isOwnedIngredientExpired(ingredient)) {
      return false
    }

    if (ingredientId != null && ingredient?.ingredient_id != null) {
      return Number(ingredient.ingredient_id) === Number(ingredientId)
    }

    return normalizedName && normalizeIngredientName(ingredient?.name) === normalizedName
  }) || null
}

function getItemSourceBadges(item, fridgeIngredients) {
  const badges = []
  ;(item?.source_refs || []).forEach((ref) => {
    const title = String(ref?.recipe_title || '').trim()
    if (ref?.type === 'recipe' && title && !badges.some((badge) => badge.label === title)) {
      badges.push({ label: title, type: 'recipe' })
    }
  })

  const hasManualSource = item?.source_type === 'manual'
    || (item?.source_refs || []).some((ref) => ref?.type === 'manual')
  if (hasManualSource && !badges.some((badge) => badge.type === 'manual')) {
    badges.push({ label: '직접 추가', type: 'manual' })
  }

  if (hasManualSource && findOwnedFridgeIngredient(item?.name, item?.ingredient_id, fridgeIngredients)) {
    badges.push({ label: '보유 재료', type: 'owned' })
  }

  return badges
}

function getRecipeTitle(shoppingList, context) {
  const sourceRecipeTitles = getSourceRecipeTitles(shoppingList)
  if (sourceRecipeTitles.length > 1) {
    return `${sourceRecipeTitles[0]} 외 ${sourceRecipeTitles.length - 1}개 레시피`
  }
  if (sourceRecipeTitles.length === 1) {
    return sourceRecipeTitles[0]
  }
  if (context?.recipeId && Number(context.recipeId) === Number(shoppingList?.recipe_id)) {
    return context.recipeTitle
  }
  if (shoppingList?.recipe_title) {
    return shoppingList.recipe_title
  }
  if (shoppingList?.recipe_id) {
    return '레시피 장보기'
  }
  return '오늘 장보기'
}

function buildFallbackShoppingList(context) {
  if (!context || !Array.isArray(context.missingIngredients) || context.missingIngredients.length === 0) {
    return null
  }

  return {
    id: null,
    recipe_id: context.recipeId,
    source: 'recipe',
    status: 'active',
    source_recipes: [{ type: 'recipe', recipe_id: context.recipeId, recipe_title: context.recipeTitle }],
    total_price: 0,
    created_at: context.createdAt,
    isFallback: true,
    items: context.missingIngredients.map((item, index) => ({
      id: `fallback-${index}`,
      ingredient_id: item.ingredient_id,
      name: item.name,
      amount: item.amount,
      provider: 'backend',
      product_id: null,
      product_name: null,
      product_link: null,
      product_image: null,
      price: null,
      mall_name: null,
      is_checked: true,
      is_purchased: false,
      source_type: 'recipe',
      source_refs: [{ type: 'recipe', recipe_id: context.recipeId, recipe_title: context.recipeTitle }],
      created_at: context.createdAt,
    })),
  }
}

function buildEmptyShoppingList() {
  return {
    id: null,
    recipe_id: null,
    source: 'manual',
    status: 'active',
    source_recipes: [],
    total_price: 0,
    created_at: new Date().toISOString(),
    items: [],
  }
}

function ShoppingLoginPrompt({ onLogin }) {
  return (
    <section className="shopping-page shopping-page--start" aria-labelledby="shopping-title">
      <div className="shopping-hero">
        <div className="shopping-hero__copy">
          <span className="shopping-eyebrow">장보기</span>
          <h1 id="shopping-title">로그인이 필요해요</h1>
          <p>장보기 내역과 냉장고 재료를 연결해 필요한 재료만 확인할 수 있어요.</p>
        </div>
        <div className="shopping-hero__art" aria-hidden="true">
          <img src={imageShop} alt="" />
        </div>
      </div>

      <button className="shopping-primary-action shopping-login-action" type="button" onClick={onLogin}>
        로그인하기
      </button>
    </section>
  )
}

function ShoppingCompletionState({ stockedCount, onViewFridge, onStartShopping }) {
  return (
    <section className="shopping-page shopping-page--completed" aria-labelledby="shopping-completion-title">
      <div className="shopping-completion-card">
        <span className="shopping-completion-card__icon" aria-hidden="true">✓</span>
        <span className="shopping-completion-card__eyebrow">냉장고 입고 완료</span>
        <h1 id="shopping-completion-title">장보기를 완료했어요</h1>
        <p>{stockedCount}개 재료를 냉장고에 입고했습니다.</p>
        <div className="shopping-completion-card__actions">
          <button type="button" className="shopping-completion-card__primary" onClick={onViewFridge}>
            냉장고에서 확인
          </button>
          <button type="button" className="shopping-completion-card__secondary" onClick={onStartShopping}>
            새 장보기 시작
          </button>
        </div>
      </div>
    </section>
  )
}

function ShoppingList() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { dialogNode, showAlert, showConfirm } = useAppDialog()
  const [storedContext] = useState(readShoppingContext)
  const [shoppingList, setShoppingList] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isMutating, setIsMutating] = useState(false)
  const [error, setError] = useState('')
  const [purchaseCompletion, setPurchaseCompletion] = useState(null)
  const [ownedProductMap, setOwnedProductMap] = useState({})
  const [isManualAddOpen, setIsManualAddOpen] = useState(false)
  const [manualSearchQuery, setManualSearchQuery] = useState('')
  const [manualSearchResults, setManualSearchResults] = useState([])
  const [isManualSearching, setIsManualSearching] = useState(false)
  const [isManualAdding, setIsManualAdding] = useState(false)
  const [ingredientSuggestions, setIngredientSuggestions] = useState([])
  const [fridgeIngredients, setFridgeIngredients] = useState([])
  const [statusFilter, setStatusFilter] = useState('all')
  const [sourceFilters, setSourceFilters] = useState([])
  const [selectedOwnedKeys, setSelectedOwnedKeys] = useState([])

  const isLoggedIn = hasShoppingAuth()
  const shoppingListId = searchParams.get('shoppingListId')
  const sourceParam = searchParams.get('source')
  const fallbackParam = searchParams.get('fallback')
  const sourceRecipeTitles = getSourceRecipeTitles(shoppingList)
  const items = shoppingList?.items ?? []
  const isFallbackList = Boolean(shoppingList?.isFallback)
  const ownedItems = dedupeIngredientsForDisplay(resolveOwnedIngredients(shoppingList, storedContext, isFallbackList))
  const ownedProductQuery = ownedItems.map((item) => item.name).filter(Boolean).join('|')
  const ownedShoppingItems = ownedItems.map((item) => ({
    ...item,
    ...(ownedProductMap[item.name] || {}),
  }))
  const activeItems = items.filter((item) => !item.is_purchased)
  const hasCurrentShoppingList = Boolean(shoppingList?.id)
  const sourceFilterOptions = buildSourceFilterOptions(shoppingList, activeItems)
  const recipeFilterOptionCount = sourceFilterOptions.filter((option) => option.type === 'recipe').length
  const sourceFilterKey = sourceFilterOptions.map((option) => option.key).join('|')

  const itemMatchesSourceKey = (item, sourceKey) => {
    const option = sourceFilterOptions.find((candidate) => candidate.key === sourceKey)
    return itemMatchesSourceOption(item, option, recipeFilterOptionCount)
  }

  const getFilteredItems = (status, sources) => {
    const selectedSources = Array.isArray(sources) ? sources : []
    let active = activeItems
    let owned = ownedShoppingItems

    if (selectedSources.length > 0) {
      active = active.filter((item) => selectedSources.some((sourceKey) => itemMatchesSourceKey(item, sourceKey)))
      const hasRecipeSource = selectedSources.some((sourceKey) => (
        sourceFilterOptions.find((option) => option.key === sourceKey)?.type === 'recipe'
      ))
      owned = hasRecipeSource ? owned : []
    }

    if (status === 'need_buy') {
      owned = []
    } else if (status === 'owned') {
      active = []
    }

    return { active, owned }
  }

  const countFilteredItems = (status, sources = sourceFilters) => {
    const filtered = getFilteredItems(status, sources)
    return filtered.active.length + filtered.owned.length
  }

  const filteredItems = getFilteredItems(statusFilter, sourceFilters)
  const visibleActiveItems = filteredItems.active
  const visibleOwnedShoppingItems = filteredItems.owned
  const selectedItems = visibleActiveItems.filter((item) => item.is_checked)
  const selectedOwnedItems = visibleOwnedShoppingItems.filter((item) => (
    selectedOwnedKeys.includes(getIngredientDisplayKey(item))
  ))
  const selectedCount = selectedItems.length + selectedOwnedItems.length
  const visibleItemCount = visibleActiveItems.length + visibleOwnedShoppingItems.length
  const selectedTotalPrice = [...selectedItems, ...selectedOwnedItems]
    .reduce((sum, item) => sum + Number(item.price || 0), 0)
  const manualOwnedIngredient = findOwnedFridgeIngredient(
    manualSearchQuery,
    null,
    fridgeIngredients,
  )

  useEffect(() => {
    let isAlive = true

    async function loadShoppingList() {
      setIsLoading(true)
      setError('')

      if (!hasShoppingAuth()) {
        setShoppingList(sourceParam === 'recipe' ? buildFallbackShoppingList(storedContext) : null)
        setIsLoading(false)
        return
      }

      try {
        if (fallbackParam === '1' || sourceParam === 'recipe') {
          const fallbackList = buildFallbackShoppingList(storedContext)
          if (fallbackList && !shoppingListId) {
            setShoppingList(fallbackList)
            return
          }
        }

        const data = shoppingListId
          ? await getShoppingList(shoppingListId)
          : await getCurrentShoppingList().then((response) => response.shopping_list)

        if (!isAlive) return

        setShoppingList(data || buildEmptyShoppingList())
      } catch (shoppingError) {
        if (!isAlive) return

        if (shoppingError.status === 401) {
          setShoppingList(null)
          return
        }

        if (!shoppingListId) {
          setShoppingList(buildEmptyShoppingList())
          return
        }

        setError(shoppingError.message || '장보기 목록을 불러오지 못했어요.')
      } finally {
        if (isAlive) {
          setIsLoading(false)
        }
      }
    }

    loadShoppingList()
    return () => {
      isAlive = false
    }
  }, [shoppingListId, sourceParam, fallbackParam, storedContext])

  // 선택한 출처 필터가 사라지면(레시피 제거 등) 해당 필터만 제외한다.
  useEffect(() => {
    setSourceFilters((prev) => {
      if (prev.length === 0) {
        return prev
      }

      const next = prev.filter((key) => sourceFilterOptions.some((option) => option.key === key))
      return next.length === prev.length ? prev : next
    })
  }, [sourceFilterKey])

  useEffect(() => {
    let isAlive = true

    async function loadOwnedProducts() {
      if (!shoppingList?.recipe_id || isFallbackList || ownedItems.length === 0 || !hasShoppingAuth()) {
        setOwnedProductMap({})
        return
      }

      const ingredientNames = [...new Set(ownedItems.map((item) => item.name).filter(Boolean))]
      if (ingredientNames.length === 0) {
        setOwnedProductMap({})
        return
      }

      try {
        const data = await compareShoppingProducts(ingredientNames)
        if (!isAlive) return

        const nextMap = {}
        ;(data.market_prices || []).forEach((row) => {
          nextMap[row.name] = row
        })
        setOwnedProductMap(nextMap)
      } catch {
        if (isAlive) {
          setOwnedProductMap({})
        }
      }
    }

    loadOwnedProducts()
    return () => {
      isAlive = false
    }
  }, [shoppingList?.recipe_id, isFallbackList, ownedProductQuery])

  // 재료명 입력 시 식재료 마스터 자동완성을 디바운스로 조회한다.
  useEffect(() => {
    const keyword = manualSearchQuery.trim()
    if (!isManualAddOpen || !keyword) {
      setIngredientSuggestions([])
      return undefined
    }

    let isAlive = true
    const timer = window.setTimeout(async () => {
      try {
        const names = await searchIngredientSuggestions(keyword)
        if (isAlive) {
          setIngredientSuggestions(Array.isArray(names) ? names : [])
        }
      } catch {
        if (isAlive) {
          setIngredientSuggestions([])
        }
      }
    }, 250)

    return () => {
      isAlive = false
      window.clearTimeout(timer)
    }
  }, [manualSearchQuery, isManualAddOpen])

  useEffect(() => {
    let isAlive = true

    async function loadFridgeIngredients() {
      if (!hasShoppingAuth()) {
        setFridgeIngredients([])
        return
      }

      try {
        const ingredients = await getFridgeIngredients()
        if (isAlive) {
          setFridgeIngredients(Array.isArray(ingredients) ? ingredients : [])
        }
      } catch {
        if (isAlive) {
          setFridgeIngredients([])
        }
      }
    }

    loadFridgeIngredients()
    return () => {
      isAlive = false
    }
  }, [isLoggedIn])

  const allChecked = visibleItemCount > 0
    && visibleActiveItems.every((item) => item.is_checked)
    && visibleOwnedShoppingItems.every((item) => selectedOwnedKeys.includes(getIngredientDisplayKey(item)))

  const updateItemChecked = async (item) => {
    if (isFallbackList) {
      setShoppingList((prev) => ({
        ...prev,
        items: prev.items.map((prevItem) => (
          prevItem.id === item.id ? { ...prevItem, is_checked: !prevItem.is_checked } : prevItem
        )),
      }))
      return
    }

    setIsMutating(true)
    try {
      const updated = await updateShoppingListItem(item.id, { is_checked: !item.is_checked })
      setShoppingList(updated)
    } catch (shoppingError) {
      await showAlert(shoppingError.message || '재료 선택 상태를 바꾸지 못했어요.', {
        title: '장보기 수정 실패',
      })
    } finally {
      setIsMutating(false)
    }
  }

  const toggleSelectAll = async () => {
    const nextChecked = !allChecked
    const targets = visibleActiveItems.filter((item) => item.is_checked !== nextChecked)
    const ownedKeys = visibleOwnedShoppingItems.map(getIngredientDisplayKey)

    setSelectedOwnedKeys((previousKeys) => {
      const nextKeys = new Set(previousKeys)
      ownedKeys.forEach((key) => {
        if (nextChecked) nextKeys.add(key)
        else nextKeys.delete(key)
      })
      return [...nextKeys]
    })

    if (targets.length === 0) return

    if (isFallbackList) {
      const targetIds = new Set(targets.map((item) => item.id))
      setShoppingList((prev) => ({
        ...prev,
        items: prev.items.map((item) => (
          targetIds.has(item.id) ? { ...item, is_checked: nextChecked } : item
        )),
      }))
      return
    }

    setIsMutating(true)
    try {
      let latest = shoppingList
      for (const item of targets) {
        latest = await updateShoppingListItem(item.id, { is_checked: nextChecked })
      }
      setShoppingList(latest)
    } catch (shoppingError) {
      await showAlert(shoppingError.message || '전체 선택 상태를 바꾸지 못했어요.', {
        title: '장보기 수정 실패',
      })
    } finally {
      setIsMutating(false)
    }
  }

  const toggleOwnedItem = (item) => {
    const itemKey = getIngredientDisplayKey(item)
    setSelectedOwnedKeys((previousKeys) => (
      previousKeys.includes(itemKey)
        ? previousKeys.filter((key) => key !== itemKey)
        : [...previousKeys, itemKey]
    ))
  }

  const removeRecipeSource = async (filter) => {
    if (isFallbackList || !shoppingList?.id || !filter.recipeId) {
      return
    }

    const confirmed = await showConfirm(`${filter.label}에서 추가된 장보기 항목을 제외할까요?`, {
      title: '이 레시피 장보기에서 제외',
      confirmText: '제외하기',
      cancelText: '취소',
    })
    if (!confirmed) {
      return
    }

    setIsMutating(true)
    try {
      const updated = await removeShoppingListRecipe(shoppingList.id, filter.recipeId)
      setShoppingList(updated)
      setSourceFilters((previousFilters) => (
        previousFilters.includes(filter.key) ? [] : previousFilters
      ))
      await showAlert(`‘${filter.label}’ 레시피를 장보기 목록에서 제외했어요.`, {
        title: '레시피 제외 완료',
      })
    } catch (shoppingError) {
      await showAlert(shoppingError.message || '레시피를 장보기 목록에서 제외하지 못했어요.', {
        title: '레시피 제외 실패',
      })
    } finally {
      setIsMutating(false)
    }
  }

  const deleteSelectedItems = async () => {
    if (selectedItems.length === 0) {
      return
    }

    const confirmed = await showConfirm(`총 ${selectedItems.length}개 삭제하시겠습니까?`, {
      title: '선택 삭제',
      confirmText: '삭제',
      cancelText: '취소',
    })
    if (!confirmed) {
      return
    }

    if (isFallbackList) {
      const selectedIds = new Set(selectedItems.map((item) => item.id))
      setShoppingList((prev) => ({
        ...prev,
        items: prev.items.filter((item) => !selectedIds.has(item.id)),
      }))
      return
    }

    setIsMutating(true)
    try {
      let latest = shoppingList
      for (const item of selectedItems) {
        latest = await deleteShoppingListItem(item.id)
      }
      setShoppingList(latest)
    } catch (shoppingError) {
      await showAlert(shoppingError.message || '선택한 재료를 삭제하지 못했어요.', {
        title: '선택 삭제 실패',
      })
    } finally {
      setIsMutating(false)
    }
  }

  const deleteWholeList = async () => {
    const confirmed = await showConfirm('이 장보기 목록을 삭제할까요? 삭제하면 되돌릴 수 없어요.', {
      title: '장보기 목록 삭제',
      confirmText: '삭제',
      cancelText: '취소',
    })
    if (!confirmed) {
      return
    }

    if (isFallbackList || !shoppingList?.id) {
      setShoppingList(null)
      navigate('/shopping-list')
      return
    }

    setIsMutating(true)
    try {
      await deleteShoppingList(shoppingList.id)
      setShoppingList(null)
      navigate('/shopping-list')
    } catch (shoppingError) {
      await showAlert(shoppingError.message || '장보기 목록을 삭제하지 못했어요.', {
        title: '목록 삭제 실패',
      })
    } finally {
      setIsMutating(false)
    }
  }

  const searchManualProducts = async (event, keywordOverride = null) => {
    event?.preventDefault()
    const query = (keywordOverride ?? manualSearchQuery).trim()
    if (!query) {
      await showAlert('검색할 재료명을 입력해 주세요.', {
        title: '장보기 재료 추가',
      })
      return
    }

    setIsManualSearching(true)
    try {
      const data = await searchShoppingProducts(query, 5)
      setManualSearchResults(data.items || [])
    } catch (shoppingError) {
      await showAlert(shoppingError.message || '상품을 검색하지 못했어요.', {
        title: '상품 검색 실패',
      })
    } finally {
      setIsManualSearching(false)
    }
  }

  const addManualIngredient = async (product = null) => {
    const query = manualSearchQuery.trim()
    const ingredientName = (product?.name || query).trim()
    if (!ingredientName) {
      await showAlert('추가할 재료명을 입력해 주세요.', {
        title: '장보기 재료 추가',
      })
      return
    }

    if (isFallbackList) {
      await showAlert('임시 장보기 화면에서는 추가한 장보기 재료를 저장할 수 없어요. 서버 연결 후 다시 시도해 주세요.', {
        title: '재료 추가 불가',
      })
      return
    }

    const ingredient = {
      name: ingredientName,
      provider: product?.provider,
      product_id: product?.product_id,
      product_name: product?.product_name,
      product_link: product?.product_link,
      product_image: product?.product_image,
      price: product?.price,
      mall_name: product?.mall_name,
    }

    setIsManualAdding(true)
    try {
      const updated = await createManualShoppingList({ ingredients: [ingredient] })
      setShoppingList(updated)
      setManualSearchQuery('')
      setManualSearchResults([])
      setIsManualAddOpen(false)
      await showAlert(`${ingredientName}을(를) 장보기 목록에 추가했어요.`, {
        title: '재료 추가 완료',
      })
    } catch (shoppingError) {
      await showAlert(shoppingError.message || '재료를 장보기 목록에 추가하지 못했어요.', {
        title: '재료 추가 실패',
      })
    } finally {
      setIsManualAdding(false)
    }
  }

  const completePurchase = async () => {
    if (isFallbackList) {
      await showAlert('임시 장보기 화면에서는 냉장고 입고 처리를 할 수 없어요. 백엔드 연결 후 장보기 목록을 다시 생성해 주세요.', {
        title: '입고 처리 불가',
      })
      return
    }

    if (!shoppingList?.id || selectedCount === 0) {
      await showAlert('입고 처리할 선택 재료가 없어요.', {
        title: '구매 완료',
      })
      return
    }

    const confirmed = await showConfirm(`총 ${selectedCount}개 재료를 냉장고에 입고하시겠습니까?`, {
      title: '냉장고 입고',
      confirmText: '입고하기',
      cancelText: '취소',
    })
    if (!confirmed) {
      return
    }

    setIsMutating(true)
    try {
      const result = await completeShoppingPurchase({
        shopping_list_id: shoppingList.id,
        item_ids: selectedItems.map((item) => item.id),
        owned_ingredients: selectedOwnedItems.map((item) => ({
          name: item.name,
          amount: item.amount || null,
          ingredient_id: item.ingredient_id || null,
          fridge_ingredient_name: item.fridge_ingredient_name || null,
        })),
      })

      setSelectedOwnedKeys([])

      if (!result.shopping_list) {
        // 모든 재료가 입고되어 현재 장보기에서 빠지는 경우에도 장보기 화면에 머문다.
        setPurchaseCompletion({ stockedCount: Number(result.stocked_count || selectedCount) })
        setShoppingList(null)
        navigate('/shopping-list', { replace: true })
        return
      }

      setShoppingList(result.shopping_list)
      await showAlert(result.message || '구매한 재료를 냉장고에 입고했어요.', {
        title: '냉장고 입고 완료',
      })
    } catch (shoppingError) {
      await showAlert(shoppingError.message || '구매 완료 처리를 하지 못했어요.', {
        title: '구매 완료 실패',
      })
    } finally {
      setIsMutating(false)
    }
  }

  if (purchaseCompletion) {
    return (
      <>
        <ShoppingCompletionState
          stockedCount={purchaseCompletion.stockedCount}
          onViewFridge={() => navigate('/fridge')}
          onStartShopping={() => navigate('/recipes')}
        />
        {dialogNode}
      </>
    )
  }

  if (isLoading) {
    return (
      <section className="shopping-page" aria-busy="true">
        <p className="shopping-status">장보기 정보를 불러오는 중이에요.</p>
        {dialogNode}
      </section>
    )
  }

  if (error) {
    return (
      <section className="shopping-page">
        <p className="shopping-status shopping-status--error">{error}</p>
        <button className="shopping-primary-action" type="button" onClick={() => navigate('/recipes')}>
          레시피 먼저 확인하기
        </button>
        {dialogNode}
      </section>
    )
  }

  if (!shoppingList) {
    return (
      <>
        <ShoppingLoginPrompt onLogin={() => navigate('/login')} />
        {dialogNode}
      </>
    )
  }

  return (
    <section className="shopping-page" aria-labelledby="shopping-title">
      <div className="shopping-hero">
        <div className="shopping-hero__copy">
          <span className="shopping-eyebrow">장보기</span>
          <h1 id="shopping-title">지금 사야 할 재료</h1>
          <p>
            냉장고에 있는 재료와 부족한 재료를 함께 보고, 필요한 재료는 구매 링크로 바로 확인해요.
          </p>
        </div>
        <div className="shopping-hero__art" aria-hidden="true">
          <img src={imageShop} alt="" />
        </div>
      </div>

      <div className="shopping-main-grid shopping-main-grid--recipe">
        <section className="shopping-panel shopping-list-panel" aria-labelledby="shopping-list-title">
          <div className="shopping-list-toolbar">
            <div className="shopping-list-toolbar__title">
              <h2 id="shopping-list-title">현재 장보기 목록</h2>
              <span className="shopping-count-badge">{visibleItemCount}개</span>
            </div>
            <div className="shopping-list-toolbar__actions">
              <button
                type="button"
                className="shopping-manual-toggle"
                onClick={() => setIsManualAddOpen((prev) => !prev)}
                disabled={isMutating || isFallbackList}
              >
                + 장보기 재료 추가
              </button>
              <button
                type="button"
                className={`shopping-select-all ${allChecked ? 'is-active' : ''}`}
                onClick={toggleSelectAll}
                disabled={isMutating || visibleItemCount === 0}
                aria-label={selectedCount > 0 ? `${selectedCount}개 선택됨` : '전체 선택'}
              >
                <span className={`shopping-check ${allChecked ? 'is-checked' : ''}`} aria-hidden="true" />
                {selectedCount > 0 ? <em>{selectedCount}개 선택됨</em> : '전체 선택'}
              </button>
            </div>
          </div>

          <div className="shopping-filter-groups" aria-label="장보기 목록 필터">
            <div className="shopping-filter-group" role="group" aria-label="재료 상태">
              <span>상태</span>
              <div className="shopping-filter-group__options">
                {SHOPPING_STATUS_FILTERS.map((filter) => (
                  <button
                    type="button"
                    key={filter.key}
                    className={statusFilter === filter.key ? 'is-active' : ''}
                    aria-pressed={statusFilter === filter.key}
                    onClick={() => setStatusFilter(filter.key)}
                  >
                    {filter.label} <em>{countFilteredItems(filter.key)}</em>
                  </button>
                ))}
              </div>
            </div>

            {sourceFilterOptions.length > 0 ? (
              <div className="shopping-filter-group shopping-filter-group--source" role="group" aria-label="재료 출처">
                <span title="같은 재료가 여러 레시피에 포함되면 출처별 개수는 중복될 수 있어요.">출처</span>
                <div className="shopping-filter-group__options">
                  <button
                    type="button"
                    className={sourceFilters.length === 0 ? 'is-active' : ''}
                    aria-pressed={sourceFilters.length === 0}
                    onClick={() => setSourceFilters([])}
                  >
                    전체 <em>{countFilteredItems(statusFilter, [])}</em>
                  </button>
                  {sourceFilterOptions.map((filter) => {
                    const isActive = sourceFilters.includes(filter.key)

                    if (filter.type === 'recipe') {
                      return (
                        <div
                          className={`shopping-filter-recipe-option ${isActive ? 'is-active' : ''}`}
                          key={filter.key}
                        >
                          <button
                            type="button"
                            className="shopping-filter-recipe-select"
                            aria-pressed={isActive}
                            onClick={() => setSourceFilters([filter.key])}
                          >
                            {filter.label} <em>{countFilteredItems(statusFilter, [filter.key])}</em>
                          </button>
                          <button
                            type="button"
                            className="shopping-filter-recipe-remove"
                            aria-label={`${filter.label} 장보기에서 제외`}
                            title="이 레시피 장보기에서 제외"
                            disabled={isMutating || isFallbackList || !filter.recipeId}
                            onClick={() => removeRecipeSource(filter)}
                          >
                            <span aria-hidden="true">×</span>
                          </button>
                        </div>
                      )
                    }

                    return (
                      <button
                        type="button"
                        key={filter.key}
                        className={isActive ? 'is-active' : ''}
                        aria-pressed={isActive}
                        onClick={() => setSourceFilters([filter.key])}
                      >
                        {filter.label} <em>{countFilteredItems(statusFilter, [filter.key])}</em>
                      </button>
                    )
                  })}
                </div>
              </div>
            ) : null}
          </div>

          {isManualAddOpen ? (
            <div className="shopping-manual-panel">
              <form className="shopping-manual-search" onSubmit={searchManualProducts}>
                <label htmlFor="shopping-manual-search-input">장보기 재료 추가</label>
                <div className="shopping-manual-search__row">
                  <div className="shopping-manual-search__field">
                    <svg
                      className="shopping-manual-search__icon"
                      viewBox="0 0 20 20"
                      aria-hidden="true"
                      focusable="false"
                    >
                      <circle cx="9" cy="9" r="5.5" fill="none" stroke="currentColor" strokeWidth="1.8" />
                      <line x1="13.2" y1="13.2" x2="17" y2="17" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
                    </svg>
                    <input
                      id="shopping-manual-search-input"
                      type="search"
                      value={manualSearchQuery}
                      onChange={(event) => {
                        setManualSearchQuery(event.target.value)
                        setManualSearchResults([])
                      }}
                      placeholder="추가할 재료명 입력 (ex.우유, 양파)"
                      disabled={isManualSearching || isManualAdding}
                      autoComplete="off"
                    />
                  </div>
                  <button type="submit" disabled={isManualSearching || isManualAdding}>
                    {isManualSearching ? '검색 중' : '검색'}
                  </button>
                </div>
              </form>

              {manualOwnedIngredient ? (
                <p className="shopping-owned-search-hint" role="status">
                  ✓ 이미 냉장고에 보유 중인 재료예요.
                </p>
              ) : null}

              {manualSearchQuery.trim() ? (
                <div className="shopping-suggest">
                  <p className="shopping-suggest__head">식재료 검색 결과</p>
                  {ingredientSuggestions.map((name) => (
                    <button
                      className="shopping-suggest__item"
                      type="button"
                      key={name}
                      disabled={isManualSearching || isManualAdding}
                      onClick={() => {
                        setManualSearchQuery(name)
                        setIngredientSuggestions([])
                        searchManualProducts(null, name)
                      }}
                    >
                      {name}
                    </button>
                  ))}
                  <button
                    className="shopping-suggest__item shopping-suggest__item--custom"
                    type="button"
                    disabled={isManualAdding}
                    onClick={() => addManualIngredient(null)}
                  >
                    ‘{manualSearchQuery.trim()}’를 목록에 없는 재료로 직접 추가
                  </button>
                </div>
              ) : null}

              {manualSearchResults.length > 0 ? (
                <div className="shopping-manual-results">
                  {manualSearchResults.map((product) => (
                    <div className="shopping-manual-result" key={`${product.product_id || product.product_link || product.product_name}`}>
                      <ImageSlot className="shopping-manual-result__image" src={product.product_image} alt={product.product_name || product.name} />
                      <div className="shopping-manual-result__info">
                        <strong>{product.product_name || product.name}</strong>
                        <span>{product.mall_name || product.provider || 'provider'} · {formatPrice(product.price)}</span>
                      </div>
                      <button
                        type="button"
                        onClick={() => addManualIngredient(product)}
                        disabled={isManualAdding}
                      >
                        담기
                      </button>
                    </div>
                  ))}
                </div>
              ) : manualSearchQuery.trim() ? (
                <p className="shopping-manual-empty">검색 결과에서 고르거나 재료명만 바로 추가할 수 있어요.</p>
              ) : null}

              <button
                className="shopping-manual-plain-add"
                type="button"
                onClick={() => addManualIngredient(null)}
                disabled={isManualAdding || !manualSearchQuery.trim()}
              >
                재료명만 장보기 목록에 추가
              </button>
            </div>
          ) : null}

          <div className="shopping-item-rows">
            {visibleItemCount === 0 ? (
              <div className="shopping-empty-block">
                <p className="shopping-empty-note">
                  {sourceFilters.length > 0
                    ? '선택한 출처 기준으로 표시할 장보기 재료가 없어요.'
                    : statusFilter === 'owned'
                      ? '현재 냉장고에 보유 중인 레시피 재료가 없어요.'
                    : ownedItems.length > 0 && statusFilter !== 'need_buy'
                    ? '따로 구매할 재료가 없어요. 필요한 재료는 이미 냉장고에 있어요.'
                    : hasCurrentShoppingList
                      ? '구매가 필요한 재료를 모두 냉장고에 입고했어요.'
                      : '아직 장보기 목록에 담긴 재료가 없어요.'}
                </p>
                {hasCurrentShoppingList ? (
                  <button
                    className="shopping-delete-list-button"
                    type="button"
                    disabled={isMutating}
                    onClick={deleteWholeList}
                  >
                    이 장보기 목록 삭제
                  </button>
                ) : null}
              </div>
            ) : (
              visibleActiveItems.map((item) => {
                const sourceBadges = getItemSourceBadges(item, fridgeIngredients)
                return (
                <div className="shopping-item-row" key={item.id}>
                  <button
                    className={`shopping-check ${item.is_checked ? 'is-checked' : ''}`}
                    type="button"
                    aria-label={`${item.name} 구매 대상 ${item.is_checked ? '해제' : '선택'}`}
                    disabled={isMutating}
                    onClick={() => updateItemChecked(item)}
                  />
                  <ImageSlot className="shopping-item-row__image" src={item.product_image} alt={item.product_name || item.name} />
                  <div className="shopping-item-row__info">
                    <div className="shopping-item-row__title">
                      <strong>{item.name}<span>· {formatQuantity(item)}</span></strong>
                      {sourceBadges.map((badge) => (
                        <span key={badge.label} className={`shopping-source-badge is-${badge.type}`}>
                          {badge.label}
                        </span>
                      ))}
                    </div>
                    <small>{item.product_name || '상품 검색 결과 없음'}</small>
                  </div>
                  <div className="shopping-item-row__meta">
                    <span>{item.mall_name || item.provider || 'provider'}</span>
                    <strong>{formatPrice(item.price)}</strong>
                  </div>
                  {item.product_link ? (
                    <a
                      className="shopping-item-row__link"
                      href={item.product_link}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      구매 링크
                    </a>
                  ) : (
                    <span className="shopping-item-row__link is-disabled">링크 없음</span>
                  )}
                </div>
                )
              })
            )}

            {visibleOwnedShoppingItems.map((item, index) => {
              const isSelected = selectedOwnedKeys.includes(getIngredientDisplayKey(item))
              return (
                <div className="shopping-item-row shopping-item-row--owned" key={`owned-${item.name}-${index}`}>
                  <button
                    type="button"
                    className={`shopping-owned-check ${isSelected ? 'is-selected' : ''}`}
                    aria-label={`${item.name} 입고 대상 ${isSelected ? '해제' : '선택'}`}
                    aria-pressed={isSelected}
                    disabled={isMutating || isFallbackList}
                    onClick={() => toggleOwnedItem(item)}
                  />
                  <ImageSlot className="shopping-item-row__image" src={item.product_image} alt={item.product_name || item.name} />
                  <div className="shopping-item-row__info">
                    <div className="shopping-item-row__title">
                      <strong>{item.name}{item.amount ? <span>· {item.amount}</span> : null}</strong>
                      <span className="shopping-owned-badge">보유 재료</span>
                      {isOwnedIngredientExpired(item) ? (
                        <span className="shopping-expired-badge">소비기한 지남</span>
                      ) : null}
                    </div>
                    <small>{item.product_name || '상품 검색 결과 없음'}</small>
                  </div>
                  <div className="shopping-item-row__meta">
                    <span>{item.mall_name || item.provider || 'provider'}</span>
                    <strong>{formatPrice(item.price)}</strong>
                  </div>
                  {item.product_link ? (
                    <a
                      className="shopping-item-row__link"
                      href={item.product_link}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      구매 링크
                    </a>
                  ) : (
                    <span className="shopping-item-row__link is-disabled">링크 없음</span>
                  )}
                </div>
              )
            })}
          </div>
        </section>

        <aside className="shopping-sidebar" aria-label="장보기 요약 및 액션">
          <div className="shopping-sidebar__card shopping-summary-box">
            {isFallbackList ? (
              <p className="shopping-sidebar__note shopping-sidebar__note--warn">
                서버 연결 실패로 부족 재료만 임시 표시 중이라 입고 처리가 제한돼요.
              </p>
            ) : null}
            <dl className="shopping-metric-list">
              <div>
                <dt>구매 필요</dt>
                <dd>{visibleActiveItems.length}개</dd>
              </div>
              <div>
                <dt>보유 재료</dt>
                <dd>{visibleOwnedShoppingItems.length}개</dd>
              </div>
              <div className="shopping-metric-list__total">
                <dt>예상 금액 <span>선택 {selectedCount}개</span></dt>
                <dd>{formatPrice(selectedTotalPrice)}</dd>
              </div>
            </dl>
            <button
              className="shopping-sidebar__primary"
              type="button"
              disabled={isMutating || selectedCount === 0}
              onClick={completePurchase}
            >
              선택 {selectedCount}개 냉장고 입고
            </button>
            <button
              className="shopping-sidebar__danger"
              type="button"
              disabled={isMutating || selectedItems.length === 0}
              onClick={deleteSelectedItems}
            >
              선택 {selectedItems.length}개 삭제
            </button>
          </div>

          <button
            className="shopping-sidebar__back"
            type="button"
            onClick={() => navigate(shoppingList.recipe_id && sourceRecipeTitles.length <= 1 ? `/recipes/${shoppingList.recipe_id}` : '/recipes')}
          >
            ← 레시피 상세로 돌아가기
          </button>
        </aside>
      </div>
      {dialogNode}
    </section>
  )
}

export default ShoppingList
