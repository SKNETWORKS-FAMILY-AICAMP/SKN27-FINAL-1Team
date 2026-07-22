import React, { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import './RecipeDetail.css'

import imageEatRefrigerator from '../../assets/extracted/images/image_eat_refrigerator.png'
import { useAppDialog } from '../../components/AppDialog.jsx'
import { createRecipeShoppingList, hasShoppingAuth } from '../../services/shoppingApi.js'
import { API_URL } from '../../utils/api.js'
import { saveStoredRecipe } from '../../utils/savedRecipes.js'

const SHOPPING_CONTEXT_KEY = 'bobbeori-recipe-shopping-context'

function ImageSlot({ src, alt = '', className = '', loading = 'eager' }) {
  return (
    <span className={`recipe-detail-image-slot ${src ? 'is-filled' : ''} ${className}`}>
      {src ? <img src={src} alt={alt} loading={loading} /> : null}
    </span>
  )
}

function IngredientCard({ item, variant, showFridgeHint }) {
  const classNames = [
    variant === 'owned' || variant === 'maybe' ? 'is-checked' : '',
    variant === 'maybe' ? 'is-maybe-owned' : '',
  ].filter(Boolean).join(' ')

  return (
    <article className={classNames || undefined}>
      <div className="recipe-detail-ingredient__body">
        <div className="recipe-detail-ingredient__primary">
          <strong>{item.name}</strong>
          <span className="recipe-detail-ingredient__amount">{item.amount || '-'}</span>
        </div>
        {showFridgeHint ? (
          <p className="recipe-detail-ingredient__fridge-hint">
            냉장고: {item.fridge_ingredient_name}
          </p>
        ) : null}
      </div>
    </article>
  )
}

function formatCookingTime(minutes) {
  if (minutes == null) {
    return '시간 확인 필요'
  }
  return `${minutes}분`
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
  const swipeStartX = useRef(null)
  const [recipe, setRecipe] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState(null)
  const [isSaved, setIsSaved] = useState(false)
  const [currentStep, setCurrentStep] = useState(0)
  const [isCooked, setIsCooked] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [isShoppingCreating, setIsShoppingCreating] = useState(false)

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
      const response = await fetch(`${API_URL}/api/v1/recommendations`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ recipe_id: recipe.recipe_id, recommendation_type: 'manual_save' }),
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

      const savedResult = await response.json()
      saveStoredRecipe({
        recipe_id: recipe.recipe_id,
        recommendation_id: savedResult.recommendation_id,
        title: recipe.title,
        description: buildDescription(recipe),
        category: recipe.category,
        image: recipe.main_image_url || imageEatRefrigerator,
        source: '저장한 레시피',
        savedType: 'saved',
      })
      setIsSaved(true)
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
      setCurrentStep(0)
      setIsCooked(false)

      const token = window.localStorage.getItem('bobbeori-token')

      const requestDetail = (authToken) => fetch(`${API_URL}/api/v1/recipes/${recipeId}`, {
        signal: controller.signal,
        headers: authToken ? { Authorization: `Bearer ${authToken}` } : {},
      })

      try {
        let response = await requestDetail(token)

        // 레시피 상세는 비로그인도 열람 가능하므로, 만료/무효 토큰이면
        // 죽은 토큰을 정리하고 게스트로 다시 조회한다.
        if (response.status === 401 && token) {
          window.localStorage.removeItem('bobbeori-token')
          response = await requestDetail(null)
        }

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

  const exactOwnedIngredients = recipe?.owned_ingredients ?? []
  const maybeOwnedIngredients = recipe?.maybe_owned_ingredients ?? []
  const missingIngredients = recipe?.missing_ingredients ?? []
  const displayOwnedIngredients = [
    ...exactOwnedIngredients.map((item) => ({ ...item, ownershipType: 'exact' })),
    ...maybeOwnedIngredients.map((item) => ({ ...item, ownershipType: 'maybe' })),
  ]
  const steps = recipe?.steps ?? []
  const isLastStep = steps.length > 0 && currentStep >= steps.length - 1
  const servingLabel = recipe?.serving_count != null ? `${recipe.serving_count}인분 기준` : '1인분 기준'

  const buildShoppingContext = () => ({
    type: 'recipe',
    recipeId: recipe.recipe_id,
    recipeTitle: recipe.title,
    recipePath: `/recipes/${recipe.recipe_id}`,
    sourceUrl: recipe.source_url,
    servingLabel,
    createdAt: new Date().toISOString(),
    ownedIngredients: displayOwnedIngredients.map((item) => ({
      name: item.name,
      amount: item.amount,
      fridge_ingredient_name: item.fridge_ingredient_name,
      expiry_date: item.expiry_date,
      status: item.status,
      is_expired: Boolean(item.is_expired),
    })),
    missingIngredients: missingIngredients.map((item) => ({
      ingredient_id: item.ingredient_id,
      name: item.name,
      amount: item.amount,
    })),
  })

  const saveShoppingContext = () => {
    window.localStorage.setItem(SHOPPING_CONTEXT_KEY, JSON.stringify(buildShoppingContext()))
  }

  const createShoppingList = async () => {
    if (!hasShoppingAuth()) {
      await showAlert('부족 재료 장보기를 사용하려면 로그인이 필요해요.', {
        title: '로그인이 필요해요',
      })
      navigate('/login')
      return null
    }

    if (missingIngredients.length === 0) {
      await showAlert('장보기로 보낼 부족 재료가 없어요.', {
        title: '장보기 목록',
      })
      return null
    }

    saveShoppingContext()
    setIsShoppingCreating(true)

    try {
      return await createRecipeShoppingList({
        recipeId: recipe.recipe_id,
        missingIngredients: missingIngredients.map((item) => ({
          ingredient_id: item.ingredient_id,
          name: item.name,
          amount: item.amount,
        })),
      })
    } catch (shoppingError) {
      if (shoppingError.status === 401) {
        await showAlert('로그인이 만료되었어요. 다시 로그인해 주세요.', {
          title: '로그인이 필요해요',
        })
        navigate('/login')
        return null
      }

      if (shoppingError.status === 0) {
        const requestInfo = shoppingError.url ? `\n\n요청 주소: ${shoppingError.url}` : ''
        await showAlert(`백엔드 장보기 목록은 만들지 못했지만, 부족 재료 화면으로 이동할게요. 구매 링크는 서버 연결 후 다시 확인할 수 있어요.${requestInfo}`, {
          title: '임시 장보기 화면',
        })
        navigate(`/shopping-list?source=recipe&fallback=1`)
        return null
      }

      await showAlert(shoppingError.message || '장보기 목록을 만들지 못했어요.', {
        title: '장보기 생성 실패',
      })
      return null
    } finally {
      setIsShoppingCreating(false)
    }
  }

  const goShopping = async () => {
    const shoppingList = await createShoppingList()
    if (shoppingList?.id) {
      navigate(`/shopping-list?shoppingListId=${shoppingList.id}`)
    }
  }

  const moveCookingStep = (direction) => {
    setIsCooked(false)
    setCurrentStep((prev) => Math.max(0, Math.min(prev + direction, steps.length - 1)))
  }

  const completeStep = () => {
    if (isLastStep) {
      setIsCooked(true)
      if (recipe?.title) {
        window.localStorage.setItem('bobbeori-last-cooked-recipe', recipe.title)
      }
      return
    }

    setCurrentStep((prev) => prev + 1)
  }

  const handleStepSwipeEnd = (event) => {
    if (swipeStartX.current == null) return
    const distance = event.changedTouches[0].clientX - swipeStartX.current
    swipeStartX.current = null
    if (Math.abs(distance) < 50) return
    if (distance < 0 && !isLastStep) moveCookingStep(1)
    if (distance > 0 && currentStep > 0) moveCookingStep(-1)
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
        <div className="recipe-detail-main-image">
          <ImageSlot src={recipe.main_image_url || imageEatRefrigerator} alt={recipe.title} />
        </div>

        <div className="recipe-detail-summary">
          <p className="recipe-detail-eyebrow">{recipe.category || '오늘의 레시피'}</p>
          <h1 id="recipe-detail-title">{recipe.title}</h1>
          <p>{buildDescription(recipe)}</p>

          <div className="recipe-detail-meta" aria-label="레시피 정보">
            <span><b aria-hidden="true">◷</b>{formatCookingTime(recipe.cooking_time_min)}</span>
            <span><b aria-hidden="true">♙</b>{formatServing(recipe.serving_count)}</span>
            <span><b aria-hidden="true">▥</b>{formatDifficulty(recipe.difficulty)}</span>
          </div>

          <button
            className="recipe-detail-save-button"
            type="button"
            disabled={isSaved || isSaving}
            onClick={handleSaveRecipe}
          >
            <span aria-hidden="true">{isSaved ? '♥' : '♡'}</span>
            {isSaving ? '저장 중...' : isSaved ? '저장한 레시피' : '레시피 저장하기'}
          </button>
        </div>
      </div>

      <div className="recipe-detail-content">
        <aside className="recipe-detail-sidebar recipe-detail-sidebar--left">
          <section className="recipe-detail-panel recipe-detail-ingredients" aria-labelledby="owned-ingredients-title">
            <div className="recipe-detail-panel__title">
              <h2 id="owned-ingredients-title"><span className="recipe-detail-title-icon is-owned" aria-hidden="true">✓</span>보유 재료</h2>
              <span>{displayOwnedIngredients.length}개</span>
            </div>

            <div className="recipe-detail-ingredient-list">
              {displayOwnedIngredients.length === 0 ? (
                <p className="recipe-detail-empty-note">로그인 후 냉장고 재료를 등록하면 보유 여부를 확인할 수 있어요.</p>
              ) : (
                displayOwnedIngredients.map((item, index) => {
                  const isMaybe = item.ownershipType === 'maybe'
                  const showFridgeHint = isMaybe
                    && item.fridge_ingredient_name
                    && item.fridge_ingredient_name !== item.name
                  const keyPrefix = isMaybe ? 'maybe' : 'owned'

                  return (
                    <IngredientCard
                      key={`${keyPrefix}-${item.ingredient_id ?? item.name}-${index}`}
                      item={item}
                      variant={isMaybe ? 'maybe' : 'owned'}
                      showFridgeHint={showFridgeHint}
                    />
                  )
                })
              )}
            </div>
          </section>

          <section className="recipe-detail-panel recipe-detail-ingredients is-missing" aria-labelledby="missing-ingredients-title">
            <div className="recipe-detail-panel__title">
              <h2 id="missing-ingredients-title"><span className="recipe-detail-title-icon is-missing" aria-hidden="true">＋</span>부족 재료</h2>
              <span>{missingIngredients.length}개</span>
            </div>

            <div className="recipe-detail-ingredient-list">
              {missingIngredients.length === 0 ? (
                <p className="recipe-detail-empty-note">부족한 재료가 없어요.</p>
              ) : (
                missingIngredients.map((item, index) => (
                  <IngredientCard
                    key={`missing-${item.ingredient_id ?? item.name}-${index}`}
                    item={item}
                    variant="missing"
                  />
                ))
              )}
            </div>
            <button
              className="recipe-detail-ingredient-shopping-button"
              type="button"
              disabled={missingIngredients.length === 0 || isShoppingCreating}
              onClick={goShopping}
            >
              {isShoppingCreating ? '장보기 생성 중' : '장보기 바로가기'}
            </button>
          </section>
        </aside>

        <section className="recipe-detail-panel recipe-detail-steps" aria-labelledby="steps-title">
          <div className="recipe-detail-panel__title">
            <div>
              <p className="recipe-detail-section-kicker">COOKING GUIDE</p>
              <h2 id="steps-title">{steps[currentStep]?.title || '조리 단계'}</h2>
            </div>
            {steps.length > 0 ? <span className="recipe-detail-step-count">{currentStep + 1} / {steps.length}</span> : null}
          </div>
          {steps.length === 0 ? (
            <p className="recipe-detail-empty-note">등록된 조리 순서가 없어요.</p>
          ) : (
            <div className="recipe-detail-slider-wrap">
              {isCooked ? (
                <div className="recipe-detail-complete" role="status">
                  <span aria-hidden="true">✓</span>
                  <div><strong>맛있게 완성했어요</strong><p>오늘의 요리를 완성했어요.</p></div>
                </div>
              ) : null}

              <div
                className="recipe-detail-slider"
                aria-live="polite"
                onTouchStart={(event) => { swipeStartX.current = event.touches[0].clientX }}
                onTouchEnd={handleStepSwipeEnd}
              >
                <article className="recipe-detail-step-slide" key={currentStep}>
                  <p>{steps[currentStep].text}</p>
                  {steps[currentStep].image_url ? (
                    <ImageSlot
                      className="recipe-detail-step-slide__image"
                      src={steps[currentStep].image_url}
                      alt={`${recipe.title} 조리 ${currentStep + 1}단계`}
                      loading="lazy"
                    />
                  ) : null}
                </article>
              </div>

              <div className="recipe-detail-slider-nav">
                <button
                  className="recipe-detail-slider-arrow"
                  type="button"
                  disabled={currentStep === 0}
                  onClick={() => moveCookingStep(-1)}
                >
                  <span aria-hidden="true">←</span> 이전
                </button>
                <div className="recipe-detail-slider-dots" aria-label="조리 단계 선택">
                  {steps.map((step, index) => (
                    <button
                      type="button"
                      key={`${step.title}-dot-${index}`}
                      aria-label={`${index + 1}단계 보기`}
                      aria-current={index === currentStep ? 'step' : undefined}
                      onClick={() => {
                        setCurrentStep(index)
                        setIsCooked(false)
                      }}
                    />
                  ))}
                </div>
                <button
                  className="recipe-detail-slider-arrow is-next"
                  type="button"
                  disabled={isCooked}
                  onClick={completeStep}
                >
                  {isCooked ? '완료' : isLastStep ? '요리 완료' : '다음'} <span aria-hidden="true">→</span>
                </button>
              </div>
              <p className="recipe-detail-swipe-hint">화면을 좌우로 밀어 단계를 넘길 수 있어요.</p>
            </div>
          )}
        </section>
      </div>

      {dialogNode}
    </section>
  )
}

export default RecipeDetail
