import React from 'react'
import { Link } from 'react-router-dom'
import './RecipeDetail.css'

import iconBasket from '../../assets/extracted/icons/icon_basket.png'
import iconEgg from '../../assets/extracted/icons/icon_egg.png'
import iconMushroom from '../../assets/extracted/icons/icon_mushroom.png'
import iconOnion from '../../assets/extracted/icons/icon_onion.png'
import imageEatRefrigerator from '../../assets/extracted/images/image_eat_refrigerator.png'
import imageRecommendation from '../../assets/extracted/images/image_recommendation.png'

const ownedIngredients = [
  { name: '대파' },
  { name: '두부' },
  { name: '계란', image: iconEgg },
  { name: '양파', image: iconOnion },
  { name: '버섯', image: iconMushroom },
  { name: '김치' },
]

const missingIngredients = [
  { name: '다진 마늘', amount: '100g' },
  { name: '고춧가루', amount: '200g' },
]

const steps = [
  { title: '재료 손질', text: '대파, 양파, 버섯을 먹기 좋게 썰고 두부는 한 입 크기로 썰어주세요.' },
  { title: '대파 볶기', text: '냄비에 대파를 넣고 중불에서 향이 날 때까지 볶아주세요.' },
  { title: '양파, 버섯 볶기', text: '양파와 버섯을 넣고 함께 2분 정도 볶아주세요.' },
  { title: '물 붓고 끓이기', text: '물과 육수 또는 물을 붓고 끓여주세요.' },
]

function ImageSlot({ src, alt = '', className = '' }) {
  return (
    <span className={`recipe-detail-image-slot ${src ? 'is-filled' : ''} ${className}`}>
      {src ? <img src={src} alt={alt} /> : null}
    </span>
  )
}

function RecipeDetail() {
  return (
    <section className="recipe-detail-page" aria-labelledby="recipe-detail-title">
      <Link className="recipe-detail-mobile-back" to="/recipes" aria-label="레시피 목록으로 돌아가기">
        <span aria-hidden="true" />
      </Link>

      <div className="recipe-detail-hero">
        <div className="recipe-detail-gallery">
          <div className="recipe-detail-main-image">
            <ImageSlot src={imageEatRefrigerator} />
            <button type="button" aria-label="레시피 저장">
              ♡
            </button>
          </div>
          <div className="recipe-detail-thumbs">
            {[0, 1, 2, 3].map((item) => (
              <ImageSlot className="recipe-detail-thumb" key={item} src={item === 0 ? imageEatRefrigerator : null} />
            ))}
            <button type="button">레시피 영상 보기</button>
          </div>
        </div>

        <div className="recipe-detail-summary">
          <h1 id="recipe-detail-title">대파 두부 계란찌개</h1>
          <p>시원한 대파와 부드러운 두부, 계란이 어우러진 간단하고 든든한 집밥 찌개예요.</p>

          <div className="recipe-detail-meta" aria-label="레시피 정보">
            <span>조리 시간 20분</span>
            <span>2인분</span>
            <span>쉬움</span>
          </div>

          <section className="recipe-detail-match">
            <div>
              <strong>냉장고 매칭률</strong>
              <p>보유 재료를 기반으로 추천해요</p>
            </div>
            <b>78%</b>
            <ImageSlot className="recipe-detail-match__image" src={imageRecommendation} />
            <span aria-hidden="true" />
          </section>
        </div>

        <aside className="recipe-detail-score">
          <h2>매칭률은 어떻게 계산되나요?</h2>
          <p>보유 재료와 레시피에 필요한 재료를 비교해 매칭률을 계산해요.</p>
          <ul>
            <li>
              보유 재료 일치 <strong>+60%</strong>
            </li>
            <li>
              유사 재료 대체 <strong>+20%</strong>
            </li>
            <li>
              조미료/기본 재료 보유 <strong>+20%</strong>
            </li>
          </ul>
          <button type="button">자세히 알아보기</button>
        </aside>
      </div>

      <div className="recipe-detail-grid">
        <section className="recipe-detail-panel recipe-detail-ingredients" aria-labelledby="ingredients-title">
          <div className="recipe-detail-panel__title">
            <h2 id="ingredients-title">필요 재료</h2>
            <span>2인분 기준</span>
            <button type="button">재료 수정</button>
          </div>

          <div className="recipe-detail-ingredient-group">
            <h3>보유 재료 (6)</h3>
            <div className="recipe-detail-ingredient-list">
              {ownedIngredients.map((item) => (
                <article key={item.name}>
                  <ImageSlot className="recipe-detail-ingredient__image" src={item.image} />
                  <strong>{item.name}</strong>
                  <span>보유</span>
                </article>
              ))}
            </div>
          </div>

          <div className="recipe-detail-ingredient-group is-missing">
            <h3>부족 재료 (2)</h3>
            <div className="recipe-detail-ingredient-list">
              {missingIngredients.map((item) => (
                <article key={item.name}>
                  <ImageSlot className="recipe-detail-ingredient__image" />
                  <strong>{item.name}</strong>
                  <span>부족</span>
                </article>
              ))}
            </div>
          </div>

          <div className="recipe-detail-tip">
            <strong>Tip.</strong>
            <p>냉장고에 있는 재료로 김치찌개, 된장찌개도 추천해요!</p>
            <button type="button">추천 레시피 보기</button>
          </div>
        </section>

        <aside className="recipe-detail-panel recipe-detail-shopping" aria-labelledby="shopping-title">
          <div>
            <h2 id="shopping-title">부족 재료 장보기</h2>
            <p>2가지 부족 재료를 한 번에 구매해요.</p>
          </div>
          <ImageSlot className="recipe-detail-shopping__image" src={iconBasket} />
          <ul>
            {missingIngredients.map((item) => (
              <li key={item.name}>
                <span>{item.name} ({item.amount})</span>
                <strong>1개</strong>
              </li>
            ))}
          </ul>
          <button className="recipe-detail-primary" type="button">
            부족 재료 장보기
          </button>
          <button className="recipe-detail-secondary" type="button">
            장바구니 담기
          </button>
        </aside>
      </div>

      <section className="recipe-detail-panel recipe-detail-steps" aria-labelledby="steps-title">
        <div className="recipe-detail-panel__title">
          <h2 id="steps-title">조리 순서 미리보기</h2>
          <span>전체 6단계</span>
        </div>
        <div className="recipe-detail-step-list">
          {steps.map((step, index) => (
            <article key={step.title}>
              <span>{index + 1}</span>
              <ImageSlot className="recipe-detail-step__image" src={index === 0 ? null : imageEatRefrigerator} />
              <div>
                <h3>{step.title}</h3>
                <p>{step.text}</p>
              </div>
            </article>
          ))}
        </div>
      </section>

      <div className="recipe-detail-actions">
        <button className="recipe-detail-primary" type="button">
          조리 시작
        </button>
        <button className="recipe-detail-secondary" type="button">
          재료 수정
        </button>
      </div>
    </section>
  )
}

export default RecipeDetail
