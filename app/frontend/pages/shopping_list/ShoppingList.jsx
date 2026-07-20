import React, { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import './ShoppingList.css'

import imageShop from '../../assets/extracted/images/image_shop.png'
import { useAppDialog } from '../../components/AppDialog.jsx'
import {
  compareShoppingProducts,
  completeShoppingPurchase,
  createManualShoppingList,
  deleteShoppingList,
  deleteShoppingListItem,
  getCurrentShoppingList,
  getShoppingList,
  hasShoppingAuth,
  searchIngredientSuggestions,
  searchShoppingProducts,
  updateShoppingListItem,
} from '../../services/shoppingApi.js'

const SHOPPING_CONTEXT_KEY = 'bobbeori-recipe-shopping-context'
const SHOPPING_STATUS_FILTERS = [
  { key: 'all', label: '전체' },
  { key: 'need_buy', label: '구매 필요' },
]
const RECIPE_FILTER_PREFIX = 'recipe:'

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

function getSourceRecipeTitles(list) {
  const titles = []
  ;(list?.source_recipes || []).forEach((recipe) => {
    const title = String(recipe?.recipe_title || '').trim()
    if (title && !titles.includes(title)) {
      titles.push(title)
    }
  })

  ;(list?.items || []).forEach((item) => {
    ;(item.source_refs || []).forEach((ref) => {
      const title = String(ref?.recipe_title || '').trim()
      if (ref?.type === 'recipe' && title && !titles.includes(title)) {
        titles.push(title)
      }
    })
  })

  return titles
}

function getItemSourceBadges(item) {
  const badges = []
  ;(item?.source_refs || []).forEach((ref) => {
    const title = String(ref?.recipe_title || '').trim()
    if (ref?.type === 'recipe' && title && !badges.some((badge) => badge.label === title)) {
      badges.push({ label: title, type: 'recipe' })
    }
  })

  if (badges.length === 0 && item?.source_type === 'manual') {
    badges.push({ label: '직접 추가', type: 'manual' })
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

function ShoppingList() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { dialogNode, showAlert, showConfirm } = useAppDialog()
  const [storedContext] = useState(readShoppingContext)
  const [shoppingList, setShoppingList] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isMutating, setIsMutating] = useState(false)
  const [error, setError] = useState('')
  const [ownedProductMap, setOwnedProductMap] = useState({})
  const [isManualAddOpen, setIsManualAddOpen] = useState(false)
  const [manualSearchQuery, setManualSearchQuery] = useState('')
  const [manualSearchResults, setManualSearchResults] = useState([])
  const [isManualSearching, setIsManualSearching] = useState(false)
  const [isManualAdding, setIsManualAdding] = useState(false)
  const [ingredientSuggestions, setIngredientSuggestions] = useState([])
  const [statusFilter, setStatusFilter] = useState('all')
  const [sourceFilters, setSourceFilters] = useState([])

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
  const recipeFilterOptions = getSourceRecipeTitles(shoppingList)
  const hasCurrentShoppingList = Boolean(shoppingList?.id)
  const hasManualItems = activeItems.some((item) => item.source_type === 'manual')
  const sourceFilterOptions = [
    ...recipeFilterOptions.map((title) => ({ key: `${RECIPE_FILTER_PREFIX}${title}`, label: title })),
    ...(hasManualItems ? [{ key: 'manual', label: '직접 추가' }] : []),
  ]
  const sourceFilterKey = sourceFilterOptions.map((option) => option.key).join('|')

  const itemMatchesSourceKey = (item, sourceKey) => {
    if (sourceKey === 'manual') {
      return item.source_type === 'manual'
    }

    if (sourceKey.startsWith(RECIPE_FILTER_PREFIX)) {
      const title = sourceKey.slice(RECIPE_FILTER_PREFIX.length)
      return (item.source_refs || []).some((ref) => (
        ref?.type === 'recipe' && String(ref?.recipe_title || '').trim() === title
      ))
    }

    return true
  }

  // 상태 축(단일)과 출처 축(다중 OR)을 함께 적용해, 칩 개수와 실제 표시 행이 항상 일치하게 한다.
  const getFilteredItems = (status, sources) => {
    const sourceKeys = Array.isArray(sources) ? sources : []
    let active = activeItems
    let owned = ownedShoppingItems

    if (sourceKeys.length > 0) {
      active = active.filter((item) => sourceKeys.some((key) => itemMatchesSourceKey(item, key)))
      // 보유 재료는 레시피 맥락에서만 의미가 있어, 레시피 출처가 하나도 선택되지 않으면 감춘다.
      if (!sourceKeys.some((key) => key.startsWith(RECIPE_FILTER_PREFIX))) {
        owned = []
      }
    }

    if (status === 'need_buy') {
      owned = []
    }

    return { active, owned }
  }

  const countFilteredItems = (status, sources) => {
    const filtered = getFilteredItems(status, sources)
    return filtered.active.length + filtered.owned.length
  }

  const filteredItems = getFilteredItems(statusFilter, sourceFilters)
  const visibleActiveItems = filteredItems.active
  const visibleOwnedShoppingItems = filteredItems.owned
  const selectedItems = visibleActiveItems.filter((item) => item.is_checked)
  const visibleItemCount = visibleActiveItems.length + visibleOwnedShoppingItems.length
  // 예상 금액은 백엔드 합계가 아니라 화면에서 선택된 재료 기준으로 계산한다.
  const selectedTotalPrice = selectedItems.reduce((sum, item) => sum + (item.price || 0), 0)

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

  // 선택한 출처가 사라지면(레시피 제거 등) 그 출처만 선택 목록에서 뺀다.
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

  const allChecked = visibleActiveItems.length > 0 && visibleActiveItems.every((item) => item.is_checked)

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
    if (targets.length === 0) {
      return
    }

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

    if (!shoppingList?.id || selectedItems.length === 0) {
      await showAlert('입고 처리할 선택 재료가 없어요.', {
        title: '구매 완료',
      })
      return
    }

    const confirmed = await showConfirm(`총 ${selectedItems.length}개 재료를 냉장고에 입고하시겠습니까?`, {
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
      })

      if (!result.shopping_list) {
        // 모든 재료가 입고되어 현재 장보기에서 빠지는 경우
        setShoppingList(null)
        navigate('/shopping-list')
        await showAlert(result.message || '구매한 재료를 냉장고에 입고하고 장보기를 완료했어요.', {
          title: '냉장고 입고 완료',
        })
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
                disabled={isMutating || visibleActiveItems.length === 0}
              >
                <span className={`shopping-check ${allChecked ? 'is-checked' : ''}`} aria-hidden="true" />
                전체 선택
                {selectedItems.length > 0 ? <em>{selectedItems.length}개 선택됨</em> : null}
              </button>
            </div>
          </div>

          <div className="shopping-filter-bar" aria-label="장보기 목록 필터">
            {/* 상태는 단일 선택이라 앱 공통 트랙형 세그먼트를 그대로 쓴다. */}
            <div className="shopping-choice-group" role="group" aria-label="상태">
              <span>상태</span>
              <div className="shopping-choice-group__options">
                {SHOPPING_STATUS_FILTERS.map((filter) => (
                  <button
                    type="button"
                    key={filter.key}
                    className={statusFilter === filter.key ? 'is-active' : ''}
                    aria-pressed={statusFilter === filter.key}
                    onClick={() => setStatusFilter(filter.key)}
                  >
                    {filter.label} <em>{countFilteredItems(filter.key, sourceFilters)}</em>
                  </button>
                ))}
              </div>
            </div>

            {/* 출처는 다중 선택이라 트랙 대신 체크형 칩으로 구분한다. */}
            {sourceFilterOptions.length > 0 ? (
              <div className="shopping-choice-group" role="group" aria-label="출처">
                <span>출처 <small>여러 개 선택 가능</small></span>
                <div className="shopping-source-chips">
                  {sourceFilterOptions.map((filter) => {
                    const isActive = sourceFilters.includes(filter.key)
                    return (
                      <button
                        type="button"
                        key={filter.key}
                        className={`shopping-source-chip ${isActive ? 'is-active' : ''}`}
                        aria-pressed={isActive}
                        onClick={() => setSourceFilters((prev) => (
                          prev.includes(filter.key)
                            ? prev.filter((key) => key !== filter.key)
                            : [...prev, filter.key]
                        ))}
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
                      onChange={(event) => setManualSearchQuery(event.target.value)}
                      placeholder="추가할 재료명 입력 (ex.우유, 계란)"
                      disabled={isManualSearching || isManualAdding}
                      autoComplete="off"
                    />
                  </div>
                  <button type="submit" disabled={isManualSearching || isManualAdding}>
                    {isManualSearching ? '검색 중' : '검색'}
                  </button>
                </div>
              </form>

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
                const sourceBadges = getItemSourceBadges(item)
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

            {visibleOwnedShoppingItems.map((item, index) => (
              <div className="shopping-item-row shopping-item-row--owned" key={`owned-${item.name}-${index}`}>
                <span className="shopping-owned-check" aria-hidden="true" />
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
            ))}
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
                <dt>예상 금액 <span>선택 {selectedItems.length}개</span></dt>
                <dd>{formatPrice(selectedTotalPrice)}</dd>
              </div>
            </dl>
            <button
              className="shopping-sidebar__primary"
              type="button"
              disabled={isMutating || selectedItems.length === 0}
              onClick={completePurchase}
            >
              선택 {selectedItems.length}개 냉장고 입고
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
