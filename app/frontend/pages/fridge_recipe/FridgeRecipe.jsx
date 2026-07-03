import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import './FridgeRecipe.css'

import imageHello from '../../assets/extracted/images/image_hello.png'
import imageMenuRecommendation from '../../assets/extracted/images/image_menu_recommendation.png'
import { userProfile } from '../../mock/userService.js'
import { saveRecommendationResult, saveStoredRecipe } from '../../utils/savedRecipes.js'
import { API_URL } from '../../utils/api.js'


function ImageSlot({ src, alt = '', className = '' }) {
  return (
    <span className={`fridge-recipe-image-slot ${src ? 'is-filled' : ''} ${className}`}>
      {src ? <img src={src} alt={alt} /> : null}
    </span>
  )
}

function formatPeople(servingCount) {
  if (!servingCount) return '인분 정보 없음'
  return `${servingCount}인분`
}

function FridgeRecipe() {
  const navigate = useNavigate()
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')
  const [items, setItems] = useState([])
  const [hasMore, setHasMore] = useState(false)
  const [excludedRecipeIds, setExcludedRecipeIds] = useState([])
  const [hasRequested, setHasRequested] = useState(false)
  const [selectedRecipeId, setSelectedRecipeId] = useState(null)
  const [savedRecipe, setSavedRecipe] = useState(() => {
    if (typeof window === 'undefined') return null

    const saved = window.localStorage.getItem('bobbeori-fridge-recipe')
    return saved ? JSON.parse(saved) : null
  })

  const fetchRecommendations = async ({ refreshPool, excludeIds }) => {
    const token = window.localStorage.getItem('bobbeori-token')
    if (!token) {
      navigate('/login')
      return
    }

    setIsLoading(true)
    setError('')

    try {
      const response = await fetch(`${API_URL}/api/v1/recipes/recommend`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          mode: 'fridge_consume',
          exclude_recipe_ids: excludeIds,
          refresh_pool: refreshPool,
        }),
      })

      if (!response.ok) {
        throw new Error('추천을 불러오지 못했어요.')
      }

      const data = await response.json()
      setItems(data.items || [])
      setHasMore(Boolean(data.has_more))
      setHasRequested(true)
      setSelectedRecipeId(null)

      if (refreshPool) {
        setExcludedRecipeIds([])
      }
    } catch (fetchError) {
      setError(fetchError.message || '추천을 불러오지 못했어요.')
    } finally {
      setIsLoading(false)
    }
  }

  const startRecommendation = () => {
    fetchRecommendations({ refreshPool: true, excludeIds: [] })
  }

  const loadMoreRecommendations = () => {
    const currentIds = items.map((recipe) => recipe.recipe_id)
    const nextExclude = [...new Set([...excludedRecipeIds, ...currentIds])]
    setExcludedRecipeIds(nextExclude)
    fetchRecommendations({ refreshPool: false, excludeIds: nextExclude })
  }

  const saveRecipe = (recipe) => {
    const recipeId = recipe.recipe_id
    const totalIngredients = recipe.owned_ingredient_count + recipe.missing_ingredient_count
    const nextRecipe = {
      id: recipeId,
      recipe_id: recipeId,
      title: recipe.title,
      category: recipe.category,
      level: recipe.difficulty || '난이도 미정',
      people: formatPeople(recipe.serving_count),
      owned: recipe.owned_ingredient_count,
      total: totalIngredients,
      reason: recipe.reason,
      missing: recipe.missing_ingredient_count,
    }

    const saved = saveStoredRecipe({ ...nextRecipe, source: '냉장고파먹기', image: recipe.main_image_url })
    saveRecommendationResult(recipe, 'fridge_based').catch(() => {})

    setSelectedRecipeId(recipeId)
    setSavedRecipe(saved)
    window.localStorage.setItem('bobbeori-fridge-recipe', JSON.stringify(saved))
    window.localStorage.setItem('bobbeori-selected-recipe', recipe.title)
  }

  const isRecommendationReady = hasRequested && !isLoading && items.length > 0
  const isEmptyResult = hasRequested && !isLoading && items.length === 0

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
            <button type="button" onClick={startRecommendation} disabled={isLoading}>
              {isLoading ? '추천 중' : hasRequested ? '새로 추천받기' : '추천받기'}
            </button>
            {hasRequested && hasMore ? (
              <button
                type="button"
                className="is-secondary"
                onClick={loadMoreRecommendations}
                disabled={isLoading}
              >
                다른 레시피 추천
              </button>
            ) : null}
          </div>
        </div>
        <ImageSlot className="fridge-recipe-hero__image" src={imageMenuRecommendation} />
      </div>

      {error ? (
        <p className="fridge-recipe-empty" role="alert">{error}</p>
      ) : null}

      {!isRecommendationReady && !isEmptyResult ? (
        <section className="fridge-recipe-empty" aria-label="추천 시작 안내">
          <ImageSlot className="fridge-recipe-empty__image" src={imageHello} />
          <div>
            <h2>{isLoading ? '냉장고 재료를 살펴보고 있어요' : '추천받기를 눌러 메뉴를 받아보세요'}</h2>
            <p>
              추천이 완료되면 후보 메뉴가 나타나고, 마음에 드는 레시피를 저장할 수 있어요.
            </p>
          </div>
        </section>
      ) : isEmptyResult ? (
        <section className="fridge-recipe-empty" aria-label="추천 결과 없음">
          <ImageSlot className="fridge-recipe-empty__image" src={imageHello} />
          <div>
            <h2>추천할 메뉴를 찾지 못했어요</h2>
            <p>냉장고에 재료를 등록한 뒤 다시 추천받기를 눌러보세요.</p>
          </div>
        </section>
      ) : (
        <section className="fridge-recipe-results" aria-labelledby="fridge-recipe-results-title">
          <div className="fridge-recipe-section-title">
            <h2 id="fridge-recipe-results-title">추천받은 메뉴</h2>
            <p>추천받은 메뉴를 저장해보세요.</p>
          </div>

          <div className="fridge-recipe-grid">
            {items.map((recipe) => (
              <article
                className={selectedRecipeId === recipe.recipe_id ? 'fridge-recipe-card is-selected' : 'fridge-recipe-card'}
                key={recipe.recipe_id}
              >
                <div className="fridge-recipe-card__media">
                  <ImageSlot className="fridge-recipe-card__image" src={recipe.main_image_url} alt={recipe.title} />
                  <span>{recipe.category || '추천 메뉴'}</span>
                </div>

                <div className="fridge-recipe-card__body">
                  <h2>{recipe.title}</h2>
                  <p className="fridge-recipe-card__meta">
                    {recipe.difficulty || '난이도 미정'} · {formatPeople(recipe.serving_count)}
                  </p>
                  <div className="fridge-recipe-card__score">
                    <div>
                      <dt>보유 재료</dt>
                      <dd>
                        {recipe.owned_ingredient_count}/
                        {recipe.owned_ingredient_count + recipe.missing_ingredient_count}개
                      </dd>
                    </div>
                    <div>
                      <dt>부족 재료</dt>
                      <dd>{recipe.missing_ingredient_count}개</dd>
                    </div>
                  </div>

                  {recipe.reason ? (
                    <div className="fridge-recipe-card__reason">
                      <b>추천 이유</b>
                      <p>{recipe.reason}</p>
                    </div>
                  ) : null}

                  <div className="fridge-recipe-card__actions">
                    <button type="button" onClick={() => saveRecipe(recipe)}>
                      {selectedRecipeId === recipe.recipe_id ? '저장됨' : '이 레시피 저장'}
                    </button>
                    <button type="button" onClick={() => navigate(`/recipes/${recipe.recipe_id}`)}>
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
          <button type="button" onClick={() => navigate('/mypage?tab=saved')}>마이페이지에서 확인</button>
        </section>
      ) : null}
    </section>
  )
}

export default FridgeRecipe
