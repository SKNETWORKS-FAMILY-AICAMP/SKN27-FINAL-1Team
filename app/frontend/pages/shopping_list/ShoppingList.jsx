import React, { useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import './ShoppingList.css'

import iconBasket from '../../assets/extracted/icons/icon_basket.png'
import iconCart from '../../assets/extracted/icons/icon_cart.png'
import iconRefrigerator from '../../assets/extracted/icons/icon_refrigerator.png'
import imageShop from '../../assets/extracted/images/image_shop.png'
import { useAppDialog } from '../../components/AppDialog.jsx'
import {
  completeShoppingPurchase,
  deleteShoppingListItem,
  getCurrentShoppingList,
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

function getRecipeTitle(shoppingList, context) {
  if (context?.recipeId && Number(context.recipeId) === Number(shoppingList?.recipe_id)) {
    return context.recipeTitle
  }
  if (shoppingList?.recipe_id) {
    return `레시피 #${shoppingList.recipe_id}`
  }
  return '최근 장보기'
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

function ShoppingStart({ isLoggedIn, recentList, notice, onContinue, onRecipeBrowse, onLogin }) {
  return (
    <section className="shopping-page shopping-page--start" aria-labelledby="shopping-title">
      <div className="shopping-hero">
        <div className="shopping-hero__copy">
          <span className="shopping-eyebrow">장보기 시작</span>
          <h1 id="shopping-title">무엇을 기준으로 장볼까요?</h1>
          <p>
            레시피에서 부족 재료를 바로 확인하거나, 최근 장보기 목록을 이어서 볼 수 있어요.
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
              구매 전 재료 {recentList.items.filter((item) => !item.is_purchased).length}개가 남아 있어요.
              {formatCreatedAt(recentList.created_at)} 기준 목록입니다.
            </p>
            <button className="shopping-primary-action" type="button" onClick={onContinue}>
              이어서 장보기
            </button>
          </article>
        ) : null}

        <article className="shopping-start-card">
          <span>1순위 흐름</span>
          <h2>레시피 기준으로 장보기</h2>
          <p>레시피 상세에서 냉장고 재료와 비교한 뒤 부족한 재료만 구매 링크로 연결해요.</p>
          <button className="shopping-soft-action" type="button" onClick={onRecipeBrowse}>
            레시피 먼저 확인하기
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

function ShoppingList() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { dialogNode, showAlert, showConfirm } = useAppDialog()
  const [storedContext] = useState(readShoppingContext)
  const [shoppingList, setShoppingList] = useState(null)
  const [recentList, setRecentList] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isMutating, setIsMutating] = useState(false)
  const [error, setError] = useState('')
  const [startNotice, setStartNotice] = useState('')

  const isLoggedIn = hasShoppingAuth()
  const shoppingListId = searchParams.get('shoppingListId')
  const recipeTitle = getRecipeTitle(shoppingList, storedContext)
  const items = shoppingList?.items ?? []
  const isFallbackList = Boolean(shoppingList?.isFallback)
  const selectedItems = items.filter((item) => item.is_checked && !item.is_purchased)
  const ownedItems = storedContext?.recipeId && Number(storedContext.recipeId) === Number(shoppingList?.recipe_id)
    ? storedContext.ownedIngredients
    : []
  const activeItems = items.filter((item) => !item.is_purchased)

  useEffect(() => {
    let isAlive = true

    async function loadShoppingList() {
      setIsLoading(true)
      setError('')
      setStartNotice('')

      if (!hasShoppingAuth()) {
        setShoppingList(searchParams.get('source') === 'recipe' ? buildFallbackShoppingList(storedContext) : null)
        setRecentList(null)
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

        if (!isAlive) return

        setShoppingList(shoppingListId ? data : null)
        setRecentList(shoppingListId ? null : data)
      } catch (shoppingError) {
        if (!isAlive) return

        if (shoppingError.status === 401) {
          setShoppingList(null)
          setRecentList(null)
          return
        }

        if (!shoppingListId) {
          setShoppingList(null)
          setRecentList(null)
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
  }, [shoppingListId])

  const summary = useMemo(
    () => [
      {
        label: '구매 필요',
        value: `${activeItems.length}개`,
        note: `${recipeTitle} 기준`,
        image: iconBasket,
      },
      {
        label: '보유 재료',
        value: `${ownedItems.length}개`,
        note: '내 냉장고와 비교',
        image: iconRefrigerator,
      },
      {
        label: '예상 금액',
        value: formatPrice(shoppingList?.total_price ?? 0),
        note: '선택된 상품 기준',
        image: iconCart,
      },
    ],
    [activeItems.length, ownedItems.length, recipeTitle, shoppingList?.total_price],
  )

  const continueRecentShopping = () => {
    if (!recentList?.id) return
    navigate(`/shopping-list?shoppingListId=${recentList.id}`)
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

    const confirmed = await showConfirm(`선택한 ${selectedItems.length}개 재료를 냉장고에 입고하시겠습니까?`, {
      title: '냉장고 입고',
      confirmText: '입고',
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
        <ShoppingStart
          isLoggedIn={isLoggedIn}
          recentList={recentList}
          notice={startNotice}
          onContinue={continueRecentShopping}
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
          <h1 id="shopping-title">{recipeTitle} 부족 재료</h1>
          <p>
            내 냉장고에 있는 재료는 제외하고, 이 레시피에 필요한 부족 재료만 구매 링크로 연결해요.
          </p>
          <div className="shopping-service-badges" aria-label="장보기 기준">
            <span>{storedContext?.servingLabel ?? '레시피 기준'}</span>
            <span>냉장고 비교</span>
            <span>부족 재료만</span>
            {isFallbackList ? <span>임시 목록</span> : null}
          </div>
        </div>
        <div className="shopping-hero__art" aria-hidden="true">
          <img src={imageShop} alt="" />
        </div>
      </div>

      <div className="shopping-summary shopping-summary--compact" aria-label="장보기 요약">
        {summary.map((card) => (
          <article className="shopping-summary-card" key={card.label}>
            <ImageSlot className="shopping-summary-card__icon" src={card.image} />
            <div>
              <span>{card.label}</span>
              <strong>{card.value}</strong>
              <p>{card.note}</p>
            </div>
          </article>
        ))}
      </div>

      <div className="shopping-main-grid shopping-main-grid--recipe">
        <section className="shopping-panel shopping-list-panel" aria-labelledby="shopping-list-title">
          <div className="shopping-panel__header">
            <div>
              <h2 id="shopping-list-title">구매가 필요한 재료</h2>
              <p>
                {activeItems.length}가지 재료를 구매하면 바로 조리를 시작할 수 있어요.
                {isFallbackList ? ' 서버 연결 후 구매 링크가 표시됩니다.' : ''}
              </p>
            </div>
            <div className="shopping-panel__header-actions">
              <button
                className="shopping-delete-button"
                type="button"
                disabled={isMutating || selectedItems.length === 0}
                onClick={deleteSelectedItems}
              >
                선택 삭제 ({selectedItems.length})
              </button>
              <button
                className="shopping-soft-button"
                type="button"
                onClick={() => navigate(shoppingList.recipe_id ? `/recipes/${shoppingList.recipe_id}` : '/recipes')}
              >
                레시피로 돌아가기
              </button>
            </div>
          </div>

          <div className="shopping-link-list">
            {activeItems.length === 0 ? (
              <p className="shopping-empty-note">구매가 필요한 재료를 모두 냉장고에 입고했어요.</p>
            ) : (
              activeItems.map((item) => (
                <article
                  className="shopping-link-item"
                  key={item.id}
                >
                  <button
                    className={`shopping-check ${item.is_checked ? 'is-checked' : ''}`}
                    type="button"
                    aria-label={`${item.name} 구매 대상 ${item.is_checked ? '해제' : '선택'}`}
                    disabled={isMutating}
                    onClick={() => updateItemChecked(item)}
                  />
                  <ImageSlot className="shopping-item__image" src={item.product_image} alt={item.product_name || item.name} />
                  <div>
                    <strong>{item.name}</strong>
                    <p>{formatQuantity(item)}</p>
                    <small>{item.product_name || '상품 검색 결과 없음'}</small>
                  </div>
                  <div className="shopping-product-meta">
                    <span>{item.mall_name || item.provider || 'provider'}</span>
                    <strong>{formatPrice(item.price)}</strong>
                  </div>
                  {item.product_link ? (
                    <a
                      className="shopping-purchase-link"
                      href={item.product_link}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      구매 링크
                    </a>
                  ) : (
                    <span className="shopping-purchase-link is-disabled">링크 없음</span>
                  )}
                </article>
              ))
            )}
          </div>
        </section>

        <aside className="shopping-panel shopping-owned-panel" aria-labelledby="owned-title">
          <div className="shopping-panel__header">
            <div>
              <h2 id="owned-title">이미 있는 재료</h2>
              <p>냉장고에서 확인되어 장보기 목록에서 제외했어요.</p>
            </div>
          </div>

          {ownedItems.length > 0 ? (
            <div className="shopping-owned-list">
              {ownedItems.map((item, index) => (
                <span key={`${item.name}-${index}`}>
                  {item.name}{item.amount ? ` ${item.amount}` : ''}
                </span>
              ))}
            </div>
          ) : (
            <p className="shopping-empty-note">보유 재료 정보는 레시피 상세에서 이어온 경우에만 표시돼요.</p>
          )}

          <div className="shopping-service-note">
            <strong>구매 링크 안내</strong>
            <p>
              {isFallbackList
                ? '지금은 장보기 목록 생성에 실패해 부족 재료만 임시로 보여주고 있어요.'
                : '재료별로 찾은 상품 링크로 바로 연결돼요. 쇼핑몰 장바구니에 자동으로 담기지는 않아요.'}
            </p>
          </div>
        </aside>
      </div>

      <div className="shopping-actions shopping-actions--recipe">
        <button
          className="shopping-soft-action"
          type="button"
          onClick={() => navigate(shoppingList.recipe_id ? `/recipes/${shoppingList.recipe_id}` : '/recipes')}
        >
          레시피 상세 보기
        </button>
        <button
          className="shopping-soft-action"
          type="button"
          disabled={isMutating || selectedItems.length === 0}
          onClick={completePurchase}
        >
          선택 재료 ({selectedItems.length}) 구매 완료 후 냉장고 입고
        </button>
      </div>
      {dialogNode}
    </section>
  )
}

export default ShoppingList
