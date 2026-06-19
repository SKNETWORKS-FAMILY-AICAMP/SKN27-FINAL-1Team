import React from 'react'
import { Link } from 'react-router-dom'
import './FridgeRecipe.css'

import iconBasket from '../../assets/extracted/icons/icon_basket.png'
import iconOnion from '../../assets/extracted/icons/icon_onion.png'
import iconRefrigerator from '../../assets/extracted/icons/icon_refrigerator.png'
import imageEatRefrigerator from '../../assets/extracted/images/image_eat_refrigerator.png'
import imageHello from '../../assets/extracted/images/image_hello.png'
import imageMenuRecommendation from '../../assets/extracted/images/image_menu_recommendation.png'
import imagePutting from '../../assets/extracted/images/image_putting.png'

const summary = [
  { label: '보유 재료', value: '18개', note: '전체 재료 보기', image: iconRefrigerator },
  { label: '소비 임박 재료', value: '4개', note: 'D-3 이하', image: iconOnion },
  { label: '오늘의 추천', value: '6개', note: '업데이트 09:30' },
  { label: '예상 절약', value: '8,400원', note: '평균 1,400원/식' },
]

const tabs = ['전체 추천 (6)', '소비 임박 우선 (3)', '재료 많이 활용 (2)', '간단 요리 (2)']

const recommendations = [
  {
    title: '대파 두부 계란찌개',
    category: '임박 재료 사용',
    time: '20분',
    level: '쉬움',
    people: '2인분',
    match: '93%',
    reason: '대파가 D-1이라 먼저 사용할 수 있어요. 보유 재료 7/8개로 간단하게 만들 수 있어요.',
    missing: ['된장 1큰술'],
    image: imageEatRefrigerator,
  },
  {
    title: '돼지고기 간장볶음',
    category: '보유 재료 활용',
    time: '15분',
    level: '쉬움',
    people: '2인분',
    match: '89%',
    reason: '돼지고기, 양파 등 보유 재료를 많이 활용할 수 있어서 알뜰해요.',
    missing: ['간장 1큰술', '식용유 1큰술'],
  },
  {
    title: '토마토 파스타',
    category: '간단 요리',
    time: '15분',
    level: '쉬움',
    people: '2인분',
    match: '82%',
    reason: '토마토가 D-2라 맛있을 때 사용할 수 있어요. 한 번에 뚝딱!',
    missing: ['파스타면 100g', '올리브오일 1큰술'],
  },
]

const process = [
  '보유 재료 기반 추천',
  '소비 임박 재료 우선',
  '추천 이유 표시',
  '부족 재료 계산',
]

function ImageSlot({ src, alt = '', className = '' }) {
  return (
    <span className={`fridge-recipe-image-slot ${src ? 'is-filled' : ''} ${className}`}>
      {src ? <img src={src} alt={alt} /> : null}
    </span>
  )
}

function FridgeRecipe() {
  return (
    <section className="fridge-recipe-page" aria-labelledby="fridge-recipe-title">
      <div className="fridge-recipe-hero">
        <div className="fridge-recipe-hero__copy">
          <h1 id="fridge-recipe-title">냉장고파먹기</h1>
          <p>오늘 냉장고에 있는 재료와 소비 임박 재료를 우선 활용할 수 있는 레시피를 추천해드려요!</p>
        </div>
        <ImageSlot className="fridge-recipe-hero__image" src={imageMenuRecommendation} />
      </div>

      <div className="fridge-recipe-summary" aria-label="냉장고파먹기 요약">
        {summary.map((item) => (
          <article className="fridge-recipe-summary-card" key={item.label}>
            <ImageSlot className="fridge-recipe-summary-card__image" src={item.image} />
            <div>
              <span>{item.label}</span>
              <strong>{item.value}</strong>
              <p>{item.note}</p>
            </div>
          </article>
        ))}
      </div>

      <div className="fridge-recipe-content">
        <main>
          <div className="fridge-recipe-toolbar">
            <div className="fridge-recipe-tabs" aria-label="추천 필터">
              {tabs.map((tab, index) => (
                <button className={index === 0 ? 'is-active' : ''} type="button" key={tab}>
                  {tab}
                </button>
              ))}
            </div>
            <select aria-label="정렬">
              <option>추천순</option>
            </select>
          </div>

          <div className="fridge-recipe-grid">
            {recommendations.map((recipe) => (
              <article className="fridge-recipe-card" key={recipe.title}>
                <div className="fridge-recipe-card__media">
                  <span>{recipe.category}</span>
                  <button type="button" aria-label={`${recipe.title} 저장`}>
                    ♡
                  </button>
                  <ImageSlot className="fridge-recipe-card__image" src={recipe.image} />
                </div>

                <div className="fridge-recipe-card__body">
                  <h2>{recipe.title}</h2>
                  <p className="fridge-recipe-card__meta">
                    {recipe.time} · {recipe.level} · {recipe.people}
                  </p>
                  <strong className="fridge-recipe-card__match">냉장고 매칭률 {recipe.match}</strong>

                  <div className="fridge-recipe-card__reason">
                    <b>추천 이유</b>
                    <p>{recipe.reason}</p>
                  </div>

                  <div className="fridge-recipe-card__missing">
                    <span>부족 재료 ({recipe.missing.length})</span>
                    <div>
                      {recipe.missing.map((item) => (
                        <em key={item}>{item}</em>
                      ))}
                    </div>
                  </div>

                  <div className="fridge-recipe-card__actions">
                    <Link to="/recipes/green-onion-tofu-egg-stew">레시피 보기</Link>
                    <Link to="/shopping-list">장보기 이동</Link>
                  </div>
                </div>
              </article>
            ))}
          </div>
        </main>

        <aside className="fridge-recipe-process" aria-labelledby="process-title">
          <h2 id="process-title">추천은 이렇게 진행돼요!</h2>
          <ol>
            {process.map((item, index) => (
              <li key={item}>
                <span>{index + 1}</span>
                <strong>{item}</strong>
                <p>
                  {index === 0 && '냉장고에 있는 재료로 만들 수 있는 요리를 찾아요.'}
                  {index === 1 && 'D-3 이하 재료를 먼저 사용할 수 있도록 추천해요.'}
                  {index === 2 && '왜 이 레시피가 추천됐는지 이유를 알려드려요.'}
                  {index === 3 && '부족한 재료를 계산해서 장보기로 바로 연결돼요.'}
                </p>
              </li>
            ))}
          </ol>
        </aside>
      </div>

      <section className="fridge-recipe-cta">
        <ImageSlot className="fridge-recipe-cta__fridge" src={imagePutting} />
        <div>
          <h2>오늘의 재료로 맛있는 한 끼 어때요?</h2>
          <p>냉장고를 비우고, 절약까지! 오늘이 딱 좋은 날이에요.</p>
        </div>
        <ImageSlot className="fridge-recipe-cta__mascot" src={imageHello} />
        <Link to="/recipes/green-onion-tofu-egg-stew">오늘 요리 시작하기</Link>
      </section>
    </section>
  )
}

export default FridgeRecipe
