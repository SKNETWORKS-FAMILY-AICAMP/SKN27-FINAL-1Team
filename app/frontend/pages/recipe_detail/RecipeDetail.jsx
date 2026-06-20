import React, { useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import './RecipeDetail.css'

import iconBasket from '../../assets/extracted/icons/icon_basket.png'
import imageEatRefrigerator from '../../assets/extracted/images/image_eat_refrigerator.png'
import { useAppDialog } from '../../components/AppDialog.jsx'
import { missingIngredients, ownedIngredients, recipeSteps as steps } from '../../mock/recipeDetailMock.js'
import { userProfile } from '../../mock/userService.js'

function ImageSlot({ src, alt = '', className = '' }) {
  return (
    <span className={`recipe-detail-image-slot ${src ? 'is-filled' : ''} ${className}`}>
      {src ? <img src={src} alt={alt} /> : null}
    </span>
  )
}

function RecipeDetail() {
  const navigate = useNavigate()
  const { dialogNode, showAlert } = useAppDialog()
  const stepsRef = useRef(null)
  const [isSaved, setIsSaved] = useState(false)
  const [isCooking, setIsCooking] = useState(false)
  const [currentStep, setCurrentStep] = useState(0)
  const [isCooked, setIsCooked] = useState(false)

  const checkedCount = ownedIngredients.length
  const isLastStep = currentStep >= steps.length - 1

  const startCooking = () => {
    setIsCooking(true)
    setIsCooked(false)
    setCurrentStep(0)
    stepsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  const moveCookingStep = (direction) => {
    setCurrentStep((prev) => Math.max(0, Math.min(prev + direction, steps.length - 1)))
  }

  const completeStep = () => {
    if (isLastStep) {
      setIsCooked(true)
      setIsCooking(false)
      window.localStorage.setItem('bobbeori-last-cooked-recipe', '대파 두부 계란찌개')
      return
    }

    setCurrentStep((prev) => prev + 1)
  }

  return (
    <section className="recipe-detail-page" aria-labelledby="recipe-detail-title">
      <Link className="recipe-detail-mobile-back" to="/recipes" aria-label="레시피 목록으로 돌아가기">
        <span aria-hidden="true" />
      </Link>

      <div className="recipe-detail-hero">
        <div className="recipe-detail-gallery">
          <div className="recipe-detail-main-image">
            <ImageSlot src={imageEatRefrigerator} />
            <button
              type="button"
              aria-label="레시피 저장"
              aria-pressed={isSaved}
              onClick={() => setIsSaved((prev) => !prev)}
            >
              {isSaved ? '♥' : '♡'}
            </button>
          </div>
        </div>

        <div className="recipe-detail-summary">
          <h1 id="recipe-detail-title">대파 두부 계란찌개</h1>
          <p>
            {userProfile.mealTarget}에 맞춰 {userProfile.cookTime} 안에 만들 수 있고,
            {userProfile.taste} 먹기 좋은 든든한 집밥 찌개예요.
          </p>
          <button
            className="recipe-detail-video-button"
            type="button"
            onClick={() => showAlert('레시피 영상은 준비 중입니다.', {
              title: '준비 중이에요',
            })}
          >
            레시피 영상 보기
          </button>

          <div className="recipe-detail-meta" aria-label="레시피 정보">
            <span>조리 시간 20분</span>
            <span>1인분</span>
            <span>쉬움</span>
            <span>재료 확인 {checkedCount}/{ownedIngredients.length}</span>
          </div>
        </div>
      </div>

      <div className="recipe-detail-grid">
        <section className="recipe-detail-panel recipe-detail-ingredients" aria-labelledby="ingredients-title">
          <div className="recipe-detail-panel__title">
            <h2 id="ingredients-title">필요 재료</h2>
            <span>1인분 기준</span>
          </div>

          <div className="recipe-detail-ingredient-group">
            <h3>보유 재료 (6)</h3>
            <div className="recipe-detail-ingredient-list">
              {ownedIngredients.map((item) => (
                <article
                  className="is-checked"
                  key={item.name}
                >
                  <ImageSlot className="recipe-detail-ingredient__image" src={item.image} />
                  <div className="recipe-detail-ingredient__info">
                    <strong>{item.name}</strong>
                    <small>{item.amount}</small>
                  </div>
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
                  <div className="recipe-detail-ingredient__info">
                    <strong>{item.name}</strong>
                    <small>{item.amount}</small>
                  </div>
                </article>
              ))}
            </div>
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
          <button className="recipe-detail-primary" type="button" onClick={() => navigate('/shopping-list')}>
            부족 재료 장보기
          </button>
          <button
            className="recipe-detail-secondary"
            type="button"
            onClick={() => showAlert('장바구니에 부족 재료를 담았어요.', {
              title: '장바구니 담기',
            })}
          >
            장바구니 담기
          </button>
        </aside>
      </div>

      <section className="recipe-detail-panel recipe-detail-steps" aria-labelledby="steps-title" ref={stepsRef}>
        <div className="recipe-detail-panel__title">
          <h2 id="steps-title">{isCooking ? '조리 진행' : '조리 순서 미리보기'}</h2>
          <span>전체 {steps.length}단계</span>
        </div>
        <article className={`recipe-detail-current-step ${isCooked ? 'is-complete' : ''}`}>
          <span>{isCooked ? '완료' : `${currentStep + 1}/${steps.length}`}</span>
          <div>
            <h3>{isCooked ? '맛있게 완성했어요' : steps[currentStep].title}</h3>
            <p>{isCooked ? '조리 기록이 저장됐고, 다음 추천으로 이어갈 수 있어요.' : steps[currentStep].text}</p>
          </div>
          <div className="recipe-detail-current-step__actions">
            <button type="button" disabled={currentStep === 0 || isCooked} onClick={() => moveCookingStep(-1)}>
              이전
            </button>
            <button type="button" disabled={isCooked} onClick={completeStep}>
              {isLastStep ? '요리 완료' : '다음 단계'}
            </button>
          </div>
        </article>
        <div className="recipe-detail-step-list">
          {steps.map((step, index) => (
            <article
              className={[
                index === currentStep && !isCooked ? 'is-active' : '',
                index < currentStep || isCooked ? 'is-done' : '',
              ]
                .filter(Boolean)
                .join(' ')}
              key={step.title}
              onClick={() => {
                setCurrentStep(index)
                setIsCooking(true)
                setIsCooked(false)
              }}
            >
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

      {dialogNode}
    </section>
  )
}

export default RecipeDetail
