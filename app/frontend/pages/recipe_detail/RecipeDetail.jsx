import React, { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import './RecipeDetail.css'

import iconBasket from '../../assets/extracted/icons/icon_basket.png'
import imageEatRefrigerator from '../../assets/extracted/images/image_eat_refrigerator.png'
import { useAppDialog } from '../../components/AppDialog.jsx'

const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000'

function ImageSlot({ src, alt = '', className = '' }) {
  return (
    <span className={`recipe-detail-image-slot ${src ? 'is-filled' : ''} ${className}`}>
      {src ? <img src={src} alt={alt} /> : null}
    </span>
  )
}

function formatCookingTime(minutes) {
  if (minutes == null) {
    return '조리 시간 확인 필요'
  }
  return `조리 시간 ${minutes}분`
}

function formatServing(count) {
  if (count == null) {
    return '인분 확인 필요'
  }
  return `${count}인분`
}

function formatDifficulty(difficulty) {
  return difficulty || '난이도 확인 필요'
}

function buildDescription(recipe) {
  const parts = []
  if (recipe.category) {
    parts.push(`${recipe.category} 요리`)
  }
  if (recipe.cooking_time_min != null) {
    parts.push(`조리 시간 약 ${recipe.cooking_time_min}분`)
  }
  if (recipe.difficulty) {
    parts.push(`난이도 ${recipe.difficulty}`)
  }
  if (parts.length === 0) {
    return `${recipe.title} 레시피입니다.`
  }
  return `${recipe.title}은(는) ${parts.join(', ')} 기준의 레시피예요.`
}

function RecipeDetail() {
  const navigate = useNavigate()
  const { recipeId } = useParams()
  const { dialogNode, showAlert } = useAppDialog()
  const stepsRef = useRef(null)
  const [recipe, setRecipe] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState(null)
  const [isSaved, setIsSaved] = useState(false)
  const [isCooking, setIsCooking] = useState(false)
  const [currentStep, setCurrentStep] = useState(0)
  const [isCooked, setIsCooked] = useState(false)
  const [isSaving, setIsSaving] = useState(false)

  const handleSaveRecipe = async () => {
    const token = window.localStorage.getItem('bobbeori-token')
    if (!token) {
      await showAlert('레시피를 저장하려면 로그인이 필요해요.', {
        title: '로그인이 필요해요',
      })
      navigate('/login')
      return
    }

    if (!recipe?.recipe_id) {
      await showAlert('레시피 정보가 올바르지 않아 저장할 수 없어요.', {
        title: '저장 실패',
      })
      return
    }

    setIsSaving(true)
    try {
      const response = await fetch(`${apiUrl}/api/v1/recommendations`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ recipe_id: recipe.recipe_id }),
      })

      if (response.status === 401) {
        await showAlert('로그인이 만료되었어요. 다시 로그인해 주세요.', {
          title: '로그인이 필요해요',
        })
        navigate('/login')
        return
      }

      if (response.status === 404) {
        await showAlert('레시피를 찾을 수 없어 저장하지 못했어요.', {
          title: '저장 실패',
        })
        return
      }

      if (!response.ok) {
        await showAlert('레시피를 추천 목록에 저장하지 못했어요.', {
          title: '저장 실패',
        })
        return
      }

      await showAlert('레시피를 추천 목록에 저장했어요.', {
        title: '저장 완료',
      })
    } catch {
      await showAlert('레시피를 추천 목록에 저장하지 못했어요.', {
        title: '저장 실패',
      })
    } finally {
      setIsSaving(false)
    }
  }

  useEffect(() => {
    const controller = new AbortController()

    const fetchRecipe = async () => {
      setIsLoading(true)
      setError(null)
      setRecipe(null)
      setIsCooking(false)
      setCurrentStep(0)
      setIsCooked(false)

      const token = window.localStorage.getItem('bobbeori-token')
      const headers = {}
      if (token) {
        headers.Authorization = `Bearer ${token}`
      }

      try {
        const response = await fetch(`${apiUrl}/api/v1/recipes/${recipeId}`, {
          signal: controller.signal,
          headers,
        })

        if (response.status === 404) {
          setError('레시피를 찾을 수 없습니다.')
          return
        }

        if (!response.ok) {
          throw new Error('레시피 상세 정보를 불러오지 못했습니다.')
        }

        const data = await response.json()
        setRecipe(data)
      } catch (fetchError) {
        if (fetchError.name === 'AbortError') {
          return
        }
        setError(fetchError.message || '레시피 상세 정보를 불러오지 못했습니다.')
      } finally {
        setIsLoading(false)
      }
    }

    if (!recipeId) {
      setError('레시피 ID가 올바르지 않습니다.')
      setIsLoading(false)
      return undefined
    }

    fetchRecipe()
    return () => controller.abort()
  }, [recipeId])

  const ownedIngredients = recipe?.owned_ingredients ?? []
  const missingIngredients = recipe?.missing_ingredients ?? []
  const steps = recipe?.steps ?? []
  const totalIngredients = ownedIngredients.length + missingIngredients.length
  const checkedCount = ownedIngredients.length
  const isLastStep = steps.length > 0 && currentStep >= steps.length - 1
  const servingLabel = recipe?.serving_count != null ? `${recipe.serving_count}인분 기준` : '1인분 기준'

  const moveCookingStep = (direction) => {
    setCurrentStep((prev) => Math.max(0, Math.min(prev + direction, steps.length - 1)))
  }

  const completeStep = () => {
    if (isLastStep) {
      setIsCooked(true)
      setIsCooking(false)
      if (recipe?.title) {
        window.localStorage.setItem('bobbeori-last-cooked-recipe', recipe.title)
      }
      return
    }

    setCurrentStep((prev) => prev + 1)
  }

  if (isLoading) {
    return (
      <section className="recipe-detail-page" aria-busy="true">
        <Link className="recipe-detail-mobile-back" to="/recipes" aria-label="레시피 목록으로 돌아가기">
          <span aria-hidden="true" />
        </Link>
        <p className="recipe-detail-status">레시피 정보를 불러오는 중이에요.</p>
      </section>
    )
  }

  if (error || !recipe) {
    return (
      <section className="recipe-detail-page">
        <Link className="recipe-detail-mobile-back" to="/recipes" aria-label="레시피 목록으로 돌아가기">
          <span aria-hidden="true" />
        </Link>
        <p className="recipe-detail-status recipe-detail-status--error">{error || '레시피를 불러올 수 없습니다.'}</p>
        <button className="recipe-detail-primary" type="button" onClick={() => navigate('/recipes')}>
          레시피 목록으로 돌아가기
        </button>
      </section>
    )
  }

  return (
    <section className="recipe-detail-page" aria-labelledby="recipe-detail-title">
      <Link className="recipe-detail-mobile-back" to="/recipes" aria-label="레시피 목록으로 돌아가기">
        <span aria-hidden="true" />
      </Link>

      <div className="recipe-detail-hero">
        <div className="recipe-detail-gallery">
          <div className="recipe-detail-main-image">
            <ImageSlot src={recipe.main_image_url || imageEatRefrigerator} alt={recipe.title} />
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
          <h1 id="recipe-detail-title">{recipe.title}</h1>
          <p>{buildDescription(recipe)}</p>
          <button
            className="recipe-detail-video-button"
            type="button"
            disabled={isSaving}
            onClick={handleSaveRecipe}
          >
            레시피 저장하기
          </button>

          <div className="recipe-detail-meta" aria-label="레시피 정보">
            <span>{formatCookingTime(recipe.cooking_time_min)}</span>
            <span>{formatServing(recipe.serving_count)}</span>
            <span>{formatDifficulty(recipe.difficulty)}</span>
            <span>재료 확인 {checkedCount}/{totalIngredients}</span>
          </div>
        </div>
      </div>

      <div className="recipe-detail-grid">
        <section className="recipe-detail-panel recipe-detail-ingredients" aria-labelledby="ingredients-title">
          <div className="recipe-detail-panel__title">
            <h2 id="ingredients-title">필요 재료</h2>
            <span>{servingLabel}</span>
          </div>

          <div className="recipe-detail-ingredient-group">
            <h3>보유 재료 ({ownedIngredients.length})</h3>
            <div className="recipe-detail-ingredient-list">
              {ownedIngredients.length === 0 ? (
                <p className="recipe-detail-empty-note">보유 재료가 없어요. 로그인 후 냉장고를 등록하면 확인할 수 있어요.</p>
              ) : (
                ownedIngredients.map((item, index) => (
                  <article
                    className="is-checked"
                    key={`owned-${item.ingredient_id ?? item.name}-${index}`}
                  >
                    <ImageSlot className="recipe-detail-ingredient__image" />
                    <div className="recipe-detail-ingredient__info">
                      <strong>{item.name}</strong>
                      <small>{item.amount || '-'}</small>
                    </div>
                  </article>
                ))
              )}
            </div>
          </div>

          <div className="recipe-detail-ingredient-group is-missing">
            <h3>부족 재료 ({missingIngredients.length})</h3>
            <div className="recipe-detail-ingredient-list">
              {missingIngredients.length === 0 ? (
                <p className="recipe-detail-empty-note">부족한 재료가 없어요.</p>
              ) : (
                missingIngredients.map((item, index) => (
                  <article key={`missing-${item.ingredient_id ?? item.name}-${index}`}>
                    <ImageSlot className="recipe-detail-ingredient__image" />
                    <div className="recipe-detail-ingredient__info">
                      <strong>{item.name}</strong>
                      <small>{item.amount || '-'}</small>
                    </div>
                  </article>
                ))
              )}
            </div>
          </div>
        </section>

        <aside className="recipe-detail-panel recipe-detail-shopping" aria-labelledby="shopping-title">
          <div>
            <h2 id="shopping-title">부족 재료 장보기</h2>
            <p>
              {missingIngredients.length > 0
                ? `${missingIngredients.length}가지 부족 재료를 한 번에 구매해요.`
                : '부족한 재료가 없어요.'}
            </p>
          </div>
          <ImageSlot className="recipe-detail-shopping__image" src={iconBasket} />
          <ul>
            {missingIngredients.map((item, index) => (
              <li key={`shop-${item.ingredient_id ?? item.name}-${index}`}>
                <span>{item.name}{item.amount ? ` (${item.amount})` : ''}</span>
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
        {steps.length === 0 ? (
          <p className="recipe-detail-empty-note">등록된 조리 순서가 없어요.</p>
        ) : (
          <>
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
                  key={`${step.title}-${index}`}
                  onClick={() => {
                    setCurrentStep(index)
                    setIsCooking(true)
                    setIsCooked(false)
                  }}
                >
                  <span>{index + 1}</span>
                  <ImageSlot
                    className="recipe-detail-step__image"
                    src={index === 0 ? null : (step.image_url || imageEatRefrigerator)}
                  />
                  <div>
                    <h3>{step.title}</h3>
                    <p>{step.text}</p>
                  </div>
                </article>
              ))}
            </div>
          </>
        )}
      </section>

      {dialogNode}
    </section>
  )
}

export default RecipeDetail
