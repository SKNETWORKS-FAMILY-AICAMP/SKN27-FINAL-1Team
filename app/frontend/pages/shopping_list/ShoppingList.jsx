import React, { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import './ShoppingList.css'

import iconBasket from '../../assets/extracted/icons/icon_basket.png'
import iconCart from '../../assets/extracted/icons/icon_cart.png'
import iconRefrigerator from '../../assets/extracted/icons/icon_refrigerator.png'
import imageShop from '../../assets/extracted/images/image_shop.png'
import { useAppDialog } from '../../components/AppDialog.jsx'
import { priceRows, shoppingItems } from '../../mock/shoppingListMock.js'
import {
  formatWon,
  serviceBadges,
  serviceContext,
  serviceSteps,
  userProfile,
} from '../../mock/userService.js'

function ImageSlot({ src, alt = '', className = '' }) {
  return (
    <span className={`shopping-image-slot ${src ? 'is-filled' : ''} ${className}`}>
      {src ? <img src={src} alt={alt} /> : null}
    </span>
  )
}

function ShoppingList() {
  const navigate = useNavigate()
  const { dialogNode, showAlert, showPrompt } = useAppDialog()
  const [items, setItems] = useState(() =>
    shoppingItems.map((item) => ({ ...item, selected: true, count: 1 })),
  )

  const selectedCount = items.filter((item) => item.selected).length
  const selectedItems = items.filter((item) => item.selected)
  const allSelected = selectedCount === items.length && items.length > 0
  const selectedRatio = items.length ? selectedCount / items.length : 0
  const cartTotal = Math.round((serviceContext.currentCartTotal * selectedRatio) / 10) * 10
  const budgetLeft = serviceContext.cartBudget - cartTotal
  const deliverySaving = serviceContext.deliveryTotal - cartTotal
  const summary = useMemo(
    () => [
      {
        label: '선택 재료',
        value: `${selectedCount}개`,
        note: `${items.length}개 중 ${userProfile.mealTarget}에 맞게 선택`,
        image: iconBasket,
      },
      {
        label: '예상 결제',
        value: formatWon(cartTotal),
        note: `${serviceContext.selectedMarket} · ${serviceContext.deliveryEta}`,
        image: iconCart,
      },
      {
        label: '예산 상태',
        value: budgetLeft >= 0 ? `${formatWon(budgetLeft)} 남음` : `${formatWon(Math.abs(budgetLeft))} 초과`,
        note: `목표 ${userProfile.budgetLabel}`,
        accent: budgetLeft >= 0,
      },
      {
        label: '배달 대비 절약',
        value: formatWon(Math.max(0, deliverySaving)),
        note: `배달 예상 ${formatWon(serviceContext.deliveryTotal)} 대비`,
        accent: true,
      },
      {
        label: '냉장고 매칭',
        value: serviceContext.fridgeMatch,
        note: `${serviceContext.urgentIngredientCount}개 임박 재료 우선 반영`,
        image: iconRefrigerator,
      },
    ],
    [budgetLeft, cartTotal, deliverySaving, items.length, selectedCount],
  )

  const toggleAll = () => {
    setItems((prev) => prev.map((item) => ({ ...item, selected: !allSelected })))
  }

  const toggleItem = (name) => {
    setItems((prev) =>
      prev.map((item) =>
        item.name === name ? { ...item, selected: !item.selected } : item,
      ),
    )
  }

  const changeCount = (name, amount) => {
    setItems((prev) =>
      prev.map((item) =>
        item.name === name ? { ...item, count: Math.max(1, item.count + amount) } : item,
      ),
    )
  }

  const addItem = async () => {
    const name = await showPrompt('추가할 재료명을 입력해주세요.', {
      title: '재료 추가',
      placeholder: '예: 양파',
    })

    if (!name?.trim()) {
      return
    }

    setItems((prev) => [
      ...prev,
      {
        name: name.trim(),
        detail: '직접 추가',
        quantity: '1개',
        recipe: '직접 추가',
        reason: '사용자가 직접 추가한 재료',
        priority: '직접 추가',
        selected: true,
        count: 1,
      },
    ])
  }

  const completePurchase = () => {
    window.localStorage.setItem('bobbeori-last-stocked-count', String(selectedCount))
    navigate('/fridge')
  }

  return (
    <section className="shopping-page" aria-labelledby="shopping-title">
      <div className="shopping-hero">
        <div className="shopping-hero__copy">
          <span className="shopping-eyebrow">사용자 맞춤 장보기</span>
          <h1 id="shopping-title">{userProfile.mealTarget} 장보기 플랜</h1>
          <p>
            {userProfile.household}, {userProfile.cookTime}, {userProfile.budgetLabel} 기준으로
            필요한 재료만 골라 담았어요.
          </p>
          <div className="shopping-service-badges" aria-label="맞춤 기준">
            {serviceBadges.map((badge) => (
              <span key={badge}>{badge}</span>
            ))}
          </div>
        </div>
        <div className="shopping-hero__art" aria-hidden="true">
          <img src={imageShop} alt="" />
        </div>
      </div>

      <div className="shopping-summary" aria-label="장보기 요약">
        {summary.map((card) => (
          <article className="shopping-summary-card" key={card.label}>
            <ImageSlot className="shopping-summary-card__icon" src={card.image} />
            <div>
              <span>{card.label}</span>
              <strong className={card.accent ? 'is-accent' : ''}>{card.value}</strong>
              <p>{card.note}</p>
            </div>
          </article>
        ))}
      </div>

      <section className="shopping-personal-panel" aria-labelledby="shopping-service-title">
        <div>
          <span>오늘의 서비스 흐름</span>
          <h2 id="shopping-service-title">
            {serviceContext.selectedRecipe}에 필요한 것만 남겼어요
          </h2>
          <p>
            {userProfile.priority}를 기준으로 냉장고 재고와 부족 재료를 비교했고,
            {serviceContext.pairedRecipe}까지 함께 만들 수 있는 장보기 조합입니다.
          </p>
        </div>
        <ol>
          {serviceSteps.map((step) => (
            <li key={step.title}>
              <strong>{step.title}</strong>
              <p>{step.description}</p>
            </li>
          ))}
        </ol>
      </section>

      <div className="shopping-main-grid">
        <section className="shopping-panel shopping-list-panel" aria-labelledby="shopping-list-title">
          <div className="shopping-panel__header">
            <div>
              <h2 id="shopping-list-title">오늘 필요한 재료</h2>
              <p>
                선택한 {selectedCount}개 재료 기준 예상 결제 금액은 {formatWon(cartTotal)}입니다.
              </p>
            </div>
            <button className="shopping-soft-button" type="button" onClick={() => navigate('/recipe-fridge')}>
              추천 레시피 보기
            </button>
          </div>

          <div className="shopping-items">
            <div className="shopping-items__head">
              <button type="button" onClick={toggleAll}>
                {allSelected ? '전체 해제' : '전체 선택'}
              </button>
              <span>재료</span>
              <span>필요 수량</span>
              <span>사용 레시피</span>
            </div>
            {items.map((item) => (
              <article className="shopping-item" key={item.name}>
                <button
                  className={`shopping-check ${item.selected ? 'is-checked' : ''}`}
                  type="button"
                  aria-label={`${item.name} 선택`}
                  aria-pressed={item.selected}
                  onClick={() => toggleItem(item.name)}
                />
                <div className="shopping-item__ingredient">
                  <ImageSlot className="shopping-item__image" src={item.image} />
                  <div>
                    <div className="shopping-item__title-row">
                      <strong>{item.name}</strong>
                      <em>{item.priority}</em>
                    </div>
                    <p>{item.detail}</p>
                    <small>{item.reason}</small>
                  </div>
                </div>
                <div className="shopping-quantity" aria-label={`${item.name} 수량`}>
                  <button type="button" onClick={() => changeCount(item.name, -1)}>-</button>
                  <span>{item.count > 1 ? `${item.quantity}×${item.count}` : item.quantity}</span>
                  <button type="button" onClick={() => changeCount(item.name, 1)}>+</button>
                </div>
                <span className="shopping-recipe-chip">{item.recipe}</span>
              </article>
            ))}
          </div>

          <button className="shopping-add-button" type="button" onClick={addItem}>
            + 직접 재료 추가
          </button>
          <p className="shopping-tip">
            {budgetLeft >= 0
              ? `아직 ${formatWon(budgetLeft)} 여유가 있어요. 선택 재료를 모두 사도 예산 안에 들어옵니다.`
              : `${formatWon(Math.abs(budgetLeft))} 초과예요. 선택 품목부터 빼면 예산 안에 맞출 수 있어요.`}
          </p>
        </section>

        <section className="shopping-panel shopping-price-panel" aria-labelledby="price-title">
          <div className="shopping-panel__header">
            <div>
              <h2 id="price-title">사용자 기준 최저가 조합</h2>
              <p>{userProfile.budgetLabel}와 오늘 도착 가능 여부를 같이 봤어요.</p>
            </div>
          </div>

          <div className="shopping-price-table" role="table" aria-label="구매처별 가격 비교">
            <div className="shopping-price-row shopping-price-row--head" role="row">
              <span role="columnheader">재료</span>
              <span role="columnheader">마켓컬리</span>
              <span role="columnheader">쿠팡</span>
              <span role="columnheader">최저가</span>
              <span role="columnheader">비교</span>
            </div>
            {priceRows.map((row) => (
              <div className="shopping-price-row" role="row" key={row.name}>
                <span role="cell">{row.name}</span>
                <span role="cell">{row.marketA}</span>
                <span role="cell">{row.marketB}</span>
                <strong role="cell">{row.best}</strong>
                <span role="cell">{row.diff}</span>
              </div>
            ))}
            <div className="shopping-price-row shopping-price-row--total" role="row">
              <span role="cell">합계</span>
              <span role="cell">16,740원</span>
              <span role="cell">15,690원</span>
              <strong role="cell">15,690원</strong>
              <span role="cell">-1,050원</span>
            </div>
          </div>

          <div className="shopping-best-box">
            <strong>추천 구매처: {serviceContext.selectedMarket} ({formatWon(cartTotal)})</strong>
            <button
              className="shopping-soft-button"
              type="button"
              onClick={() => showAlert(`${selectedCount}개 재료를 최저가 장바구니에 담았어요.`, {
                title: '장바구니 담기',
              })}
            >
              최저가 장바구니 담기
            </button>
          </div>

          <div className="shopping-service-note">
            <strong>맞춤 제안</strong>
            <p>
              {selectedItems.some((item) => item.priority === '선택')
                ? '예산을 더 줄이고 싶다면 선택 품목부터 빼는 것을 추천해요.'
                : '선택한 재료는 오늘 메뉴에 바로 쓰이는 품목 위주예요.'}
            </p>
          </div>
        </section>
      </div>

      <div className="shopping-metrics">
        <section className="shopping-panel shopping-saving" aria-labelledby="saving-title">
          <ImageSlot className="shopping-saving__image" src={imageShop} />
          <div>
            <h2 id="saving-title">배달 대비 절약</h2>
            <div className="shopping-saving__compare">
              <span>
                장바구니 예상가
                <strong>{formatWon(cartTotal)}</strong>
              </span>
              <span>
                배달 예상가
                <strong>{formatWon(serviceContext.deliveryTotal)}</strong>
              </span>
              <em>{formatWon(Math.max(0, deliverySaving))}</em>
            </div>
          </div>
        </section>

        <section className="shopping-panel shopping-cost" aria-labelledby="cost-title">
          <h2 id="cost-title">예산 안심 계산</h2>
          <div className="shopping-cost__flow">
            <span>
              장보기 합계
              <strong>{formatWon(cartTotal)}</strong>
            </span>
            <b>+</b>
            <span>
              집 재료 활용
              <strong>{serviceContext.fridgeMatch}</strong>
            </span>
            <b>=</b>
            <span>
              남은 예산
              <strong>{budgetLeft >= 0 ? formatWon(budgetLeft) : '초과'}</strong>
            </span>
            <em>{budgetLeft >= 0 ? '안심' : '조정'}</em>
          </div>
        </section>
      </div>

      <div className="shopping-actions">
        <button
          className="shopping-soft-action"
          type="button"
          onClick={() => navigate('/recipes/green-onion-tofu-egg-stew')}
        >
          레시피 상세 보기
        </button>
        <button
          className="shopping-soft-action"
          type="button"
          onClick={() => window.open('https://www.coupang.com/', '_blank', 'noopener,noreferrer')}
        >
          최저가 마켓 바로가기
        </button>
        <button
          className="shopping-primary-action"
          type="button"
          disabled={selectedCount === 0}
          onClick={completePurchase}
        >
          구매 완료하고 냉장고 입고
          <ImageSlot className="shopping-primary-action__icon" src={iconRefrigerator} />
        </button>
        <button
          className="shopping-soft-action"
          type="button"
          onClick={() => showAlert(`${selectedCount}개 재료를 장바구니에 담았어요.`, {
            title: '장바구니 담기',
          })}
        >
          장바구니 담기
        </button>
      </div>
      {dialogNode}
    </section>
  )
}

export default ShoppingList
