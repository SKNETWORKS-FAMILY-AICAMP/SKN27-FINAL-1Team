import React, { useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import './ShoppingList.css'

import iconBasket from '../../assets/extracted/icons/icon_basket.png'
import iconCart from '../../assets/extracted/icons/icon_cart.png'
import iconRefrigerator from '../../assets/extracted/icons/icon_refrigerator.png'
import imageShop from '../../assets/extracted/images/image_shop.png'
import { useAppDialog } from '../../components/AppDialog.jsx'

const SHOPPING_CONTEXT_KEY = 'bobbeori-recipe-shopping-context'

const markets = [
  {
    key: 'naver',
    label: '네이버쇼핑',
    buildUrl: (query) => `https://search.shopping.naver.com/search/all?query=${encodeURIComponent(query)}`,
  },
  {
    key: 'coupang',
    label: '쿠팡',
    buildUrl: (query) => `https://www.coupang.com/np/search?q=${encodeURIComponent(query)}`,
  },
  {
    key: 'kurly',
    label: '컬리',
    buildUrl: (query) => `https://www.kurly.com/search?sword=${encodeURIComponent(query)}`,
  },
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

function buildSearchQuery(item) {
  return [item.name, item.amount].filter(Boolean).join(' ')
}

function ShoppingStart({ recentContext, onContinue, onRecipeBrowse }) {
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

      <div className="shopping-start-grid">
        {recentContext ? (
          <article className="shopping-start-card is-featured">
            <span>최근 장바구니</span>
            <h2>{recentContext.recipeTitle} 이어서 장보기</h2>
            <p>
              {recentContext.missingIngredients.length}가지 부족 재료가 저장되어 있어요.
              {formatCreatedAt(recentContext.createdAt)} 기준 목록입니다.
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
          <span>준비 중</span>
          <h2>냉장고 보충 장보기</h2>
          <p>자주 쓰는 재료, 곧 떨어지는 재료, 유통기한 임박 재료를 기준으로 추천하는 흐름입니다.</p>
          <button className="shopping-soft-action" type="button" onClick={onRecipeBrowse}>
            지금은 레시피에서 시작하기
          </button>
        </article>
      </div>
    </section>
  )
}

function ShoppingList() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { dialogNode } = useAppDialog()
  const [storedContext] = useState(readShoppingContext)
  const [activeContext, setActiveContext] = useState(() => (
    searchParams.has('recipeId') || searchParams.get('source') === 'recipe' ? storedContext : null
  ))

  const missingItems = activeContext?.missingIngredients ?? []
  const ownedItems = activeContext?.ownedIngredients ?? []
  const hasRecipeContext = Boolean(activeContext && missingItems.length > 0)

  const summary = useMemo(
    () => [
      {
        label: '부족 재료',
        value: `${missingItems.length}개`,
        note: `${activeContext?.recipeTitle ?? '레시피'} 기준`,
        image: iconBasket,
      },
      {
        label: '보유 재료',
        value: `${ownedItems.length}개`,
        note: '내 냉장고와 비교',
        image: iconRefrigerator,
      },
      {
        label: '구매 연결',
        value: `${markets.length}곳`,
        note: '재료별 검색 링크 제공',
        image: iconCart,
      },
    ],
    [activeContext?.recipeTitle, missingItems.length, ownedItems.length],
  )

  const openAllNaverLinks = () => {
    missingItems.forEach((item, index) => {
      window.setTimeout(() => {
        window.open(markets[0].buildUrl(buildSearchQuery(item)), '_blank', 'noopener,noreferrer')
      }, index * 120)
    })
  }

  if (!hasRecipeContext) {
    return (
      <>
        <ShoppingStart
          recentContext={storedContext}
          onContinue={() => setActiveContext(storedContext)}
          onRecipeBrowse={() => navigate('/recipes')}
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
          <h1 id="shopping-title">{activeContext.recipeTitle} 부족 재료</h1>
          <p>
            내 냉장고에 있는 재료는 제외하고, 이 레시피에 필요한 부족 재료만 구매 링크로 연결해요.
          </p>
          <div className="shopping-service-badges" aria-label="장보기 기준">
            <span>{activeContext.servingLabel ?? '레시피 기준'}</span>
            <span>냉장고 비교</span>
            <span>부족 재료만</span>
            <span>구매 링크 연결</span>
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

      <section className="shopping-personal-panel" aria-labelledby="shopping-service-title">
        <div>
          <span>장보기 흐름</span>
          <h2 id="shopping-service-title">레시피에서 이어진 부족 재료를 해결해요</h2>
          <p>
            {activeContext.recipeTitle}에 필요한 재료 중 냉장고에 없는 항목만 추렸어요.
            원하는 구매처 버튼을 누르면 해당 재료 검색 결과로 이동합니다.
          </p>
        </div>
        <ol>
          <li>
            <strong>냉장고 확인</strong>
            <p>보유 재료를 먼저 제외했어요.</p>
          </li>
          <li>
            <strong>부족 재료 추림</strong>
            <p>레시피에 꼭 필요한 재료만 남겼어요.</p>
          </li>
          <li>
            <strong>구매 링크 연결</strong>
            <p>재료별 쇼핑 검색으로 바로 이어져요.</p>
          </li>
        </ol>
      </section>

      <div className="shopping-main-grid shopping-main-grid--recipe">
        <section className="shopping-panel shopping-list-panel" aria-labelledby="shopping-list-title">
          <div className="shopping-panel__header">
            <div>
              <h2 id="shopping-list-title">구매가 필요한 재료</h2>
              <p>{missingItems.length}가지 재료를 구매하면 바로 조리를 시작할 수 있어요.</p>
            </div>
            <button
              className="shopping-soft-button"
              type="button"
              onClick={() => navigate(activeContext.recipePath || '/recipes')}
            >
              레시피로 돌아가기
            </button>
          </div>

          <div className="shopping-link-list">
            {missingItems.map((item, index) => (
              <article className="shopping-link-item" key={`${item.ingredient_id ?? item.name}-${index}`}>
                <div>
                  <strong>{item.name}</strong>
                  <p>{item.amount || '필요 수량 확인'}</p>
                </div>
                <div className="shopping-market-links" aria-label={`${item.name} 구매 링크`}>
                  {markets.map((market) => (
                    <a
                      key={market.key}
                      href={market.buildUrl(buildSearchQuery(item))}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      {market.label}
                    </a>
                  ))}
                </div>
              </article>
            ))}
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
            <p className="shopping-empty-note">보유 재료가 없거나 로그인 전이라 전체 재료가 부족 재료로 표시될 수 있어요.</p>
          )}

          <div className="shopping-service-note">
            <strong>구매 링크 안내</strong>
            <p>
              쇼핑몰 장바구니에 직접 담는 제휴 API는 아직 연결하지 않았어요.
              현재는 재료명 기준 검색 결과로 연결하는 MVP 흐름입니다.
            </p>
          </div>
        </aside>
      </div>

      <div className="shopping-actions shopping-actions--recipe">
        <button
          className="shopping-soft-action"
          type="button"
          onClick={() => navigate(activeContext.recipePath || '/recipes')}
        >
          레시피 상세 보기
        </button>
        <button className="shopping-primary-action" type="button" onClick={openAllNaverLinks}>
          선택 재료 구매 링크 열기
        </button>
      </div>
      {dialogNode}
    </section>
  )
}

export default ShoppingList
