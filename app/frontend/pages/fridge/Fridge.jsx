import React from 'react'
import './Fridge.css'

import iconEgg from '../../assets/extracted/icons/icon_egg.png'
import iconMushroom from '../../assets/extracted/icons/icon_mushroom.png'
import iconOnion from '../../assets/extracted/icons/icon_onion.png'
import iconReceipt from '../../assets/extracted/icons/icon_receipt.png'
import iconRefrigerator from '../../assets/extracted/icons/icon_refrigerator.png'
import imageAlarm from '../../assets/extracted/images/image_alarm.png'
import imagePutting from '../../assets/extracted/images/image_putting.png'

const filters = [
  { label: '전체', count: 28, active: true },
  { label: '냉장', count: 18, tone: 'cold' },
  { label: '냉동', count: 7, tone: 'frozen' },
  { label: '소비 임박', count: 3, tone: 'soon' },
]

const ingredients = [
  {
    name: '대파',
    location: '야채칸',
    quantity: '1단',
    expiry: 'D-6 (05.22)',
    status: '냉장',
  },
  {
    name: '두부',
    location: '냉장칸',
    quantity: '1모',
    expiry: 'D-4 (05.20)',
    status: '임박',
    urgent: true,
  },
  {
    name: '계란',
    location: '계란칸',
    quantity: '10개',
    expiry: 'D-8 (05.24)',
    status: '냉장',
    image: iconEgg,
  },
  {
    name: '양파',
    location: '야채칸',
    quantity: '2개',
    expiry: 'D-10 (05.26)',
    status: '냉장',
    image: iconOnion,
  },
  {
    name: '버섯',
    location: '야채칸',
    quantity: '1팩',
    expiry: 'D-3 (05.19)',
    status: '임박',
    urgent: true,
    image: iconMushroom,
  },
  {
    name: '김치',
    location: '냉장칸',
    quantity: '1통',
    expiry: 'D-7 (05.23)',
    status: '냉장',
  },
  {
    name: '당근',
    location: '야채칸',
    quantity: '3개',
    expiry: 'D-9 (05.25)',
    status: '냉장',
  },
  {
    name: '토마토',
    location: '야채칸',
    quantity: '2개',
    expiry: 'D-2 (05.18)',
    status: '임박',
    urgent: true,
  },
]

function ImageSlot({ src, alt = '', className = '' }) {
  return (
    <span className={`fridge-image-slot ${src ? 'is-filled' : ''} ${className}`}>
      {src ? <img src={src} alt={alt} /> : null}
    </span>
  )
}

function Fridge() {
  return (
    <section className="fridge-page" aria-labelledby="fridge-title">
      <div className="fridge-hero">
        <div className="fridge-hero__copy">
          <h1 id="fridge-title">냉장고 재료 관리</h1>
          <p>우리 집 재료를 한눈에 관리하고, 알뜰하게 소비해요!</p>
          <label className="fridge-search" aria-label="재료명 검색">
            <span aria-hidden="true" />
            <input type="search" placeholder="재료명으로 검색해보세요" />
          </label>
        </div>

        <div className="fridge-hero__actions">
          <button className="fridge-hero-card" type="button">
            <div>
              <strong>영수증 OCR 입고</strong>
              <p>영수증 촬영으로 재료를 한 번에 등록해요</p>
            </div>
            <ImageSlot className="fridge-hero-card__image" src={iconReceipt} />
          </button>
          <button className="fridge-hero-card fridge-hero-card--add" type="button">
            <div>
              <strong>+ 재료 추가</strong>
              <p>직접 입력해서 재료를 추가해요</p>
            </div>
            <ImageSlot className="fridge-hero-card__image" src={imageAlarm} />
          </button>
        </div>

        <ImageSlot className="fridge-hero__image" src={imagePutting} />
      </div>

      <div className="fridge-layout">
        <aside className="fridge-sidebar" aria-label="냉장고 요약">
          <section className="fridge-panel fridge-summary">
            <h2>요약 정보</h2>
            <dl>
              <div>
                <dt>전체 재료</dt>
                <dd>28개</dd>
              </div>
              <div>
                <dt>냉장</dt>
                <dd>18개</dd>
              </div>
              <div>
                <dt>냉동</dt>
                <dd>7개</dd>
              </div>
              <div>
                <dt>소비 임박 (D-3↓)</dt>
                <dd>3개</dd>
              </div>
            </dl>
            <button className="fridge-soft-button" type="button">
              통계 보기
            </button>
          </section>

          <section className="fridge-panel fridge-quick">
            <h2>빠른 이동</h2>
            <ul>
              <li>
                소비 임박 재료 <strong>3</strong>
              </li>
              <li>최근 소비 내역</li>
              <li>자주 먹는 재료</li>
              <li>
                휴지통 <strong>2</strong>
              </li>
            </ul>
          </section>

          <section className="fridge-panel fridge-tip">
            <ImageSlot className="fridge-tip__image" src={imageAlarm} />
            <h2>오늘도 알뜰하게!</h2>
            <p>소비 임박 재료 3개가 있어요. 우선 소비해볼까요?</p>
          </section>
        </aside>

        <main className="fridge-main">
          <div className="fridge-toolbar">
            <div className="fridge-filters" aria-label="재료 상태 필터">
              {filters.map((filter) => (
                <button
                  className={[
                    'fridge-filter',
                    filter.active ? 'is-active' : '',
                    filter.tone ? `is-${filter.tone}` : '',
                  ]
                    .filter(Boolean)
                    .join(' ')}
                  key={filter.label}
                  type="button"
                >
                  {filter.label} ({filter.count})
                </button>
              ))}
            </div>

            <div className="fridge-view-controls">
              <button type="button">등록일 최신순</button>
              <button className="is-active" type="button" aria-label="그리드 보기">
                <span />
              </button>
              <button type="button" aria-label="리스트 보기">
                <span />
              </button>
            </div>
          </div>

          <div className="fridge-card-grid">
            {ingredients.map((item) => (
              <article className={`fridge-item ${item.urgent ? 'is-urgent' : ''}`} key={item.name}>
                <ImageSlot className="fridge-item__image" src={item.image} />
                <div className="fridge-item__body">
                  <div className="fridge-item__title">
                    <h2>{item.name}</h2>
                    <span className={item.urgent ? 'is-urgent' : ''}>{item.status}</span>
                  </div>
                  <dl>
                    <div>
                      <dt>보관 위치</dt>
                      <dd>{item.location}</dd>
                    </div>
                    <div>
                      <dt>수량</dt>
                      <dd>{item.quantity}</dd>
                    </div>
                    <div>
                      <dt>소비기한</dt>
                      <dd className={item.urgent ? 'is-danger' : ''}>{item.expiry}</dd>
                    </div>
                  </dl>
                </div>
                <div className="fridge-item__actions">
                  <button type="button">수정</button>
                  <button type="button">소비</button>
                  <button type="button">삭제</button>
                </div>
              </article>
            ))}

            <article className="fridge-add-card">
              <ImageSlot className="fridge-add-card__image" src={imageAlarm} />
              <strong>더 많은 재료를 추가해보세요!</strong>
              <button type="button">+ 재료 추가</button>
            </article>
          </div>
        </main>
      </div>

      <section className="fridge-bottom-tip">
        <strong>알뜰 팁</strong>
        <span>소비 임박 재료로 맛있는 레시피를 추천받아 보세요!</span>
        <button type="button">레시피 추천 받기</button>
        <ImageSlot className="fridge-bottom-tip__image" src={imageAlarm} />
      </section>

      <button className="fridge-floating-add" type="button" aria-label="재료 추가">
        +
      </button>
    </section>
  )
}

export default Fridge
