import React, { useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import './RecipeDetail.css'

import iconBasket from '../../assets/extracted/icons/icon_basket.png'
import iconEgg from '../../assets/extracted/icons/icon_egg.png'
import iconMushroom from '../../assets/extracted/icons/icon_mushroom.png'
import iconOnion from '../../assets/extracted/icons/icon_onion.png'
import imageEatRefrigerator from '../../assets/extracted/images/image_eat_refrigerator.png'
import imageRecommendation from '../../assets/extracted/images/image_recommendation.png'
import { serviceContext, userProfile } from '../../data/userService.js'

const ownedIngredients = [
  { name: '대파', amount: '1대' },
  { name: '두부', amount: '1모' },
  { name: '계란', amount: '2개', image: iconEgg },
  { name: '양파', amount: '1/2개', image: iconOnion },
  { name: '버섯', amount: '한 줌', image: iconMushroom },
  { name: '김치', amount: '선택' },
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
  { title: '두부 넣기', text: '두부를 넣고 5분 정도 더 끓여 간이 배도록 해주세요.' },
  { title: '계란 풀기', text: '마지막에 계란을 풀고 1분만 더 끓인 뒤 불을 꺼주세요.' },
]

function ImageSlot({ src, alt = '', className = '' }) {
  return (
    <span className={`recipe-detail-image-slot ${src ? 'is-filled' : ''} ${className}`}>
      {src ? <img src={src} alt={alt} /> : null}
    </span>
  )
}

function RecipeDetail() {
  const navigate = useNavigate()
  const stepsRef = useRef(null)
  const [isSaved, setIsSaved] = useState(false)
  const [checkedIngredients, setCheckedIngredients] = useState(() =>
    ownedIngredients.map((item) => item.name),
  )
  const [isCooking, setIsCooking] = useState(false)
  const [currentStep, setCurrentStep] = useState(0)
  const [isCooked, setIsCooked] = useState(false)

  const progressPercent = Math.round(((currentStep + (isCooked ? 1 : 0)) / steps.length) * 100)
  const checkedCount = checkedIngredients.length
  const isLastStep = currentStep >= steps.length - 1

  const startCooking = () => {
    setIsCooking(true)
    setIsCooked(false)
    setCurrentStep(0)
    stepsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  const toggleIngredient = (name) => {
    setCheckedIngredients((prev) =>
      prev.includes(name) ? prev.filter((item) => item !== name) : [...prev, name],
    )
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
          <div className="recipe-detail-thumbs">
            {[0, 1, 2, 3].map((item) => (
              <ImageSlot className="recipe-detail-thumb" key={item} src={item === 0 ? imageEatRefrigerator : null} />
            ))}
            <button type="button" onClick={() => window.alert('레시피 영상은 준비 중입니다.')}>레시피 영상 보기</button>
          </div>
        </div>

        <div className="recipe-detail-summary">
          <h1 id="recipe-detail-title">대파 두부 계란찌개</h1>
          <p>
            {userProfile.mealTarget}에 맞춰 {userProfile.cookTime} 안에 만들 수 있고,
            {userProfile.taste} 먹기 좋은 든든한 집밥 찌개예요.
          </p>

          <div className="recipe-detail-meta" aria-label="레시피 정보">
            <span>조리 시간 20분</span>
            <span>2인분</span>
            <span>쉬움</span>
            <span>재료 확인 {checkedCount}/{ownedIngredients.length}</span>
          </div>

          <section className="recipe-detail-match">
            <div>
              <strong>냉장고 매칭률</strong>
              <p>{userProfile.priority} 기준으로 추천해요</p>
            </div>
            <b>{serviceContext.fridgeMatch}</b>
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
          <button type="button" onClick={() => navigate('/guide')}>자세히 알아보기</button>
        </aside>
      </div>

      <section className="recipe-detail-progress" aria-labelledby="recipe-detail-progress-title">
        <div>
          <span>{isCooked ? '조리 완료' : isCooking ? `${currentStep + 1}단계 진행 중` : '조리 준비'}</span>
          <h2 id="recipe-detail-progress-title">
            {isCooked ? '오늘 요리 완료!' : isCooking ? steps[currentStep].title : '재료를 확인하고 조리를 시작해요'}
          </h2>
          <p>
            {isCooked
              ? '완료 기록을 저장했어요. 남은 재료는 냉장고에서 이어서 관리할 수 있어요.'
              : isCooking
                ? steps[currentStep].text
                : `보유 재료 ${checkedCount}개를 확인했어요. 부족 재료는 장보기로 바로 넘길 수 있어요.`}
          </p>
        </div>
        <div className="recipe-detail-progress__bar" aria-label={`조리 진행률 ${progressPercent}%`}>
          <span style={{ width: `${progressPercent}%` }} />
        </div>
        <div className="recipe-detail-progress__actions">
          <button type="button" onClick={startCooking}>
            처음부터 조리
          </button>
          <button type="button" onClick={() => navigate('/shopping-list')}>
            부족 재료 장보기
          </button>
        </div>
      </section>

      <div className="recipe-detail-grid">
        <section className="recipe-detail-panel recipe-detail-ingredients" aria-labelledby="ingredients-title">
          <div className="recipe-detail-panel__title">
            <h2 id="ingredients-title">필요 재료</h2>
            <span>2인분 기준</span>
            <button type="button" onClick={() => navigate('/fridge')}>재료 수정</button>
          </div>

          <div className="recipe-detail-ingredient-group">
            <h3>보유 재료 (6)</h3>
            <div className="recipe-detail-ingredient-list">
              {ownedIngredients.map((item) => (
                <article
                  className={checkedIngredients.includes(item.name) ? 'is-checked' : ''}
                  key={item.name}
                >
                  <ImageSlot className="recipe-detail-ingredient__image" src={item.image} />
                  <strong>{item.name}</strong>
                  <small>{item.amount}</small>
                  <button
                    type="button"
                    aria-pressed={checkedIngredients.includes(item.name)}
                    onClick={() => toggleIngredient(item.name)}
                  >
                    {checkedIngredients.includes(item.name) ? '확인됨' : '확인'}
                  </button>
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
            <button type="button" onClick={() => navigate('/recipe-fridge')}>추천 레시피 보기</button>
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
            onClick={() => window.alert('장바구니에 부족 재료를 담았어요.')}
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

      <div className="recipe-detail-actions">
        <button className="recipe-detail-primary" type="button" onClick={startCooking}>
          {isCooking ? '조리 다시 시작' : '조리 시작'}
        </button>
        <button className="recipe-detail-secondary" type="button" onClick={() => navigate(isCooked ? '/recipe-fridge' : '/fridge')}>
          {isCooked ? '다음 추천 보기' : '재료 수정'}
        </button>
      </div>
    </section>
  )
}

export default RecipeDetail
