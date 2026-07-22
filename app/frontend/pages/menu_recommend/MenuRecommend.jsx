import React, { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import './MenuRecommend.css'

import imageHello from '../../assets/extracted/images/image_hello.png'
import imageMenuRecommendation from '../../assets/extracted/images/image_menu_recommendation.png'
import imageSearch from '../../assets/extracted/images/image_search.png'
import { API_URL } from '../../utils/api.js'
import { saveRecommendationResult, saveStoredRecipe } from '../../utils/savedRecipes.js'
import {
  buildRecommendRequestBody,
  countOptions,
  defaultFilters,
  filterGroups,
  filterOptions,
  formatCookingTime,
  menuRecommendProcess as process,
  recommendTemplates,
} from '../../mock/menuRecommendMock.js'


function ImageSlot({ src, alt = '', className = '' }) {
  return (
    <span className={`menu-recommend-image-slot ${src ? 'is-filled' : ''} ${className}`}>
      {src ? <img src={src} alt={alt} /> : null}
    </span>
  )
}

function getOptionLabel(key, value) {
  return filterOptions[key]?.find((option) => option.value === value)?.label ?? value
}

function MenuRecommend() {
  const navigate = useNavigate()
  const flowTimersRef = useRef([])
  const quickTemplate = recommendTemplates[0]
  const [templateId, setTemplateId] = useState(quickTemplate.id)
  const [filters, setFilters] = useState(() => ({
    ...defaultFilters,
    ...quickTemplate.preset,
  }))
  const [settingsOpen, setSettingsOpen] = useState(true)
  const [generatedRecipes, setGeneratedRecipes] = useState([])
  const [selectedIds, setSelectedIds] = useState([])
  const [savedIds, setSavedIds] = useState([])
  const [activeStep, setActiveStep] = useState(0)
  const [isGenerating, setIsGenerating] = useState(false)
  const [hasRequested, setHasRequested] = useState(false)
  const [hasMore, setHasMore] = useState(false)
  const [excludedRecipeIds, setExcludedRecipeIds] = useState([])
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState('')

  const activeTemplate = recommendTemplates.find((item) => item.id === templateId) ?? recommendTemplates[0]
  const displayedCount = generatedRecipes.length
  const isEmptyResult = hasRequested && !isGenerating && !error && displayedCount === 0

  const clearFlowTimers = () => {
    flowTimersRef.current.forEach((timerId) => window.clearTimeout(timerId))
    flowTimersRef.current = []
  }

  const resetGeneratedState = () => {
    clearFlowTimers()
    setGeneratedRecipes([])
    setSelectedIds([])
    setActiveStep(0)
    setIsGenerating(false)
    setHasRequested(false)
    setHasMore(false)
    setExcludedRecipeIds([])
    setError('')
  }

  const handleTemplateSelect = (template) => {
    setTemplateId(template.id)
    if (template.preset) {
      setFilters((prev) => ({ ...defaultFilters, ...template.preset, limit: prev.limit }))
    }
    resetGeneratedState()
  }

  const handleFilterChange = (key, value) => {
    setTemplateId('custom')
    setFilters((prev) => ({ ...prev, [key]: value }))
    resetGeneratedState()
  }

  const handleLimitChange = (limit) => {
    setFilters((prev) => ({ ...prev, limit }))
    resetGeneratedState()
  }

  const startProgressAnimation = () => {
    flowTimersRef.current = process.slice(1).map((_, index) =>
      window.setTimeout(() => {
        setActiveStep(index + 1)
      }, 420 * (index + 1)),
    )
  }

  const fetchRecommendations = async ({ refreshPool, excludeIds }) => {
    const token = window.localStorage.getItem('bobbeori-token')
    if (!token) {
      navigate('/login')
      return
    }

    clearFlowTimers()
    setSelectedIds([])
    setActiveStep(0)
    setError('')
    setIsGenerating(true)
    startProgressAnimation()

    try {
      const response = await fetch(`${API_URL}/api/v1/recipes/recommend`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(buildRecommendRequestBody(filters, { excludeIds, refreshPool })),
      })

      if (!response.ok) {
        throw new Error('추천을 불러오지 못했어요.')
      }

      const data = await response.json()
      setGeneratedRecipes(data.items || [])
      setHasMore(Boolean(data.has_more))
      setHasRequested(true)
      setActiveStep(process.length - 1)

      if (refreshPool) {
        setExcludedRecipeIds([])
      }
    } catch (fetchError) {
      setError(fetchError.message || '추천을 불러오지 못했어요.')
    } finally {
      clearFlowTimers()
      setIsGenerating(false)
    }
  }

  const handleGenerate = () => {
    setExcludedRecipeIds([])
    fetchRecommendations({ refreshPool: hasRequested, excludeIds: [] })
  }

  const loadMoreRecommendations = () => {
    const currentIds = generatedRecipes.map((recipe) => recipe.recipe_id)
    const nextExclude = [...new Set([...excludedRecipeIds, ...currentIds])]
    setExcludedRecipeIds(nextExclude)
    fetchRecommendations({ refreshPool: false, excludeIds: nextExclude })
  }

  const handleSelect = (recipeId) => {
    setSelectedIds((prev) =>
      prev.includes(recipeId) ? prev.filter((id) => id !== recipeId) : [...prev, recipeId],
    )
  }

  const selectableIds = generatedRecipes.map((recipe) => recipe.recipe_id)
  const allSelected =
    selectableIds.length > 0 && selectableIds.every((id) => selectedIds.includes(id))

  const handleSelectAll = () => {
    setSelectedIds(selectableIds)
  }

  const handleDeselectAll = () => {
    setSelectedIds([])
  }

  const persistRecipe = async (recipe) => {
    const savedResult = await saveRecommendationResult(recipe, 'menu_recommend')
    saveStoredRecipe({
      ...recipe,
      id: recipe.recipe_id,
      recipe_id: recipe.recipe_id,
      recommendation_id: savedResult.recommendation_id,
      image: recipe.main_image_url,
      source: '메뉴추천',
      reason: recipe.reason,
    })
    return recipe.recipe_id
  }

  const handleSave = async () => {
    const selected = generatedRecipes.filter((recipe) => selectedIds.includes(recipe.recipe_id))
    if (selected.length === 0 || isSaving) return

    setIsSaving(true)

    const results = await Promise.allSettled(selected.map(persistRecipe))
    const succeeded = results.filter((result) => result.status === 'fulfilled').map((result) => result.value)
    setSavedIds((prev) => Array.from(new Set([...prev, ...succeeded])))

    setIsSaving(false)
  }

  const saveSingleRecipe = async (recipeId) => {
    if (savedIds.includes(recipeId) || isSaving) return

    const recipe = generatedRecipes.find((item) => item.recipe_id === recipeId)
    if (!recipe) return

    setIsSaving(true)

    try {
      await persistRecipe(recipe)
      setSavedIds((prev) => (prev.includes(recipeId) ? prev : [...prev, recipeId]))
    } catch {
      // ponytail: 저장 실패 피드백 없음 — 카드 UI(저장 완료)만 상태 반영
    } finally {
      setIsSaving(false)
    }
  }

  const goShopping = (recipe) => {
    window.localStorage.setItem('bobbeori-shopping-recipe', recipe.title)
    navigate('/shopping-list')
  }

  useEffect(() => clearFlowTimers, [])

  const resultsSubtitle = isGenerating
    ? `${process[activeStep].title} 중이에요. 잠시만 기다려주세요.`
    : displayedCount
      ? `${displayedCount}개의 메뉴를 조건에 맞춰 골랐어요.`
      : isEmptyResult
        ? '조건에 맞는 메뉴를 찾지 못했어요.'
        : `${activeTemplate.label} · ${getOptionLabel('cookTime', filters.cookTime)} · ${filters.limit}개`

  return (
    <section className="menu-recommend-page" aria-labelledby="menu-recommend-title">
      <div className="menu-recommend-hero">
        <div className="menu-recommend-hero__copy">
          <h1 id="menu-recommend-title">메뉴 추천</h1>
          <p>상황에 맞는 템플릿을 고르거나 직접 조건을 설정해 만들기 좋은 메뉴를 추천받아보세요.</p>
        </div>
        <ImageSlot
          className="menu-recommend-hero__image"
          src={imageMenuRecommendation}
          alt="메뉴를 추천하는 밥벌이 캐릭터"
        />
      </div>

      <div className="menu-recommend-filters">
        <section
          className="menu-recommend-panel menu-recommend-panel--templates"
          aria-labelledby="builder-title"
        >
          <div className="menu-recommend-panel__heading">
            <div>
              <h2 id="builder-title">추천 템플릿 선택</h2>
              <p>상황에 맞는 템플릿을 고르면 조건이 자동으로 설정됩니다.</p>
            </div>
          </div>
          <div className="menu-recommend-templates" role="list">
            {recommendTemplates.map((template) => (
              <button
                className={[
                  'menu-recommend-template-card',
                  templateId === template.id ? 'is-active' : '',
                ]
                  .filter(Boolean)
                  .join(' ')}
                key={template.id}
                type="button"
                role="listitem"
                aria-pressed={templateId === template.id}
                onClick={() => handleTemplateSelect(template)}
              >
                <strong>{template.label}</strong>
                <span>{template.desc}</span>
              </button>
            ))}
          </div>
          <p className="menu-recommend-panel__hint">
            템플릿을 선택하면 아래 설정이 자동으로 바뀌며, 이후 수동으로 조정할 수 있어요.
          </p>
        </section>

        <section className="menu-recommend-panel menu-recommend-panel--settings">
          <div className="menu-recommend-panel__heading menu-recommend-panel__heading--split">
            <div className="menu-recommend-panel__heading-copy">
              <div>
                <h2>추천 설정</h2>
                <p>원하는 조건을 직접 설정해 맞춤 추천을 받아보세요.</p>
              </div>
            </div>
            <button
              className="menu-recommend-settings-toggle"
              type="button"
              aria-expanded={settingsOpen}
              aria-controls="menu-recommend-settings"
              onClick={() => setSettingsOpen((open) => !open)}
            >
              {settingsOpen ? '접기' : '펼치기'}
            </button>
          </div>

          <section
            className="menu-recommend-settings"
            id="menu-recommend-settings"
            hidden={!settingsOpen}
          >
            <div className="menu-recommend-settings__grid">
              {filterGroups.map((group) => (
                <div className="menu-recommend-settings__column" key={group.key}>
                  <div className="menu-recommend-settings__column-head">
                    <div>
                      <strong>{group.label}</strong>
                      {group.subtitle ? <small>{group.subtitle}</small> : null}
                    </div>
                  </div>
                  {group.type === 'select' ? (
                    <select
                      className="menu-recommend-settings__select"
                      value={filters[group.key]}
                      onChange={(event) => handleFilterChange(group.key, event.target.value)}
                      aria-label={group.label}
                    >
                      {filterOptions[group.key].map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <div className="menu-recommend-settings__pills" role="group" aria-label={group.label}>
                      {filterOptions[group.key].map((option) => (
                        <button
                          className={filters[group.key] === option.value ? 'is-active' : ''}
                          key={option.value}
                          type="button"
                          onClick={() => handleFilterChange(group.key, option.value)}
                        >
                          <span>{option.label}</span>
                          <small>{option.hint || '\u00A0'}</small>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </section>
        </section>

        <section className="menu-recommend-panel menu-recommend-panel--actions">
          <div className="menu-recommend-panel__actions">
            <div className="menu-recommend-filter menu-recommend-filter--count" role="group" aria-label="추천 개수 선택">
              <span>추천 개수</span>
              {countOptions.map((count) => (
                <button
                  className={filters.limit === count ? 'is-active' : ''}
                  key={count}
                  type="button"
                  onClick={() => handleLimitChange(count)}
                >
                  {count}
                </button>
              ))}
            </div>
            <button
              className="menu-recommend-primary"
              type="button"
              onClick={handleGenerate}
              disabled={isGenerating}
            >
              {isGenerating ? '추천 중' : `레시피 추천받기 (${filters.limit}개)`}
            </button>
          </div>
        </section>
      </div>

      <div className="menu-recommend-content">
        <main className="menu-recommend-results">
          <div className="menu-recommend-results__header">
            <div>
              <h2>추천 결과</h2>
              <p>{resultsSubtitle}</p>
            </div>
            <div className="menu-recommend-results__actions">
              {hasRequested && hasMore ? (
                <button
                  className="menu-recommend-save"
                  type="button"
                  onClick={loadMoreRecommendations}
                  disabled={isGenerating}
                >
                  다른 메뉴 보기
                </button>
              ) : null}
              {displayedCount > 0 ? (
                <>
                  <button
                    className="menu-recommend-save"
                    type="button"
                    onClick={handleSelectAll}
                    disabled={isGenerating || isSaving || allSelected}
                  >
                    전체 선택
                  </button>
                  <button
                    className="menu-recommend-save"
                    type="button"
                    onClick={handleDeselectAll}
                    disabled={isGenerating || isSaving || selectedIds.length === 0}
                  >
                    선택 해제
                  </button>
                </>
              ) : null}
              <button
                className="menu-recommend-save"
                type="button"
                disabled={selectedIds.length === 0 || isSaving}
                onClick={handleSave}
              >
                {isSaving ? '저장 중' : '선택 저장'}
              </button>
            </div>
          </div>

          {error ? (
            <p className="menu-recommend-empty" role="alert">{error}</p>
          ) : null}

          {isGenerating ? (
            <div className="menu-recommend-empty">
              <ImageSlot src={imageMenuRecommendation} alt="추천 진행 중" />
              <strong>메뉴 후보를 고르는 중이에요.</strong>
              <p>{activeTemplate.label} 조건에 맞는 메뉴를 정리하고 있어요.</p>
            </div>
          ) : isEmptyResult ? (
            <div className="menu-recommend-empty">
              <ImageSlot src={imageHello} alt="추천 결과 없음" />
              <strong>조건에 맞는 메뉴를 찾지 못했어요.</strong>
              <p>필터를 완화하거나 위에서 레시피 추천받기를 눌러보세요.</p>
            </div>
          ) : displayedCount === 0 ? (
            <div className="menu-recommend-empty">
              <ImageSlot src={imageSearch} alt="추천 대기 상태" />
              <strong>조건을 고르고 추천을 시작해주세요.</strong>
              <p>선택한 필터에 맞춰 추천 결과가 달라져요.</p>
            </div>
          ) : (
            <div className="menu-recommend-grid">
              {generatedRecipes.map((recipe) => {
                const recipeId = recipe.recipe_id
                const isSelected = selectedIds.includes(recipeId)
                const isSaved = savedIds.includes(recipeId)

                return (
                  <article
                    className={[
                      'menu-recommend-card',
                      isSelected ? 'is-selected' : '',
                      isSaved ? 'is-saved' : '',
                    ]
                      .filter(Boolean)
                      .join(' ')}
                    key={recipeId}
                  >
                    <button
                      className="menu-recommend-card__select"
                      type="button"
                      onClick={() => handleSelect(recipeId)}
                      aria-pressed={isSelected}
                    >
                      {isSelected ? '선택됨' : '선택'}
                    </button>
                    <div className="menu-recommend-card__media">
                      <ImageSlot
                        className="menu-recommend-card__image"
                        src={recipe.main_image_url}
                        alt={recipe.main_image_url ? recipe.title : ''}
                      />
                      <span className="menu-recommend-card__category">{recipe.category || '추천 메뉴'}</span>
                    </div>
                    <div className="menu-recommend-card__body">
                      <h3>{recipe.title}</h3>
                      <p>
                        {formatCookingTime(recipe.cooking_time_min)} · {recipe.difficulty || '-'}
                      </p>
                      <div className="menu-recommend-card__actions">
                        <Link to={`/recipes/${recipeId}`}>레시피 보기</Link>
                        <button
                          type="button"
                          disabled={isSaved || isSaving}
                          onClick={() => saveSingleRecipe(recipeId)}
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
      </div>
    </section>
  )
}

export default MenuRecommend
