import React from 'react'
import './ShoppingList.css'

import iconBasket from '../../assets/extracted/icons/icon_basket.png'
import iconCart from '../../assets/extracted/icons/icon_cart.png'
import iconEgg from '../../assets/extracted/icons/icon_egg.png'
import iconOnion from '../../assets/extracted/icons/icon_onion.png'
import iconRefrigerator from '../../assets/extracted/icons/icon_refrigerator.png'
import imageShop from '../../assets/extracted/images/image_shop.png'

const summaryCards = [
  { label: '부족 재료', value: '7개', note: '3개 레시피 기준', image: iconBasket },
  { label: '예상 총액', value: '16,250원', note: '배송비 포함 최저가' },
  { label: '배달 대비 절약', value: '8,400원', note: '배달가 24,650원 대비', accent: true },
  { label: '원가율', value: '32%', note: '1인분 기준' },
  { label: '최저가 구매처', value: '마켓컬리', note: '배송비 포함 기준', image: iconCart },
]

const shoppingItems = [
  { name: '대파', detail: '국내산', quantity: '1대', recipe: '대파 두부 계란찌개' },
  { name: '두부', detail: '부침/찌개용', quantity: '1모', recipe: '대파 두부 계란찌개' },
  { name: '계란', detail: '특란', quantity: '10개', recipe: '대파 두부 계란찌개', image: iconEgg },
  { name: '양파', detail: '국내산', quantity: '2개', recipe: '김치볶음밥', image: iconOnion },
  { name: '김치', detail: '배추김치', quantity: '1통 (300g)', recipe: '김치볶음밥' },
  { name: '참기름', detail: '오뚜기', quantity: '1병', recipe: '김치볶음밥' },
  { name: '김가루', detail: '조미김', quantity: '1봉', recipe: '김치볶음밥' },
]

const priceRows = [
  { name: '대파 (1대)', marketA: '1,900원', marketB: '1,490원', best: '1,490원', diff: '-410원' },
  { name: '두부 (1모)', marketA: '2,300원', marketB: '1,980원', best: '1,980원', diff: '-320원' },
  { name: '계란 (10개)', marketA: '2,980원', marketB: '2,780원', best: '2,780원', diff: '-200원' },
  { name: '양파 (2개)', marketA: '1,980원', marketB: '1,780원', best: '1,780원', diff: '-200원' },
  { name: '김치 (300g)', marketA: '2,980원', marketB: '2,500원', best: '2,500원', diff: '-480원' },
  { name: '참기름 (1병)', marketA: '3,200원', marketB: '2,980원', best: '2,980원', diff: '-220원' },
  { name: '김가루 (1봉)', marketA: '1,400원', marketB: '1,200원', best: '1,200원', diff: '-200원' },
]

function ImageSlot({ src, alt = '', className = '' }) {
  return (
    <span className={`shopping-image-slot ${src ? 'is-filled' : ''} ${className}`}>
      {src ? <img src={src} alt={alt} /> : null}
    </span>
  )
}

function ShoppingList() {
  return (
    <section className="shopping-page" aria-labelledby="shopping-title">
      <div className="shopping-hero">
        <div className="shopping-hero__copy">
          <h1 id="shopping-title">장보기</h1>
          <p>추천 레시피의 부족 재료를 모아 최저가로 똑똑하게 장볼어요!</p>
        </div>
        <div className="shopping-hero__art" aria-hidden="true">
          <img src={imageShop} alt="" />
        </div>
      </div>

      <div className="shopping-summary" aria-label="장보기 요약">
        {summaryCards.map((card) => (
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

      <div className="shopping-main-grid">
        <section className="shopping-panel shopping-list-panel" aria-labelledby="shopping-list-title">
          <div className="shopping-panel__header">
            <div>
              <h2 id="shopping-list-title">부족 재료 목록</h2>
              <p>체크 후 수량을 조절하고 장바구니에 담아보세요.</p>
            </div>
            <button className="shopping-soft-button" type="button">
              추천 레시피 보기
            </button>
          </div>

          <div className="shopping-items">
            <div className="shopping-items__head">
              <span>전체 선택</span>
              <span>재료</span>
              <span>필요 수량</span>
              <span>사용 레시피</span>
            </div>
            {shoppingItems.map((item) => (
              <article className="shopping-item" key={item.name}>
                <span className="shopping-check" aria-hidden="true" />
                <div className="shopping-item__ingredient">
                  <ImageSlot className="shopping-item__image" src={item.image} />
                  <div>
                    <strong>{item.name}</strong>
                    <p>{item.detail}</p>
                  </div>
                </div>
                <div className="shopping-quantity" aria-label={`${item.name} 수량`}>
                  <button type="button">-</button>
                  <span>{item.quantity}</span>
                  <button type="button">+</button>
                </div>
                <span className="shopping-recipe-chip">{item.recipe}</span>
              </article>
            ))}
          </div>

          <button className="shopping-add-button" type="button">
            + 직접 재료 추가
          </button>
          <p className="shopping-tip">대파와 김치는 묶음 구매 시 평균 8% 절약할 수 있어요!</p>
        </section>

        <section className="shopping-panel shopping-price-panel" aria-labelledby="price-title">
          <div className="shopping-panel__header">
            <div>
              <h2 id="price-title">구매처별 가격 비교</h2>
              <p>배송비 포함 기준</p>
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
            <strong>최저가 구매처: 쿠팡 (15,690원)</strong>
            <button className="shopping-soft-button" type="button">
              최저가 장바구니 담기
            </button>
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
                <strong>15,690원</strong>
              </span>
              <span>
                배달 예상가
                <strong>24,090원</strong>
              </span>
              <em>8,400원</em>
            </div>
          </div>
        </section>

        <section className="shopping-panel shopping-cost" aria-labelledby="cost-title">
          <h2 id="cost-title">원가율 계산</h2>
          <div className="shopping-cost__flow">
            <span>
              재료비
              <strong>5,220원</strong>
            </span>
            <b>+</b>
            <span>
              기타 비용
              <strong>760원</strong>
            </span>
            <b>=</b>
            <span>
              총 원가
              <strong>5,980원</strong>
            </span>
            <em>32%</em>
          </div>
        </section>
      </div>

      <div className="shopping-actions">
        <button className="shopping-soft-action" type="button">
          레시피 상세 보기
        </button>
        <button className="shopping-soft-action" type="button">
          최저가 마켓 바로가기
        </button>
        <button className="shopping-primary-action" type="button">
          구매 완료하고 냉장고 입고
          <ImageSlot className="shopping-primary-action__icon" src={iconRefrigerator} />
        </button>
        <button className="shopping-soft-action" type="button">
          장바구니 담기
        </button>
      </div>
    </section>
  )
}

export default ShoppingList
