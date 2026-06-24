import React, { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import './MenuRecommend.css'

import imageHello from '../../assets/extracted/images/image_hello.png'
import imageMenuRecommendation from '../../assets/extracted/images/image_menu_recommendation.png'
import imageSearch from '../../assets/extracted/images/image_search.png'
import { saveRecommendationResult, saveStoredRecipe } from '../../utils/savedRecipes.js'
import {
  countOptions,
  mealOptions,
  menuRecommendProcess as process,
  menuRecommendRecipes as recipes,
  moodOptions,
  priorityOptions,
} from '../../mock/menuRecommendMock.js'

function ImageSlot({ src, alt = '', className = '' }) {
  return (
    <span className={`menu-recommend-image-slot ${src ? 'is-filled' : ''} ${className}`}>
      {src ? <img src={src} alt={alt} /> : null}
    </span>
  )
}

function getRecipeScore(recipe, mood, meal, priority) {
  return [
    recipe.moods?.includes(mood),
    recipe.meals?.includes(meal),
    recipe.priorities?.includes(priority),
  ].filter(Boolean).length
}

function MenuRecommend() {
  const navigate = useNavigate()
  const flowTimersRef = useRef([])
  const [selectedCount, setSelectedCount] = useState(5)
  const [generatedCount, setGeneratedCount] = useState(0)
  const [selectedIds, setSelectedIds] = useState([])
  const [savedIds, setSavedIds] = useState([])
  const [selectedMood, setSelectedMood] = useState(moodOptions[0])
  const [selectedMeal, setSelectedMeal] = useState(mealOptions[2])
  const [selectedPriority, setSelectedPriority] = useState(priorityOptions[0])
  const [activeStep, setActiveStep] = useState(0)
  const [isGenerating, setIsGenerating] = useState(false)

  const sortedRecipes = useMemo(() => {
    return recipes
      .map((recipe) => ({
        ...recipe,
        matchScore: getRecipeScore(recipe, selectedMood, selectedMeal, selectedPriority),
      }))
      .sort((a, b) => b.matchScore - a.matchScore || Number.parseInt(a.time, 10) - Number.parseInt(b.time, 10))
  }, [selectedMeal, selectedMood, selectedPriority])

  const generatedRecipes = useMemo(
    () => sortedRecipes.slice(0, generatedCount),
    [generatedCount, sortedRecipes],
  )

  const clearFlowTimers = () => {
    flowTimersRef.current.forEach((timerId) => window.clearTimeout(timerId))
    flowTimersRef.current = []
  }

  const resetGeneratedState = () => {
    clearFlowTimers()
    setGeneratedCount(0)
    setSelectedIds([])
    setActiveStep(0)
    setIsGenerating(false)
  }

  const handleFilterChange = (setter) => (value) => {
    setter(value)
    resetGeneratedState()
  }

  const handleGenerate = () => {
    clearFlowTimers()
    setGeneratedCount(0)
    setSelectedIds([])
    setActiveStep(0)
    setIsGenerating(true)

    flowTimersRef.current = process.slice(1).map((_, index) =>
      window.setTimeout(() => {
        setActiveStep(index + 1)
      }, 420 * (index + 1)),
    )

    flowTimersRef.current.push(
      window.setTimeout(() => {
        setGeneratedCount(selectedCount)
        setIsGenerating(false)
        window.localStorage.setItem(
          'bobbeori-last-menu-recommend',
          JSON.stringify({
            count: selectedCount,
            mood: selectedMood,
            meal: selectedMeal,
            priority: selectedPriority,
          }),
        )
      }, 420 * process.length),
    )
  }

  const handleSelect = (recipeId) => {
    setSelectedIds((prev) =>
      prev.includes(recipeId) ? prev.filter((id) => id !== recipeId) : [...prev, recipeId],
    )
  }

  const persistRecipe = (recipe) => {
    saveStoredRecipe({
      ...recipe,
      source: '메뉴추천',
      reason: recipe.reason,
    })
    saveRecommendationResult(recipe, 'menu_recommend').catch(() => {})
  }

  const handleSave = () => {
    generatedRecipes.filter((recipe) => selectedIds.includes(recipe.id)).forEach(persistRecipe)
    setSavedIds((prev) => Array.from(new Set([...prev, ...selectedIds])))
  }

  const saveSingleRecipe = (recipeId) => {
    const recipe = recipes.find((item) => item.id === recipeId)
    if (recipe) {
      persistRecipe(recipe)
    }

    setSavedIds((prev) => (prev.includes(recipeId) ? prev : [...prev, recipeId]))
  }

  const goShopping = (recipe) => {
    window.localStorage.setItem('bobbeori-shopping-recipe', recipe.title)
    navigate('/shopping-list')
  }

  useEffect(() => clearFlowTimers, [])

  return (
    <section className="menu-recommend-page" aria-labelledby="menu-recommend-title">
      <div className="menu-recommend-hero">
        <div className="menu-recommend-hero__copy">
          <h1 id="menu-recommend-title">메뉴 추천</h1>
          <p>
            지금 먹고 싶은 분위기와 식사 시간에 맞춰 만들기 좋은 메뉴를 추천받아보세요.
          </p>
        </div>
        <ImageSlot
          className="menu-recommend-hero__image"
          src={imageMenuRecommendation}
          alt="메뉴를 추천하는 밥벌이 캐릭터"
        />
      </div>

      <section className="menu-recommend-builder" aria-labelledby="builder-title">
        <div className="menu-recommend-builder__title">
          <h2 id="builder-title">추천 조건</h2>
          <p>{selectedMeal} · {selectedMood} · {selectedPriority} · {selectedCount}개</p>
        </div>
        <div className="menu-recommend-options">
          <div className="menu-recommend-filter" role="group" aria-label="분위기 선택">
            <span>분위기</span>
            {moodOptions.map((mood) => (
              <button
                className={selectedMood === mood ? 'is-active' : ''}
                key={mood}
                type="button"
                onClick={() => handleFilterChange(setSelectedMood)(mood)}
              >
                {mood}
              </button>
            ))}
          </div>
          <div className="menu-recommend-filter" role="group" aria-label="식사 시간 선택">
            <span>식사</span>
            {mealOptions.map((meal) => (
              <button
                className={selectedMeal === meal ? 'is-active' : ''}
                key={meal}
                type="button"
                onClick={() => handleFilterChange(setSelectedMeal)(meal)}
              >
                {meal}
              </button>
            ))}
          </div>
          <div className="menu-recommend-filter" role="group" aria-label="우선순위 선택">
            <span>우선</span>
            {priorityOptions.map((priority) => (
              <button
                className={selectedPriority === priority ? 'is-active' : ''}
                key={priority}
                type="button"
                onClick={() => handleFilterChange(setSelectedPriority)(priority)}
              >
                {priority}
              </button>
            ))}
          </div>
          <div className="menu-recommend-filter" role="group" aria-label="추천 개수 선택">
            <span>개수</span>
            {countOptions.map((count) => (
              <button
                className={selectedCount === count ? 'is-active' : ''}
                key={count}
                type="button"
                onClick={() => handleFilterChange(setSelectedCount)(count)}
              >
                {count}개
              </button>
            ))}
          </div>
        </div>
        <button className="menu-recommend-primary" type="button" onClick={handleGenerate} disabled={isGenerating}>
          {isGenerating ? '추천 중' : `${selectedCount}개 추천받기`}
        </button>
      </section>

      <div className="menu-recommend-content">
        <main className="menu-recommend-results">
          <div className="menu-recommend-results__header">
            <div>
              <h2>추천 결과</h2>
              <p>
                {isGenerating
                  ? `${process[activeStep].title} 중이에요. 잠시만 기다려주세요.`
                  : generatedCount
                    ? `${generatedCount}개의 메뉴를 조건에 맞춰 골랐어요.`
                    : '조건을 고르고 추천받기를 눌러주세요.'}
              </p>
            </div>
            <button
              className="menu-recommend-save"
              type="button"
              disabled={selectedIds.length === 0}
              onClick={handleSave}
            >
              선택 저장
            </button>
          </div>

          {generatedCount === 0 ? (
            <div className="menu-recommend-empty">
              <ImageSlot src={isGenerating ? imageMenuRecommendation : imageSearch} alt="추천 대기 상태" />
              <strong>{isGenerating ? '메뉴 후보를 고르는 중이에요.' : '조건을 고르고 추천을 시작해주세요.'}</strong>
              <p>
                {isGenerating
                  ? `${selectedMeal}에 어울리는 ${selectedMood} 메뉴를 정리하고 있어요.`
                  : '선택한 필터에 맞춰 추천 결과가 달라져요.'}
              </p>
            </div>
          ) : (
            <div className="menu-recommend-grid">
              {generatedRecipes.map((recipe) => {
                const isSelected = selectedIds.includes(recipe.id)
                const isSaved = savedIds.includes(recipe.id)

                return (
                  <article
                    className={[
                      'menu-recommend-card',
                      isSelected ? 'is-selected' : '',
                      isSaved ? 'is-saved' : '',
                    ]
                      .filter(Boolean)
                      .join(' ')}
                    key={recipe.id}
                  >
                    <button
                      className="menu-recommend-card__select"
                      type="button"
                      onClick={() => handleSelect(recipe.id)}
                      aria-pressed={isSelected}
                    >
                      {isSelected ? '선택됨' : '선택'}
                    </button>
                    <div className="menu-recommend-card__media">
                      <span>{recipe.category}</span>
                      <ImageSlot
                        className="menu-recommend-card__image"
                        src={recipe.image}
                        alt={recipe.image ? recipe.title : ''}
                      />
                    </div>
                    <div className="menu-recommend-card__body">
                      <h3>{recipe.title}</h3>
                      <p>
                        {recipe.time} · {recipe.level} · 조건 {recipe.matchScore}/3
                      </p>
                      <div>
                        <b>추천 이유</b>
                        <span>{recipe.reason}</span>
                      </div>
                      <div className="menu-recommend-card__actions">
                        <Link to={`/recipes/${recipe.id}`}>레시피 보기</Link>
                        <button
                          type="button"
                          disabled={isSaved}
                          onClick={() => saveSingleRecipe(recipe.id)}
                        >
                          {isSaved ? '저장 완료' : '바로 저장'}
                        </button>
                        <button type="button" onClick={() => goShopping(recipe)}>
                          장보기
                        </button>
                      </div>
                    </div>
                  </article>
                )
              })}
            </div>
          )}
        </main>

        <aside className="menu-recommend-guide" aria-labelledby="guide-title">
          <h2 id="guide-title">추천 기준</h2>
          <ol>
            {process.map((item, index) => (
              <li className={index === activeStep && isGenerating ? 'is-active' : ''} key={item.title}>
                <strong>{item.title}</strong>
                <p>{item.description}</p>
              </li>
            ))}
          </ol>
          <ImageSlot className="menu-recommend-guide__image" src={imageHello} alt="인사하는 밥벌이" />
        </aside>
      </div>
    </section>
  )
}

export default MenuRecommend
