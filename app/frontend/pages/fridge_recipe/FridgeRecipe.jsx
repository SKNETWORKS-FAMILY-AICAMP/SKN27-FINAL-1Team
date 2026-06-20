import React, { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import './FridgeRecipe.css'

import imageHello from '../../assets/extracted/images/image_hello.png'
import imageMenuRecommendation from '../../assets/extracted/images/image_menu_recommendation.png'
import { fridgeRecipeRecommendations as recommendations } from '../../mock/fridgeRecipeMock.js'
import { userProfile } from '../../mock/userService.js'

function ImageSlot({ src, alt = '', className = '' }) {
  return (
    <span className={`fridge-recipe-image-slot ${src ? 'is-filled' : ''} ${className}`}>
      {src ? <img src={src} alt={alt} /> : null}
    </span>
  )
}

function FridgeRecipe() {
  const navigate = useNavigate()
  const timerRef = useRef(null)
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [isRecommendationReady, setIsRecommendationReady] = useState(false)
  const [selectedRecipeId, setSelectedRecipeId] = useState(null)
  const [savedRecipe, setSavedRecipe] = useState(() => {
    if (typeof window === 'undefined') return null

    const saved = window.localStorage.getItem('bobbeori-fridge-recipe')
    return saved ? JSON.parse(saved) : null
  })

  const selectedRecipe = recommendations.find((recipe) => recipe.id === selectedRecipeId)

  const startRecommendation = () => {
    window.clearTimeout(timerRef.current)
    setIsAnalyzing(true)
    setIsRecommendationReady(false)
    setSelectedRecipeId(null)

    timerRef.current = window.setTimeout(() => {
      setIsAnalyzing(false)
      setIsRecommendationReady(true)
    }, 700)
  }

  const saveRecipe = (recipe) => {
    const nextRecipe = {
      id: recipe.id,
      title: recipe.title,
      category: recipe.category,
      level: recipe.level,
      people: recipe.people,
      owned: recipe.owned,
      total: recipe.total,
      reason: recipe.reason,
      missing: recipe.missing,
    }

    setSelectedRecipeId(recipe.id)
    setSavedRecipe(nextRecipe)
    window.localStorage.setItem('bobbeori-fridge-recipe', JSON.stringify(nextRecipe))
    window.localStorage.setItem('bobbeori-selected-recipe', recipe.title)
  }

  useEffect(() => () => window.clearTimeout(timerRef.current), [])

  return (
    <section className="fridge-recipe-page" aria-labelledby="fridge-recipe-title">
      <div className="fridge-recipe-hero">
        <div className="fridge-recipe-hero__copy">
          <h1 id="fridge-recipe-title">냉장고파먹기</h1>
          <p>
            지금 냉장고에 있는 재료와 소비 임박 재료를 기준으로 만들기 좋은 메뉴를 추천받아보세요.
            추천 결과는 저장해서 마이페이지에서 다시 확인할 수 있어요.
          </p>
          <div className="fridge-recipe-hero__actions">
            <button type="button" onClick={startRecommendation} disabled={isAnalyzing}>
              {isAnalyzing ? '추천 중' : isRecommendationReady ? '다시 추천받기' : '추천받기'}
            </button>
          </div>
        </div>
        <ImageSlot className="fridge-recipe-hero__image" src={imageMenuRecommendation} />
      </div>

      {!isRecommendationReady ? (
        <section className="fridge-recipe-empty" aria-label="추천 시작 안내">
          <ImageSlot className="fridge-recipe-empty__image" src={imageHello} />
          <div>
            <h2>{isAnalyzing ? '냉장고 재료를 살펴보고 있어요' : '추천받기를 눌러 메뉴를 받아보세요'}</h2>
            <p>
              추천이 완료되면 후보 메뉴가 나타나고, 마음에 드는 레시피를 저장할 수 있어요.
            </p>
          </div>
        </section>
      ) : (
        <section className="fridge-recipe-results" aria-labelledby="fridge-recipe-results-title">
          <div className="fridge-recipe-section-title">
            <h2 id="fridge-recipe-results-title">추천받은 메뉴</h2>
            <p>하나를 선택해 저장하면 마이페이지에서 이어볼 수 있어요.</p>
          </div>

          <div className="fridge-recipe-grid">
            {recommendations.map((recipe) => (
              <article
                className={selectedRecipeId === recipe.id ? 'fridge-recipe-card is-selected' : 'fridge-recipe-card'}
                key={recipe.title}
              >
                <div className="fridge-recipe-card__media">
                  <span>{recipe.category}</span>
                  <ImageSlot className="fridge-recipe-card__image" src={recipe.image} />
                </div>

                <div className="fridge-recipe-card__body">
                  <h2>{recipe.title}</h2>
                  <p className="fridge-recipe-card__meta">
                    {recipe.level} · {recipe.people}
                  </p>
                  <div className="fridge-recipe-card__score">
                    <div>
                      <dt>보유 재료</dt>
                      <dd>{recipe.owned}/{recipe.total}개</dd>
                    </div>
                    <div>
                      <dt>부족 재료</dt>
                      <dd>{recipe.missing.length}개</dd>
                    </div>
                  </div>

                  <div className="fridge-recipe-card__reason">
                    <b>추천 이유</b>
                    <p>{recipe.reason}</p>
                  </div>

                  <div className="fridge-recipe-card__actions">
                    <button type="button" onClick={() => saveRecipe(recipe)}>
                      {selectedRecipeId === recipe.id ? '저장됨' : '이 레시피 저장'}
                    </button>
                    <button type="button" onClick={() => navigate(`/recipes/${recipe.id}`)}>
                      상세 보기
                    </button>
                  </div>
                </div>
              </article>
            ))}
          </div>
        </section>
      )}

      {savedRecipe ? (
        <section className="fridge-recipe-saved" aria-label="저장된 추천">
          <div>
            <span>저장된 메뉴</span>
            <strong>{savedRecipe.title}</strong>
            <p>{userProfile.name} 마이페이지에서 다시 확인할 수 있어요.</p>
          </div>
          <button type="button" onClick={() => navigate('/mypage')}>마이페이지에서 확인</button>
        </section>
      ) : null}
    </section>
  )
}

export default FridgeRecipe
