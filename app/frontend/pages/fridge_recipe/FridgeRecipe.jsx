import React, { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import './FridgeRecipe.css'

import iconBasket from '../../assets/extracted/icons/icon_basket.png'
import iconOnion from '../../assets/extracted/icons/icon_onion.png'
import iconRefrigerator from '../../assets/extracted/icons/icon_refrigerator.png'
import imageEatRefrigerator from '../../assets/extracted/images/image_eat_refrigerator.png'
import imageHello from '../../assets/extracted/images/image_hello.png'
import imageMenuRecommendation from '../../assets/extracted/images/image_menu_recommendation.png'
import imagePutting from '../../assets/extracted/images/image_putting.png'
import { serviceBadges, serviceContext, userProfile } from '../../data/userService.js'

const tabs = ['전체 추천 (3)', '소비 임박 우선 (2)', '재료 많이 활용 (2)', '간단 요리 (2)']

const recommendations = [
  {
    id: 'green-onion-tofu-egg-stew',
    title: '대파 두부 계란찌개',
    category: '임박 재료 사용',
    time: '20분',
    minutes: 20,
    level: '쉬움',
    people: '2인분',
    match: 93,
    owned: 7,
    total: 8,
    expiresSoon: true,
    saveEstimate: '8,400원 절약',
    reason: '대파가 D-1이라 먼저 사용할 수 있어요. 보유 재료 7/8개로 간단하게 만들 수 있어요.',
    missing: ['된장 1큰술'],
    image: imageEatRefrigerator,
  },
  {
    id: 'pork-soy-stir-fry',
    title: '돼지고기 간장볶음',
    category: '보유 재료 활용',
    time: '15분',
    minutes: 15,
    level: '쉬움',
    people: '2인분',
    match: 89,
    owned: 6,
    total: 8,
    expiresSoon: false,
    saveEstimate: '6,200원 절약',
    reason: '돼지고기, 양파 등 보유 재료를 많이 활용할 수 있어서 알뜰해요.',
    missing: ['간장 1큰술', '식용유 1큰술'],
  },
  {
    id: 'tomato-pasta',
    title: '토마토 파스타',
    category: '간단 요리',
    time: '15분',
    minutes: 15,
    level: '쉬움',
    people: '2인분',
    match: 82,
    owned: 5,
    total: 7,
    expiresSoon: true,
    saveEstimate: '5,800원 절약',
    reason: '토마토가 D-2라 맛있을 때 사용할 수 있어요. 한 번에 뚝딱 만들 수 있어요.',
    missing: ['파스타면 100g', '올리브오일 1큰술'],
  },
]

const process = [
  {
    title: '보유 재료 스캔',
    description: '냉장고에 있는 재료와 수량을 확인해요.',
  },
  {
    title: '소비 임박 우선 계산',
    description: 'D-3 이하 재료가 들어가는 메뉴에 가중치를 줘요.',
  },
  {
    title: '취향과 예산 반영',
    description: `${userProfile.cookTime}, ${userProfile.budgetLabel}, ${userProfile.taste} 조건을 반영해요.`,
  },
  {
    title: '부족 재료 장보기 연결',
    description: '없는 재료만 골라 장보기 목록으로 넘겨요.',
  },
]

function ImageSlot({ src, alt = '', className = '' }) {
  return (
    <span className={`fridge-recipe-image-slot ${src ? 'is-filled' : ''} ${className}`}>
      {src ? <img src={src} alt={alt} /> : null}
    </span>
  )
}

function FridgeRecipe() {
  const navigate = useNavigate()
  const flowTimersRef = useRef([])
  const [activeTab, setActiveTab] = useState(tabs[0])
  const [sortMode, setSortMode] = useState('recommend')
  const [savedIds, setSavedIds] = useState([])
  const [selectedRecipeId, setSelectedRecipeId] = useState(recommendations[0].id)
  const [activeStep, setActiveStep] = useState(0)
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [isRecommendationReady, setIsRecommendationReady] = useState(true)

  const selectedRecipe = recommendations.find((recipe) => recipe.id === selectedRecipeId) ?? recommendations[0]
  const progressPercent = Math.round(((activeStep + (isRecommendationReady ? 1 : 0)) / process.length) * 100)

  const visibleRecommendations = useMemo(() => {
    let next = [...recommendations]

    if (activeTab.includes('소비 임박')) {
      next = next.filter((recipe) => recipe.expiresSoon)
    }

    if (activeTab.includes('재료 많이')) {
      next = next.filter((recipe) => recipe.owned >= 6)
    }

    if (activeTab.includes('간단')) {
      next = next.filter((recipe) => recipe.minutes <= 15)
    }

    if (sortMode === 'match') {
      next.sort((a, b) => b.match - a.match)
    }

    if (sortMode === 'time') {
      next.sort((a, b) => a.minutes - b.minutes)
    }

    if (sortMode === 'saving') {
      next.sort((a, b) => b.owned - a.owned)
    }

    return next
  }, [activeTab, sortMode])

  const summary = [
    { label: '보유 재료', value: '18개', note: '전체 재료 보기', image: iconRefrigerator, onClick: () => navigate('/fridge') },
    { label: '소비 임박', value: `${serviceContext.urgentIngredientCount}개`, note: 'D-3 이하', image: iconOnion, onClick: () => setActiveTab(tabs[1]) },
    { label: '오늘 추천', value: `${recommendations.length}개`, note: userProfile.mealTarget, onClick: () => startRecommendation() },
    { label: '선택 메뉴', value: `${selectedRecipe.match}%`, note: selectedRecipe.title, image: iconBasket, onClick: () => navigate(`/recipes/${selectedRecipe.id}`) },
  ]

  const clearFlowTimers = () => {
    flowTimersRef.current.forEach((timerId) => window.clearTimeout(timerId))
    flowTimersRef.current = []
  }

  const startRecommendation = () => {
    clearFlowTimers()
    setActiveStep(0)
    setIsAnalyzing(true)
    setIsRecommendationReady(false)

    flowTimersRef.current = process.slice(1).map((_, index) =>
      window.setTimeout(() => {
        setActiveStep(index + 1)
      }, 600 * (index + 1)),
    )

    flowTimersRef.current.push(
      window.setTimeout(() => {
        setIsAnalyzing(false)
        setIsRecommendationReady(true)
        setActiveTab(tabs[1])
        setSelectedRecipeId(recommendations[0].id)
      }, 600 * process.length),
    )
  }

  const toggleSaved = (recipeId) => {
    setSavedIds((prev) =>
      prev.includes(recipeId) ? prev.filter((id) => id !== recipeId) : [...prev, recipeId],
    )
  }

  const selectRecipe = (recipe) => {
    setSelectedRecipeId(recipe.id)
    setIsRecommendationReady(true)
    window.localStorage.setItem('bobbeori-selected-recipe', recipe.title)
  }

  const goShopping = (recipe) => {
    window.localStorage.setItem('bobbeori-shopping-recipe', recipe.title)
    window.localStorage.setItem('bobbeori-shopping-missing', JSON.stringify(recipe.missing))
    navigate('/shopping-list')
  }

  useEffect(() => clearFlowTimers, [])

  return (
    <section className="fridge-recipe-page" aria-labelledby="fridge-recipe-title">
      <div className="fridge-recipe-hero">
        <div className="fridge-recipe-hero__copy">
          <h1 id="fridge-recipe-title">{userProfile.mealTarget} 맞춤 추천</h1>
          <p>
            {userProfile.household}, {userProfile.cookTime}, {userProfile.budgetLabel} 기준으로
            소비 임박 재료를 먼저 쓰는 레시피를 추천해드려요.
          </p>
          <div className="fridge-recipe-service-tags" aria-label="추천 기준">
            {serviceBadges.map((badge) => (
              <span key={badge}>{badge}</span>
            ))}
          </div>
          <div className="fridge-recipe-hero__actions">
            <button type="button" onClick={startRecommendation} disabled={isAnalyzing}>
              {isAnalyzing ? '추천 계산 중' : '추천 다시 계산'}
            </button>
            <button type="button" onClick={() => navigate('/fridge')}>냉장고 수정</button>
          </div>
        </div>
        <ImageSlot className="fridge-recipe-hero__image" src={imageMenuRecommendation} />
      </div>

      <section className="fridge-recipe-runner" aria-label="냉장고파먹기 진행 상태">
        <div>
          <span>{isRecommendationReady ? '추천 준비 완료' : `${activeStep + 1}단계 진행 중`}</span>
          <h2>{process[activeStep].title}</h2>
          <p>{process[activeStep].description}</p>
        </div>
        <div className="fridge-recipe-runner__meter" aria-hidden="true">
          <i style={{ width: `${progressPercent}%` }} />
        </div>
        <strong>{progressPercent}%</strong>
      </section>

      <div className="fridge-recipe-summary" aria-label="냉장고파먹기 요약">
        {summary.map((item) => (
          <button className="fridge-recipe-summary-card" type="button" key={item.label} onClick={item.onClick}>
            <ImageSlot className="fridge-recipe-summary-card__image" src={item.image} />
            <span>{item.label}</span>
            <strong>{item.value}</strong>
            <p>{item.note}</p>
          </button>
        ))}
      </div>

      <div className="fridge-recipe-content">
        <main>
          <div className="fridge-recipe-toolbar">
            <div className="fridge-recipe-tabs" aria-label="추천 필터">
              {tabs.map((tab) => (
                <button
                  className={activeTab === tab ? 'is-active' : ''}
                  type="button"
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                >
                  {tab}
                </button>
              ))}
            </div>
            <select aria-label="정렬" value={sortMode} onChange={(event) => setSortMode(event.target.value)}>
              <option value="recommend">추천순</option>
              <option value="match">매칭률순</option>
              <option value="time">빠른 조리순</option>
              <option value="saving">재료 활용순</option>
            </select>
          </div>

          <div className="fridge-recipe-grid">
            {visibleRecommendations.map((recipe) => (
              <article
                className={selectedRecipeId === recipe.id ? 'fridge-recipe-card is-selected' : 'fridge-recipe-card'}
                key={recipe.title}
              >
                <div className="fridge-recipe-card__media">
                  <span>{recipe.category}</span>
                  <button
                    type="button"
                    aria-label={`${recipe.title} 저장`}
                    aria-pressed={savedIds.includes(recipe.id)}
                    onClick={() => toggleSaved(recipe.id)}
                  >
                    {savedIds.includes(recipe.id) ? '♥' : '♡'}
                  </button>
                  <ImageSlot className="fridge-recipe-card__image" src={recipe.image} />
                </div>

                <div className="fridge-recipe-card__body">
                  <h2>{recipe.title}</h2>
                  <p className="fridge-recipe-card__meta">
                    {recipe.time} · {recipe.level} · {recipe.people}
                  </p>
                  <strong className="fridge-recipe-card__match">냉장고 매칭률 {recipe.match}%</strong>

                  <dl className="fridge-recipe-card__score">
                    <div>
                      <dt>보유</dt>
                      <dd>{recipe.owned}/{recipe.total}개</dd>
                    </div>
                    <div>
                      <dt>절약</dt>
                      <dd>{recipe.saveEstimate}</dd>
                    </div>
                  </dl>

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
                    <button type="button" onClick={() => selectRecipe(recipe)}>
                      {selectedRecipeId === recipe.id ? '선택됨' : '오늘 메뉴 선택'}
                    </button>
                    <Link to={`/recipes/${recipe.id}`}>레시피 보기</Link>
                    <button type="button" onClick={() => goShopping(recipe)}>장보기 이동</button>
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
              <li
                className={`${index === activeStep ? 'is-active' : ''} ${index < activeStep || isRecommendationReady ? 'is-done' : ''}`}
                key={item.title}
              >
                <span>{index + 1}</span>
                <strong>{item.title}</strong>
                <p>{item.description}</p>
              </li>
            ))}
          </ol>
        </aside>
      </div>

      <section className="fridge-recipe-cta">
        <ImageSlot className="fridge-recipe-cta__fridge" src={imagePutting} />
        <div>
          <h2>{selectedRecipe.title}로 냉장고를 비워볼까요?</h2>
          <p>
            냉장고 매칭률 {selectedRecipe.match}%, 부족 재료 {selectedRecipe.missing.length}개만 챙기면 바로 시작할 수 있어요.
          </p>
        </div>
        <ImageSlot className="fridge-recipe-cta__mascot" src={imageHello} />
        <button type="button" onClick={() => navigate(`/recipes/${selectedRecipe.id}`)}>오늘 요리 시작하기</button>
      </section>
    </section>
  )
}

export default FridgeRecipe
