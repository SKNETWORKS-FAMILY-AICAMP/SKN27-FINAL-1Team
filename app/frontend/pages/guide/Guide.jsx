import React from 'react'
import './Guide.css'

import iconBasket from '../../assets/extracted/icons/icon_basket.png'
import iconEgg from '../../assets/extracted/icons/icon_egg.png'
import iconMushroom from '../../assets/extracted/icons/icon_mushroom.png'
import iconOnion from '../../assets/extracted/icons/icon_onion.png'
import iconRefrigerator from '../../assets/extracted/icons/icon_refrigerator.png'
import imageGuide from '../../assets/extracted/images/image_guide.png'

const ingredients = [
  { name: '대파', active: true },
  { name: '두부' },
  { name: '계란', image: iconEgg },
  { name: '양파', image: iconOnion },
  { name: '버섯', image: iconMushroom },
  { name: '김치' },
]

const guideTips = [
  {
    title: '보관방법',
    points: [
      '냉장 보관이 좋아요.',
      '키친타월로 감싼 뒤 지퍼백이나 밀폐용기에 넣어 보관하세요.',
      '신문지로 감싸면 수분 손실을 줄일 수 있어요.',
    ],
    chip: '보관 온도 : 0~5°C',
  },
  {
    title: '손질방법',
    points: [
      '뿌리의 지저분한 부분을 잘라내요.',
      '시든 겉잎은 제거하고 활용할 부분만 준비해요.',
      '흰 부분과 초록 부분은 용도에 맞게 나눠 사용해요.',
    ],
    chip: '흰 부분은 국물 요리에 좋아요',
  },
  {
    title: '세척방법',
    points: [
      '흐르는 물에 흙과 이물질을 꼼꼼히 씻어요.',
      '뿌리 부분은 칼집을 살짝 내어 속까지 헹궈요.',
      '물기가 많으면 보관성이 떨어져요.',
    ],
    chip: '흐르는 물 사용 추천',
  },
  {
    title: '신선도 확인법',
    points: [
      '잎이 선명한 초록색이고 시들지 않았는지 확인해요.',
      '줄기가 단단하고 윤기가 있는지 살펴봐요.',
      '갈변이 넓게 보이면 신선도가 낮아요.',
    ],
    chip: '진액이 나오면 신선해요',
  },
]

const fridgeRows = [
  { label: '보유 수량', value: '2대' },
  { label: '보관 위치', value: '냉장실 (야채칸)', highlight: true },
  { label: '소비기한', value: 'D-5 (05.22)', danger: true },
  { label: '소비 임박 알림', value: '임박', badge: true },
  { label: '연결된 추천 레시피', value: '7개' },
]

const recipes = [
  { title: '대파 두부 계란찌개', meta: '20분 · 쉬움 · 보유 재료 7/10' },
  { title: '대파 파스타', meta: '25분 · 보통 · 보유 재료 6/9' },
  { title: '대파 삼겹살 구이', meta: '30분 · 쉬움 · 보유 재료 5/8' },
]

function ImageSlot({ src, alt, className = '' }) {
  return (
    <span className={`guide-image-slot ${src ? 'is-filled' : ''} ${className}`}>
      {src ? <img src={src} alt={alt} /> : null}
    </span>
  )
}

function Guide() {
  return (
    <section className="guide-page" aria-labelledby="guide-title">
      <div className="guide-hero">
        <div className="guide-hero__copy">
          <h1 id="guide-title">식재료 가이드</h1>
          <p>재료별 보관, 손질, 세척, 신선도 팁을 한눈에 확인해요!</p>
        </div>

        <label className="guide-search guide-hero__search" aria-label="식재료명 검색">
          <span aria-hidden="true" />
          <input placeholder="식재료명을 검색해보세요" type="search" />
        </label>

        <div className="guide-hero__art" aria-hidden="true">
          <img src={imageGuide} alt="" />
        </div>
      </div>

      <section className="guide-panel guide-ingredients" aria-labelledby="guide-ingredients-title">
        <div className="guide-section-title" id="guide-ingredients-title">
          내 냉장고 재료 기반
        </div>
        <div className="guide-ingredient-list" aria-label="재료 목록">
          {ingredients.map((ingredient) => (
            <button
              className={`guide-ingredient ${ingredient.active ? 'is-active' : ''}`}
              key={ingredient.name}
              type="button"
            >
              <ImageSlot alt="" className="guide-ingredient__image" src={ingredient.image} />
              <span>{ingredient.name}</span>
            </button>
          ))}
          <button className="guide-more-button" type="button" aria-label="재료 더 보기">
            <span aria-hidden="true" />
          </button>
        </div>
      </section>

      <div className="guide-content-grid">
        <article className="guide-panel guide-detail">
          <div className="guide-detail__header">
            <ImageSlot alt="" className="guide-detail__image" />
            <div>
              <h2>대파</h2>
              <p>알싸한 향과 달큰한 맛으로 요리에 깊은 풍미를 더해요.</p>
              <span className="guide-owned-badge">내 냉장고에 있어요</span>
            </div>
            <button className="guide-soft-button guide-detail__more" type="button">
              다른 재료 보기
            </button>
          </div>

          <div className="guide-tip-grid">
            {guideTips.map((tip) => (
              <section className="guide-tip-card" key={tip.title}>
                <div className="guide-tip-card__title">
                  <span aria-hidden="true" />
                  <h3>{tip.title}</h3>
                </div>
                <ul>
                  {tip.points.map((point) => (
                    <li key={point}>{point}</li>
                  ))}
                </ul>
                <strong>{tip.chip}</strong>
              </section>
            ))}
          </div>
        </article>

        <aside className="guide-panel guide-fridge" aria-labelledby="guide-fridge-title">
          <div className="guide-fridge__title">
            <ImageSlot alt="" className="guide-fridge__icon" src={iconRefrigerator} />
            <h2 id="guide-fridge-title">냉장고 연결</h2>
          </div>

          <dl className="guide-fridge__list">
            {fridgeRows.map((row) => (
              <div className="guide-fridge__row" key={row.label}>
                <dt>{row.label}</dt>
                <dd
                  className={[
                    row.highlight ? 'is-highlight' : '',
                    row.danger ? 'is-danger' : '',
                    row.badge ? 'is-badge' : '',
                  ]
                    .filter(Boolean)
                    .join(' ')}
                >
                  {row.value}
                </dd>
              </div>
            ))}
          </dl>

          <button className="guide-primary-button" type="button">
            레시피 보기
          </button>
          <button className="guide-soft-button guide-edit-button" type="button">
            재료 수정
          </button>
        </aside>
      </div>

      <section className="guide-panel guide-recipes" aria-labelledby="guide-recipes-title">
        <div className="guide-recipes__header">
          <h2 id="guide-recipes-title">연관 레시피</h2>
          <span>총 7개</span>
        </div>

        <div className="guide-recipe-list">
          {recipes.map((recipe) => (
            <article className="guide-recipe-card" key={recipe.title}>
              <ImageSlot alt="" className="guide-recipe-card__image" />
              <div>
                <h3>{recipe.title}</h3>
                <p>{recipe.meta}</p>
              </div>
            </article>
          ))}

          <article className="guide-recipe-more">
            <ImageSlot alt="" className="guide-recipe-more__icon" src={iconBasket} />
            <strong>더 많은 레시피를 확인해보세요!</strong>
            <button className="guide-primary-button" type="button">
              전체 보기
            </button>
          </article>
        </div>
      </section>
    </section>
  )
}

export default Guide
