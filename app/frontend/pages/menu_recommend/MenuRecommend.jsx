import React, { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import './MenuRecommend.css'

import imageHello from '../../assets/extracted/images/image_hello.png'
import imageMenuRecommendation from '../../assets/extracted/images/image_menu_recommendation.png'
import imageSearch from '../../assets/extracted/images/image_search.png'
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

const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000'

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
  const [error, setError] = useState('')

  const activeTemplate = recommendTemplates.find((item) => item.id === templateId) ?? recommendTemplates[0]
  const displayedCount = generatedRecipes.length

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

  const handleGenerate = async () => {
    const token = window.localStorage.getItem('bobbeori-token')
    if (!token) {
      navigate('/login')
      return
    }

    clearFlowTimers()
    setGeneratedRecipes([])
    setSelectedIds([])
    setActiveStep(0)
    setError('')
    setIsGenerating(true)
    startProgressAnimation()

    try {
      const response = await fetch(`${apiUrl}/api/v1/recipes/recommend`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(buildRecommendRequestBody(filters)),
      })

      if (!response.ok) {
        throw new Error('추천을 불러오지 못했어요.')
      }

      const data = await response.json()
      setGeneratedRecipes(data.items || [])
      setActiveStep(process.length - 1)
    } catch (fetchError) {
      setError(fetchError.message || '추천을 불러오지 못했어요.')
    } finally {
      clearFlowTimers()
      setIsGenerating(false)
    }
  }

  const handleSelect = (recipeId) => {
    setSelectedIds((prev) =>
      prev.includes(recipeId) ? prev.filter((id) => id !== recipeId) : [...prev, recipeId],
    )
  }

  const persistRecipe = (recipe) => {
    saveStoredRecipe({
      ...recipe,
      id: recipe.recipe_id,
      recipe_id: recipe.recipe_id,
      image: recipe.main_image_url,
      source: '메뉴추천',
      reason: recipe.reason,
    })
    saveRecommendationResult(recipe, 'menu_recommend').catch(() => {})
  }

  const handleSave = () => {
    generatedRecipes
      .filter((recipe) => selectedIds.includes(recipe.recipe_id))
      .forEach(persistRecipe)
    setSavedIds((prev) => Array.from(new Set([...prev, ...selectedIds])))
  }

  const saveSingleRecipe = (recipeId) => {
    const recipe = generatedRecipes.find((item) => item.recipe_id === recipeId)
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
            <span className="menu-recommend-panel__step">1</span>
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
                <span className="menu-recommend-template-card__icon" aria-hidden="true">
                  {template.icon}
                </span>
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
              <span className="menu-recommend-panel__step">2</span>
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
                    <span aria-hidden="true">{group.icon}</span>
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
              <p>
                {isGenerating
                  ? `${process[activeStep].title} 중이에요. 잠시만 기다려주세요.`
                  : displayedCount
                    ? `${displayedCount}개의 메뉴를 조건에 맞춰 골랐어요.`
                    : `${activeTemplate.label} · ${getOptionLabel('cookTime', filters.cookTime)} · ${filters.limit}개`}
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

          {error ? (
            <p className="menu-recommend-empty" role="alert">{error}</p>
          ) : null}

          {displayedCount === 0 ? (
            <div className="menu-recommend-empty">
              <ImageSlot src={isGenerating ? imageMenuRecommendation : imageSearch} alt="추천 대기 상태" />
              <strong>{isGenerating ? '메뉴 후보를 고르는 중이에요.' : '조건을 고르고 추천을 시작해주세요.'}</strong>
              <p>
                {isGenerating
                  ? `${activeTemplate.label} 조건에 맞는 메뉴를 정리하고 있어요.`
                  : '선택한 필터에 맞춰 추천 결과가 달라져요.'}
              </p>
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
                      <span>{recipe.category || '추천 메뉴'}</span>
                      <ImageSlot
                        className="menu-recommend-card__image"
                        src={recipe.main_image_url}
                        alt={recipe.main_image_url ? recipe.title : ''}
                      />
                    </div>
                    <div className="menu-recommend-card__body">
                      <h3>{recipe.title}</h3>
                      <p>
                        {formatCookingTime(recipe.cooking_time_min)} · {recipe.difficulty || '-'}
                      </p>
                      <div>
                        <b>추천 이유</b>
                        <span>{recipe.reason || '조건에 맞는 메뉴예요.'}</span>
                      </div>
                      <div className="menu-recommend-card__actions">
                        <Link to={`/recipes/${recipeId}`}>레시피 보기</Link>
                        <button
                          type="button"
                          disabled={isSaved}
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
