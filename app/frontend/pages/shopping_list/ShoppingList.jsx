import React, { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import './ShoppingList.css'

import imageShop from '../../assets/extracted/images/image_shop.png'
import { useAppDialog } from '../../components/AppDialog.jsx'
import {
  compareShoppingProducts,
  completeShoppingPurchase,
  deleteShoppingList,
  deleteShoppingListItem,
  getCurrentShoppingList,
  getShoppingHistory,
  getShoppingList,
  hasShoppingAuth,
  updateShoppingListItem,
} from '../../services/shoppingApi.js'

const SHOPPING_CONTEXT_KEY = 'bobbeori-recipe-shopping-context'

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

function getRecipeTitle(shoppingList, context) {
  if (context?.recipeId && Number(context.recipeId) === Number(shoppingList?.recipe_id)) {
    return context.recipeTitle
  }
  if (shoppingList?.recipe_title) {
    return shoppingList.recipe_title
  }
  if (shoppingList?.recipe_id) {
    return '레시피 장보기'
  }
  return '최근 장보기'
}

function getShoppingListTitle(list) {
  if (list.recipe_title) {
    return `${list.recipe_title} 장보기`
  }
  if (list.recipe_id) {
    return '레시피 장보기'
  }
  return '직접 장보기'
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
      created_at: context.createdAt,
    })),
  }
}

function getShoppingStatusLabel(list) {
  if (list.status === 'completed') {
    return '완료'
  }
  return '진행 중'
}

function getRemainingItemCount(list) {
  return (list.items || []).filter((item) => !item.is_purchased).length
}

function getShoppingHistoryGroupKey(list) {
  if (list?.recipe_id != null) {
    return `recipe:${list.recipe_id}`
  }

  if (list?.source === 'recipe' && list?.recipe_title) {
    return `recipe-title:${list.recipe_title.trim()}`
  }

  return `list:${list?.id ?? list?.created_at ?? 'unknown'}`
}

function mergeRecentWithHistory(recentList, historyLists) {
  const normalizedHistory = Array.isArray(historyLists) ? historyLists : []
  const mergedLists = recentList ? [recentList, ...normalizedHistory] : normalizedHistory
  const seenKeys = new Set()

  return mergedLists.filter((list) => {
    const groupKey = getShoppingHistoryGroupKey(list)
    if (seenKeys.has(groupKey)) {
      return false
    }
    seenKeys.add(groupKey)
    return true
  })
}

function ShoppingStart({ isLoggedIn, recentList, historyCount, notice, onContinue, onHistoryBrowse, onRecipeBrowse, onLogin }) {
  return (
    <section className="shopping-page shopping-page--start" aria-labelledby="shopping-title">
      <div className="shopping-hero">
        <div className="shopping-hero__copy">
          <span className="shopping-eyebrow">장보기 시작</span>
          <h1 id="shopping-title">무엇을 기준으로 장볼까요?</h1>
          <p>
            레시피에서 부족한 재료를 바로 확인하거나, 최근 장보기 목록을 이어서 볼 수 있어요.
          </p>
        </div>
        <div className="shopping-hero__art" aria-hidden="true">
          <img src={imageShop} alt="" />
        </div>
      </div>

      {notice ? (
        <p className="shopping-start-notice" role="status">
          {notice}
        </p>
      ) : null}

      <div className="shopping-start-grid">
        {recentList ? (
          <article className="shopping-start-card is-featured">
            <span>최근 장바구니</span>
            <h2>이어서 장보기</h2>
            <p>
              아직 담아둔 재료 {recentList.items.filter((item) => !item.is_purchased).length}개가 있어요
              {' '}
              <span className="shopping-start-card__meta">({formatCreatedAt(recentList.created_at)} 기준)</span>
            </p>
            <button className="shopping-primary-action" type="button" onClick={onContinue}>
              이어서 장보기
            </button>
          </article>
        ) : null}

        <article className="shopping-start-card">
          <span>장보기 기록</span>
          <h2>지난 장보기 내역</h2>
          <p>
            완료했거나 예전에 만든 장보기 목록을 확인해요.
            {historyCount > 0 ? ` 최근 내역 ${historyCount}개가 있어요.` : ''}
          </p>
          <button className="shopping-soft-action" type="button" onClick={isLoggedIn ? onHistoryBrowse : onLogin}>
            {isLoggedIn ? '내역 보기' : '로그인하고 보기'}
          </button>
        </article>

        <article className="shopping-start-card">
          <span>{isLoggedIn ? '준비 중' : '로그인 필요'}</span>
          <h2>냉장고 보충 장보기</h2>
          <p>자주 쓰는 재료, 곧 떨어지는 재료, 유통기한 임박 재료를 기준으로 추천하는 흐름입니다.</p>
          <button className="shopping-soft-action" type="button" onClick={isLoggedIn ? onRecipeBrowse : onLogin}>
            {isLoggedIn ? '지금은 레시피에서 시작하기' : '로그인하고 시작하기'}
          </button>
        </article>
      </div>
    </section>
  )
}

function ShoppingHistory({ lists, recentListId, isDeleting, onOpenList, onDeleteSelected, onBackToStart }) {
  const [selectedListIds, setSelectedListIds] = useState([])
  const selectedCount = selectedListIds.length
  const allSelected = lists.length > 0 && selectedCount === lists.length

  useEffect(() => {
    const validIds = new Set(lists.map((list) => Number(list.id)))
    setSelectedListIds((prev) => prev.filter((id) => validIds.has(Number(id))))
  }, [lists])

  const toggleHistorySelect = (listId) => {
    const normalizedId = Number(listId)
    setSelectedListIds((prev) => (
      prev.some((id) => Number(id) === normalizedId)
        ? prev.filter((id) => Number(id) !== normalizedId)
        : [...prev, listId]
    ))
  }

  const toggleAllHistory = () => {
    setSelectedListIds(allSelected ? [] : lists.map((list) => list.id))
  }

  const handleHistoryCardKeyDown = (event, listId) => {
    if (event.key !== 'Enter' && event.key !== ' ') {
      return
    }

    event.preventDefault()
    toggleHistorySelect(listId)
  }

  const deleteSelectedHistory = async () => {
    if (selectedCount === 0) {
      return
    }

    const deleted = await onDeleteSelected(selectedListIds)
    if (deleted) {
      setSelectedListIds([])
    }
  }

  return (
    <section className="shopping-page shopping-page--history" aria-labelledby="shopping-history-title">
      <div className="shopping-hero shopping-hero--compact">
        <div className="shopping-hero__copy">
          <span className="shopping-eyebrow">장보기 기록</span>
          <h1 id="shopping-history-title">지난 장보기 내역</h1>
          <p>최근 장바구니와 이전에 만들었던 장보기 목록을 함께 확인해요.</p>
        </div>
        <div className="shopping-hero__art" aria-hidden="true">
          <img src={imageShop} alt="" />
        </div>
      </div>

      <section className="shopping-panel shopping-history-panel" aria-label="지난 장보기 목록">
        <div className="shopping-list-toolbar">
          <div className="shopping-list-toolbar__title">
            <h2>내역 목록</h2>
            <span className="shopping-count-badge">{lists.length}개</span>
          </div>
          <div className="shopping-history-toolbar-actions">
            <button className="shopping-soft-button" type="button" onClick={toggleAllHistory} disabled={isDeleting || lists.length === 0}>
              {allSelected ? '전체 해제' : '전체 선택'}
            </button>
            <button className="shopping-delete-list-button" type="button" onClick={deleteSelectedHistory} disabled={isDeleting || selectedCount === 0}>
              선택 {selectedCount}개 삭제
            </button>
            <button className="shopping-soft-button" type="button" onClick={onBackToStart}>
              장보기 홈
            </button>
          </div>
        </div>

        {lists.length === 0 ? (
          <p className="shopping-empty-note">아직 이전 장보기 내역이 없어요.</p>
        ) : (
          <div className="shopping-history-list">
            {lists.map((list) => {
              const remainingCount = getRemainingItemCount(list)
              const itemPreview = (list.items || []).slice(0, 4).map((item) => item.name).join(', ')
              const isRecentShopping = recentListId != null && Number(list.id) === Number(recentListId)
              const isSelected = selectedListIds.some((id) => Number(id) === Number(list.id))

              return (
                <article
                  className={`shopping-history-card ${isRecentShopping ? 'is-recent' : ''} ${isSelected ? 'is-selected' : ''}`}
                  key={list.id}
                  role="checkbox"
                  aria-checked={isSelected}
                  tabIndex={0}
                  onClick={() => toggleHistorySelect(list.id)}
                  onKeyDown={(event) => handleHistoryCardKeyDown(event, list.id)}
                >
                  <span
                    className={`shopping-check shopping-history-select ${isSelected ? 'is-checked' : ''}`}
                    aria-hidden="true"
                  />
                  <div>
                    <span className={`shopping-history-status ${list.status === 'completed' ? 'is-completed' : ''} ${isRecentShopping ? 'is-recent' : ''}`}>
                      {isRecentShopping ? '최근 장바구니' : getShoppingStatusLabel(list)}
                    </span>
                    <h3>{getShoppingListTitle(list)}</h3>
                    <p>{itemPreview || '재료 정보 없음'}</p>
                    <small>
                      {formatCreatedAt(list.created_at)} · 남은 재료 {remainingCount}개 · 전체 {(list.items || []).length}개
                    </small>
                  </div>
                  <button
                    className="shopping-soft-button"
                    type="button"
                    onClick={(event) => {
                      event.stopPropagation()
                      onOpenList(list.id)
                    }}
                  >
                    상세 보기
                  </button>
                </article>
              )
            })}
          </div>
        )}
      </section>
    </section>
  )
}

function ShoppingList() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { dialogNode, showAlert, showConfirm } = useAppDialog()
  const [storedContext] = useState(readShoppingContext)
  const [shoppingList, setShoppingList] = useState(null)
  const [recentList, setRecentList] = useState(null)
  const [historyLists, setHistoryLists] = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [isMutating, setIsMutating] = useState(false)
  const [error, setError] = useState('')
  const [startNotice, setStartNotice] = useState('')
  const [ownedProductMap, setOwnedProductMap] = useState({})

  const isLoggedIn = hasShoppingAuth()
  const shoppingListId = searchParams.get('shoppingListId')
  const isHistoryView = searchParams.get('view') === 'history'
  const recipeTitle = getRecipeTitle(shoppingList, storedContext)
  const items = shoppingList?.items ?? []
  const isFallbackList = Boolean(shoppingList?.isFallback)
  const selectedItems = items.filter((item) => item.is_checked && !item.is_purchased)
  const ownedItems = dedupeIngredientsForDisplay(resolveOwnedIngredients(shoppingList, storedContext, isFallbackList))
  const ownedProductQuery = ownedItems.map((item) => item.name).filter(Boolean).join('|')
  const ownedShoppingItems = ownedItems.map((item) => ({
    ...item,
    ...(ownedProductMap[item.name] || {}),
  }))
  const activeItems = items.filter((item) => !item.is_purchased)
  const visibleHistoryLists = mergeRecentWithHistory(recentList, historyLists)

  useEffect(() => {
    let isAlive = true

    async function loadShoppingList() {
      setIsLoading(true)
      setError('')
      setStartNotice('')

      if (!hasShoppingAuth()) {
        setShoppingList(searchParams.get('source') === 'recipe' ? buildFallbackShoppingList(storedContext) : null)
        setRecentList(null)
        setHistoryLists([])
        setIsLoading(false)
        return
      }

      try {
        if (searchParams.get('fallback') === '1' || searchParams.get('source') === 'recipe') {
          const fallbackList = buildFallbackShoppingList(storedContext)
          if (fallbackList && !shoppingListId) {
            setShoppingList(fallbackList)
            setRecentList(null)
            return
          }
        }

        const data = shoppingListId
          ? await getShoppingList(shoppingListId)
          : await getCurrentShoppingList().then((response) => response.shopping_list)
        const historyData = !shoppingListId
          ? await getShoppingHistory().then((response) => response.shopping_lists || [])
          : []

        if (!isAlive) return

        setShoppingList(shoppingListId ? data : null)
        setRecentList(shoppingListId ? null : data)
        setHistoryLists(shoppingListId ? [] : historyData)
      } catch (shoppingError) {
        if (!isAlive) return

        if (shoppingError.status === 401) {
          setShoppingList(null)
          setRecentList(null)
          setHistoryLists([])
          return
        }

        if (!shoppingListId) {
          setShoppingList(null)
          setRecentList(null)
          setHistoryLists([])
          setStartNotice('최근 장보기 목록을 확인하지 못했어요. 레시피를 먼저 확인해 장보기를 시작할 수 있어요.')
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
  }, [shoppingListId, isHistoryView])

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

  const allChecked = activeItems.length > 0 && activeItems.every((item) => item.is_checked)

  const continueRecentShopping = () => {
    if (!recentList?.id) return
    navigate(`/shopping-list?shoppingListId=${recentList.id}`)
  }

  const browseShoppingHistory = () => {
    navigate('/shopping-list?view=history')
  }

  const openHistoryList = (shoppingHistoryId) => {
    navigate(`/shopping-list?shoppingListId=${shoppingHistoryId}`)
  }

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
    const targets = activeItems.filter((item) => item.is_checked !== nextChecked)
    if (targets.length === 0) {
      return
    }

    if (isFallbackList) {
      setShoppingList((prev) => ({
        ...prev,
        items: prev.items.map((item) => (
          item.is_purchased ? item : { ...item, is_checked: nextChecked }
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
      setRecentList(null)
      navigate('/shopping-list')
      return
    }

    setIsMutating(true)
    try {
      await deleteShoppingList(shoppingList.id)
      setShoppingList(null)
      setRecentList(null)
      navigate('/shopping-list')
    } catch (shoppingError) {
      await showAlert(shoppingError.message || '장보기 목록을 삭제하지 못했어요.', {
        title: '목록 삭제 실패',
      })
    } finally {
      setIsMutating(false)
    }
  }

  const deleteHistoryLists = async (shoppingListIds) => {
    const targetIds = [...new Set((shoppingListIds || []).map((id) => Number(id)).filter(Boolean))]
    if (targetIds.length === 0) {
      return false
    }

    const confirmed = await showConfirm(`총 ${targetIds.length}개 장보기 내역을 삭제하시겠습니까?`, {
      title: '선택 내역 삭제',
      confirmText: '삭제',
      cancelText: '취소',
    })
    if (!confirmed) {
      return false
    }

    const deletedIds = []
    setIsMutating(true)
    try {
      for (const id of targetIds) {
        await deleteShoppingList(id)
        deletedIds.push(id)
      }

      const deletedIdSet = new Set(deletedIds)
      setHistoryLists((prev) => prev.filter((list) => !deletedIdSet.has(Number(list.id))))
      setRecentList((prev) => (deletedIdSet.has(Number(prev?.id)) ? null : prev))
      setShoppingList((prev) => (deletedIdSet.has(Number(prev?.id)) ? null : prev))
      await showAlert(`${deletedIds.length}개 장보기 내역을 삭제했어요.`, {
        title: '선택 삭제 완료',
      })
      return true
    } catch (shoppingError) {
      if (deletedIds.length > 0) {
        const deletedIdSet = new Set(deletedIds)
        setHistoryLists((prev) => prev.filter((list) => !deletedIdSet.has(Number(list.id))))
        setRecentList((prev) => (deletedIdSet.has(Number(prev?.id)) ? null : prev))
        setShoppingList((prev) => (deletedIdSet.has(Number(prev?.id)) ? null : prev))
      }
      await showAlert(shoppingError.message || '선택한 장보기 내역을 삭제하지 못했어요.', {
        title: '선택 삭제 실패',
      })
      return false
    } finally {
      setIsMutating(false)
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

      if (!result.shopping_list || getRemainingItemCount(result.shopping_list) === 0) {
        try {
          await deleteShoppingList(shoppingList.id)
          setShoppingList(null)
          setRecentList((prev) => (Number(prev?.id) === Number(shoppingList.id) ? null : prev))
          setHistoryLists((prev) => prev.filter((list) => Number(list.id) !== Number(shoppingList.id)))
          navigate('/shopping-list')
          await showAlert(`${result.message || '구매한 재료를 냉장고에 입고했어요.'} 완료된 장보기 목록은 자동으로 삭제됐어요.`, {
            title: '냉장고 입고 완료',
          })
        } catch (deleteError) {
          setShoppingList(result.shopping_list)
          await showAlert(
            `${result.message || '구매한 재료를 냉장고에 입고했어요.'} 다만 완료된 장보기 목록을 자동 삭제하지 못했어요.`,
            { title: '목록 자동 삭제 실패' },
          )
        }
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

  if (!shoppingList && isHistoryView) {
    return (
      <>
        <ShoppingHistory
          lists={visibleHistoryLists}
          recentListId={recentList?.id}
          isDeleting={isMutating}
          onOpenList={openHistoryList}
          onDeleteSelected={deleteHistoryLists}
          onBackToStart={() => navigate('/shopping-list')}
        />
        {dialogNode}
      </>
    )
  }

  if (!shoppingList) {
    return (
      <>
        <ShoppingStart
          isLoggedIn={isLoggedIn}
          recentList={recentList}
          historyCount={visibleHistoryLists.length}
          notice={startNotice}
          onContinue={continueRecentShopping}
          onHistoryBrowse={browseShoppingHistory}
          onRecipeBrowse={() => navigate('/recipes')}
          onLogin={() => navigate('/login')}
        />
        {dialogNode}
      </>
    )
  }

  return (
    <section className="shopping-page" aria-labelledby="shopping-title">
      <div className="shopping-hero">
        <div className="shopping-hero__copy">
          <span className="shopping-eyebrow">레시피 기준 장보기</span>
          <h1 id="shopping-title">{recipeTitle} 만들기,<br />이 재료가 없어요</h1>
          <p>
            냉장고에 있는 재료와 부족한 재료를 함께 보고, 필요한 재료는 구매 링크로 바로 확인해요.
          </p>
          <div className="shopping-service-badges" aria-label="장보기 기준">
            <span>{storedContext?.servingLabel ?? '3인분 기준'}</span>
            <span>냉장고 비교</span>
            <span>구매 링크 제공</span>
            {isFallbackList ? <span>임시 목록</span> : null}
          </div>
        </div>
        <div className="shopping-hero__art" aria-hidden="true">
          <img src={imageShop} alt="" />
        </div>
      </div>

      <div className="shopping-main-grid shopping-main-grid--recipe">
        <section className="shopping-panel shopping-list-panel" aria-labelledby="shopping-list-title">
          <div className="shopping-list-toolbar">
            <div className="shopping-list-toolbar__title">
              <h2 id="shopping-list-title">구매가 필요한 재료</h2>
              <span className="shopping-count-badge">{activeItems.length}개</span>
            </div>
            <button
              type="button"
              className={`shopping-select-all ${allChecked ? 'is-active' : ''}`}
              onClick={toggleSelectAll}
              disabled={isMutating || activeItems.length === 0}
            >
              <span className={`shopping-check ${allChecked ? 'is-checked' : ''}`} aria-hidden="true" />
              전체 선택
              {selectedItems.length > 0 ? <em>{selectedItems.length}개 선택됨</em> : null}
            </button>
          </div>

          <div className="shopping-item-rows">
            {activeItems.length === 0 ? (
              <div className="shopping-empty-block">
                <p className="shopping-empty-note">
                  {ownedItems.length > 0
                    ? '따로 구매할 재료가 없어요. 필요한 재료는 이미 냉장고에 있어요.'
                    : '구매가 필요한 재료를 모두 냉장고에 입고했어요.'}
                </p>
                <button
                  className="shopping-delete-list-button"
                  type="button"
                  disabled={isMutating}
                  onClick={deleteWholeList}
                >
                  이 장보기 목록 삭제
                </button>
              </div>
            ) : (
              activeItems.map((item) => (
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
                    <strong>{item.name}<span>· {formatQuantity(item)}</span></strong>
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
              ))
            )}

            {ownedShoppingItems.map((item, index) => (
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
                <dd>{activeItems.length}개</dd>
              </div>
              <div>
                <dt>보유 재료</dt>
                <dd>{ownedItems.length}개</dd>
              </div>
              <div className="shopping-metric-list__total">
                <dt>예상 금액 <span>선택 {selectedItems.length}개</span></dt>
                <dd>{formatPrice(shoppingList?.total_price ?? 0)}</dd>
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
            onClick={() => navigate(shoppingList.recipe_id ? `/recipes/${shoppingList.recipe_id}` : '/recipes')}
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
