import React, { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import './Guide.css'

import iconBasket from '../../assets/extracted/icons/icon_basket.png'
import imageGuide from '../../assets/extracted/images/image_guide.png'

const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const GUIDE_PAGE_SIZE = 12
const GUIDE_RECIPE_LIMIT = 12
const GUIDE_RECIPE_VISIBLE_COUNT = 3
const EMPTY_SUGGESTION_FORM = { content: '', sourceName: '', sourceUrl: '' }

function normalizeIngredientImageName(name = '') {
  return name.replace(/\.[^.]+$/, '').replace(/\s/g, '').toLowerCase()
}

const ingredientImageModules = {
  ...import.meta.glob('../../assets/extracted/ingredients/*.{png,jpg,jpeg,webp,svg}', {
    eager: true,
    import: 'default',
  }),
}

const ingredientImages = Object.entries(ingredientImageModules)
  .map(([path, src]) => {
    const fileName = path.split('/').pop() || ''
    const name = fileName.replace(/\.[^.]+$/, '')
    return { name, key: normalizeIngredientImageName(name), src }
  })

const GUIDE_ICON_NAME_ALIASES = {
  가염버터: '버터',
  건다시마: '다시마',
  돼지삼겹살: '삼겹살',
  무염버터: '버터',
  미역: '건미역',
}

function getIngredientIcon(...names) {
  const candidates = names
    .flatMap((name) => String(name || '').split(/[,/|;·]/))
    .map((name) => name.trim())
    .filter(Boolean)

  for (const candidate of candidates) {
    const iconName = GUIDE_ICON_NAME_ALIASES[candidate] || candidate
    const key = normalizeIngredientImageName(iconName)
    const image = ingredientImages.find((item) => item.key === key)
    if (image) return image.src
  }
  return null
}

const TIP_DEFINITIONS = [
  { title: '보관방법', key: 'storage_tips', guideType: 'storage', sourceName: 'storage_source_name', sourceUrl: 'storage_source_url' },
  { title: '손질방법', key: 'prep_tips', guideType: 'prep', sourceName: 'prep_source_name', sourceUrl: 'prep_source_url' },
  { title: '세척방법', key: 'washing_tips', guideType: 'washing', sourceName: 'washing_source_name', sourceUrl: 'washing_source_url' },
  { title: '신선도 확인법', key: 'freshness_tips', guideType: 'freshness', sourceName: 'freshness_source_name', sourceUrl: 'freshness_source_url' },
]

function getAuthHeaders() {
  const token = window.localStorage.getItem('bobbeori-token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

function hasLoginToken() {
  return Boolean(window.localStorage.getItem('bobbeori-token'))
}

function splitTipText(text) {
  if (!text) return ['등록된 정보가 없습니다.']
  return String(text)
    .split(/\n{2,}|\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .slice(0, 4)
}

function normalizeSourceUrl(url) {
  if (!url) return null
  let normalized = String(url).trim().replace(/\s+/g, '')
  const schemeIndex = normalized.search(/https?:\/\//i)
  if (schemeIndex > 0) normalized = normalized.slice(schemeIndex)
  const duplicateSchemeIndex = normalized.slice(8).search(/https?:\/\//i)
  if (duplicateSchemeIndex >= 0) normalized = normalized.slice(0, duplicateSchemeIndex + 8)
  const duplicateViewIndex = normalized.indexOf('/view?', normalized.indexOf('/view?') + 1)
  if (duplicateViewIndex >= 0) normalized = normalized.slice(0, duplicateViewIndex)

  try {
    return new URL(normalized).href
  } catch {
    return null
  }
}

function buildGuideTips(guide) {
  return TIP_DEFINITIONS.map((definition) => {
    const guideText = guide?.[definition.key]
    const points = splitTipText(guideText)
    const source = definition.sourceName ? guide?.[definition.sourceName] : null
    const sourceUrl = definition.sourceUrl ? normalizeSourceUrl(guide?.[definition.sourceUrl]) : null
    return {
      ...definition,
      points,
      chip: source || '가이드 정보',
      source: source || '출처 정보 없음',
      sourceUrl,
      isMissing: !guideText,
    }
  })
}

function formatCategory(ingredient) {
  return [ingredient?.major_category, ingredient?.middle_category, ingredient?.minor_category]
    .filter(Boolean)
    .join(' > ')
}

function formatMonths(months = []) {
  return months.length ? `${months.join(', ')}월 제철` : '상시 확인'
}

function formatCookingTime(minutes) {
  return minutes == null ? '시간 정보 없음' : `${minutes}분`
}

function getGuideIcon(ingredient) {
  return getIngredientIcon(
    ingredient?.raw_name,
    ingredient?.name,
    ingredient?.representative_name,
    ...(ingredient?.aliases || []),
  )
}

function ImageSlot({ src, alt = '', label = '', className = '' }) {
  const fallback = label?.trim()?.[0] || '?'
  return (
    <span className={`guide-image-slot ${src ? 'is-filled' : ''} ${className}`}>
      {src ? <img src={src} alt={alt} /> : <span className="guide-image-slot__text">{fallback}</span>}
    </span>
  )
}

function Guide() {
  const navigate = useNavigate()
  const { ingredientName } = useParams()
  const selectedCode = ingredientName ? decodeURIComponent(ingredientName) : ''
  const isDetailPage = Boolean(selectedCode)

  const [selectedTipTitle, setSelectedTipTitle] = useState(TIP_DEFINITIONS[0].title)
  const [searchTerm, setSearchTerm] = useState('')
  const [selectedMajorCategory, setSelectedMajorCategory] = useState('')
  const [selectedMiddleCategory, setSelectedMiddleCategory] = useState('')
  const [categoryOptions, setCategoryOptions] = useState({
    major_categories: [],
    middle_categories: [],
  })
  const [page, setPage] = useState(1)
  const [guideItems, setGuideItems] = useState([])
  const [totalCount, setTotalCount] = useState(0)
  const [hasNextPage, setHasNextPage] = useState(false)
  const [selectedGuide, setSelectedGuide] = useState(null)
  const [recommendedRecipes, setRecommendedRecipes] = useState([])
  const [recipeStartIndex, setRecipeStartIndex] = useState(0)
  const [isListLoading, setIsListLoading] = useState(true)
  const [isDetailLoading, setIsDetailLoading] = useState(false)
  const [isRecipeLoading, setIsRecipeLoading] = useState(false)
  const [isLoggedIn, setIsLoggedIn] = useState(hasLoginToken)
  const [fridgeIngredients, setFridgeIngredients] = useState([])
  const [isFridgeLoading, setIsFridgeLoading] = useState(false)
  const [fridgeErrorMessage, setFridgeErrorMessage] = useState('')
  const [recipeErrorMessage, setRecipeErrorMessage] = useState('')
  const [errorMessage, setErrorMessage] = useState('')
  const [isSuggestionFormOpen, setIsSuggestionFormOpen] = useState(false)
  const [suggestionForm, setSuggestionForm] = useState(EMPTY_SUGGESTION_FORM)
  const [suggestionMessage, setSuggestionMessage] = useState('')
  const [isSuggestionSubmitting, setIsSuggestionSubmitting] = useState(false)

  useEffect(() => {
    const syncLoginState = () => setIsLoggedIn(hasLoginToken())

    window.addEventListener('storage', syncLoginState)
    window.addEventListener('bobbeori-auth-change', syncLoginState)
    return () => {
      window.removeEventListener('storage', syncLoginState)
      window.removeEventListener('bobbeori-auth-change', syncLoginState)
    }
  }, [])

  useEffect(() => {
    if (!isLoggedIn) {
      setFridgeIngredients([])
      setFridgeErrorMessage('')
      setIsFridgeLoading(false)
      return undefined
    }

    const controller = new AbortController()
    async function loadFridgeIngredients() {
      setIsFridgeLoading(true)
      setFridgeErrorMessage('')
      try {
        const response = await fetch(`${apiUrl}/api/v1/inventory`, {
          headers: getAuthHeaders(),
          signal: controller.signal,
        })
        if (!response.ok) throw new Error('냉장고 재료를 불러오지 못했습니다.')

        const data = await response.json()
        const uniqueNames = new Set()
        const ingredients = (Array.isArray(data) ? data : []).filter((ingredient) => {
          const normalizedName = String(ingredient?.name || '').replace(/\s/g, '').toLowerCase()
          if (!normalizedName || uniqueNames.has(normalizedName)) return false
          uniqueNames.add(normalizedName)
          return true
        })
        setFridgeIngredients(ingredients.slice(0, 6))
      } catch (error) {
        if (error.name !== 'AbortError') {
          setFridgeIngredients([])
          setFridgeErrorMessage(error.message)
        }
      } finally {
        if (!controller.signal.aborted) setIsFridgeLoading(false)
      }
    }

    loadFridgeIngredients()
    return () => controller.abort()
  }, [isLoggedIn])

  useEffect(() => {
    const controller = new AbortController()
    const timer = window.setTimeout(async () => {
      setIsListLoading(true)
      setErrorMessage('')
      try {
        const params = new URLSearchParams({
          page: String(page),
          page_size: String(GUIDE_PAGE_SIZE),
        })
        if (searchTerm.trim()) params.set('keyword', searchTerm.trim())
        if (selectedMajorCategory) params.set('major_category', selectedMajorCategory)
        if (selectedMiddleCategory) params.set('middle_category', selectedMiddleCategory)
        const response = await fetch(`${apiUrl}/api/v1/guide?${params}`, {
          headers: getAuthHeaders(),
          signal: controller.signal,
        })
        if (!response.ok) throw new Error('식재료 가이드를 불러오지 못했습니다.')
        const data = await response.json()
        setGuideItems(data.items || [])
        setTotalCount(data.total || 0)
        setHasNextPage(Boolean(data.has_next))
      } catch (error) {
        if (error.name !== 'AbortError') {
          setErrorMessage(error.message)
          setGuideItems([])
          setTotalCount(0)
          setHasNextPage(false)
        }
      } finally {
        if (!controller.signal.aborted) setIsListLoading(false)
      }
    }, 180)

    return () => {
      controller.abort()
      window.clearTimeout(timer)
    }
  }, [page, searchTerm, selectedMajorCategory, selectedMiddleCategory])

  useEffect(() => {
    setPage(1)
  }, [searchTerm, selectedMajorCategory, selectedMiddleCategory])

  useEffect(() => {
    setSelectedMiddleCategory('')
  }, [selectedMajorCategory])

  useEffect(() => {
    const controller = new AbortController()
    async function loadCategories() {
      try {
        const params = new URLSearchParams()
        if (searchTerm.trim()) params.set('keyword', searchTerm.trim())
        if (selectedMajorCategory) params.set('major_category', selectedMajorCategory)
        if (selectedMiddleCategory) params.set('middle_category', selectedMiddleCategory)
        const response = await fetch(`${apiUrl}/api/v1/guide/categories?${params}`, {
          headers: getAuthHeaders(),
          signal: controller.signal,
        })
        if (!response.ok) return
        const data = await response.json()
        setCategoryOptions((current) => ({
          major_categories: selectedMajorCategory ? current.major_categories : data.major_categories || [],
          middle_categories: selectedMiddleCategory ? current.middle_categories : data.middle_categories || [],
        }))
      } catch (error) {
        if (error.name !== 'AbortError') {
          setCategoryOptions({ major_categories: [], middle_categories: [] })
        }
      }
    }

    loadCategories()
    return () => controller.abort()
  }, [searchTerm, selectedMajorCategory, selectedMiddleCategory])

  useEffect(() => {
    if (!selectedCode) {
      setSelectedGuide(null)
      setRecommendedRecipes([])
      return
    }

    const controller = new AbortController()
    async function loadDetail() {
      setIsDetailLoading(true)
      setErrorMessage('')
      try {
        const response = await fetch(`${apiUrl}/api/v1/guide/detail/${encodeURIComponent(selectedCode)}`, {
          headers: getAuthHeaders(),
          signal: controller.signal,
        })
        if (!response.ok) throw new Error('선택한 식재료 가이드를 찾을 수 없습니다.')
        const data = await response.json()
        setSelectedGuide(data)
      } catch (error) {
        if (error.name !== 'AbortError') {
          setErrorMessage(error.message)
          setSelectedGuide(null)
        }
      } finally {
        if (!controller.signal.aborted) setIsDetailLoading(false)
      }
    }

    loadDetail()
    return () => controller.abort()
  }, [selectedCode])

  useEffect(() => {
    const ingredientName =
      selectedGuide?.raw_name || selectedGuide?.name || selectedGuide?.representative_name || ''

    if (!ingredientName) {
      setRecommendedRecipes([])
      setRecipeErrorMessage('')
      setIsRecipeLoading(false)
      return
    }

    const controller = new AbortController()
    async function loadRecommendedRecipes() {
      setIsRecipeLoading(true)
      setRecipeErrorMessage('')
      try {
        const params = new URLSearchParams({
          ingredient: ingredientName,
          page: '1',
          page_size: String(GUIDE_RECIPE_LIMIT),
        })
        const response = await fetch(`${apiUrl}/api/v1/recipes/search?${params}`, {
          signal: controller.signal,
        })
        if (!response.ok) throw new Error('추천 레시피를 불러오지 못했습니다.')
        const data = await response.json()
        setRecommendedRecipes(data.items || [])
        setRecipeStartIndex(0)
      } catch (error) {
        if (error.name !== 'AbortError') {
          setRecommendedRecipes([])
          setRecipeStartIndex(0)
          setRecipeErrorMessage(error.message)
        }
      } finally {
        if (!controller.signal.aborted) setIsRecipeLoading(false)
      }
    }

    loadRecommendedRecipes()
    return () => controller.abort()
  }, [selectedGuide])

  const searchSuggestions = guideItems.slice(0, 6)
  const featuredIngredients = isLoggedIn ? fridgeIngredients : searchSuggestions
  const totalPages = Math.max(1, Math.ceil(totalCount / GUIDE_PAGE_SIZE))
  const guideTips = useMemo(() => buildGuideTips(selectedGuide), [selectedGuide])
  const selectedTip = guideTips.find((tip) => tip.title === selectedTipTitle) ?? guideTips[0]
  const visibleRecommendedRecipes = recommendedRecipes.slice(
    recipeStartIndex,
    recipeStartIndex + GUIDE_RECIPE_VISIBLE_COUNT,
  )
  const canSlideRecipes = recommendedRecipes.length > GUIDE_RECIPE_VISIBLE_COUNT
  const canShowPreviousRecipes = recipeStartIndex > 0
  const canShowNextRecipes = recipeStartIndex + GUIDE_RECIPE_VISIBLE_COUNT < recommendedRecipes.length

  useEffect(() => {
    if (!guideTips.some((tip) => tip.title === selectedTipTitle)) {
      setSelectedTipTitle(guideTips[0].title)
    }
  }, [guideTips, selectedTipTitle])

  useEffect(() => {
    setIsSuggestionFormOpen(false)
    setSuggestionForm(EMPTY_SUGGESTION_FORM)
    setSuggestionMessage('')
    setIsSuggestionSubmitting(false)
  }, [selectedCode, selectedTipTitle])

  const selectIngredient = (ingredient) => {
    navigate(`/guide/${encodeURIComponent(ingredient.code)}`)
  }

  const selectFridgeIngredient = async (ingredient) => {
    const normalizedName = String(ingredient?.name || '').replace(/\s/g, '').toLowerCase()
    const loadedMatch = guideItems.find(
      (guide) => String(guide?.name || '').replace(/\s/g, '').toLowerCase() === normalizedName,
    )
    if (loadedMatch) {
      selectIngredient(loadedMatch)
      return
    }

    try {
      const params = new URLSearchParams({
        keyword: ingredient.name,
        page: '1',
        page_size: String(GUIDE_PAGE_SIZE),
      })
      const response = await fetch(`${apiUrl}/api/v1/guide?${params}`, { headers: getAuthHeaders() })
      if (response.ok) {
        const data = await response.json()
        const exactMatch = (data.items || []).find(
          (guide) => String(guide?.name || '').replace(/\s/g, '').toLowerCase() === normalizedName,
        )
        const guide = exactMatch || data.items?.[0]
        if (guide) {
          selectIngredient(guide)
          return
        }
      }
    } catch {
      // 검색 화면에서 사용자가 가장 가까운 가이드를 선택할 수 있도록 이어갑니다.
    }

    setSelectedMajorCategory('')
    setSelectedMiddleCategory('')
    setSearchTerm(ingredient.name)
    navigate('/guide')
  }

  const goToPage = (nextPage) => {
    const normalizedPage = Math.min(Math.max(Number(nextPage) || 1, 1), totalPages)
    setPage(normalizedPage)
  }

  const slideRecipes = (step) => {
    const maxStartIndex = Math.max(0, recommendedRecipes.length - GUIDE_RECIPE_VISIBLE_COUNT)
    setRecipeStartIndex((current) => Math.min(Math.max(current + step, 0), maxStartIndex))
  }

  const openSuggestionForm = () => {
    setSuggestionMessage('')
    if (!isLoggedIn) {
      setSuggestionMessage('가이드를 제보하려면 로그인이 필요합니다.')
      return
    }
    setIsSuggestionFormOpen(true)
  }

  const submitSuggestion = async (event) => {
    event.preventDefault()
    if (!selectedGuide || !selectedTip?.isMissing || isSuggestionSubmitting) return
    if (!isLoggedIn) {
      setSuggestionMessage('가이드를 제보하려면 로그인이 필요합니다.')
      return
    }

    setIsSuggestionSubmitting(true)
    setSuggestionMessage('')
    try {
      const response = await fetch(`${apiUrl}/api/v1/guide/suggestions`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...getAuthHeaders(),
        },
        body: JSON.stringify({
          ingredient_code: selectedGuide.code,
          guide_type: selectedTip.guideType,
          content: suggestionForm.content,
          source_name: suggestionForm.sourceName || null,
          source_url: suggestionForm.sourceUrl || null,
        }),
      })
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.detail || '가이드 제보를 저장하지 못했습니다.')
      }

      setSuggestionForm(EMPTY_SUGGESTION_FORM)
      setIsSuggestionFormOpen(false)
      setSuggestionMessage('제보가 접수되었습니다. 검토 후 가이드에 반영됩니다.')
    } catch (error) {
      setSuggestionMessage(error.message)
    } finally {
      setIsSuggestionSubmitting(false)
    }
  }

  return (
    <section className="guide-page" aria-labelledby="guide-title">
      <div className="guide-hero">
        <div className="guide-hero__copy">
          <h1 id="guide-title">식재료 가이드</h1>
          <p>재료별 보관, 손질, 세척, 신선도 팁을 한눈에 확인해요!</p>
        </div>

        <div className="guide-search-wrap">
          <label className="guide-search guide-hero__search" aria-label="식재료명 검색">
            <span aria-hidden="true" />
            <input
              placeholder="식재료명을 검색해보세요"
              type="search"
              value={searchTerm}
              onChange={(event) => setSearchTerm(event.target.value)}
            />
          </label>

          {searchTerm.trim() ? (
            <div className="guide-search-suggestions" aria-live="polite">
              {isListLoading ? (
                <p>검색 중...</p>
              ) : searchSuggestions.length ? (
                searchSuggestions.map((ingredient) => (
                  <button
                    key={ingredient.code}
                    type="button"
                    onClick={() => {
                      setSearchTerm('')
                      selectIngredient(ingredient)
                    }}
                  >
                    <strong>{ingredient.name}</strong>
                    <span>{formatCategory(ingredient) || '분류 정보 없음'}</span>
                  </button>
                ))
              ) : (
                <p>일치하는 식재료가 없습니다.</p>
              )}
            </div>
          ) : null}
        </div>

        <div className="guide-hero__art" aria-hidden="true">
          <img src={imageGuide} alt="" />
        </div>
      </div>

      {errorMessage ? <p className="guide-error">{errorMessage}</p> : null}

      <section className="guide-panel guide-ingredients" aria-labelledby="guide-ingredients-title">
        <div className="guide-section-title" id="guide-ingredients-title">
          {isLoggedIn ? '내 냉장고 재료' : '추천 식재료'}
        </div>
        <div
          className="guide-ingredient-list"
          aria-label={isLoggedIn ? '내 냉장고 재료 목록' : '추천 식재료 목록'}
        >
          {featuredIngredients.map((ingredient) => (
            <button
              className={`guide-ingredient ${
                isDetailPage && selectedGuide?.code === ingredient.code ? 'is-active' : ''
              }`}
              key={isLoggedIn ? `fridge-${ingredient.id}` : ingredient.code}
              type="button"
              onClick={() => (isLoggedIn ? selectFridgeIngredient(ingredient) : selectIngredient(ingredient))}
            >
              <ImageSlot
                alt=""
                className="guide-ingredient__image"
                label={ingredient.name}
                src={getGuideIcon(ingredient)}
              />
              <span>{ingredient.name}</span>
            </button>
          ))}
          {isLoggedIn && isFridgeLoading ? <p className="guide-empty">냉장고 재료를 불러오는 중입니다.</p> : null}
          {isLoggedIn && !isFridgeLoading && fridgeErrorMessage ? (
            <p className="guide-empty">{fridgeErrorMessage}</p>
          ) : null}
          {isLoggedIn && !isFridgeLoading && !fridgeErrorMessage && fridgeIngredients.length === 0 ? (
            <div className="guide-empty guide-fridge-empty">
              <strong>냉장고에 등록된 식재료가 없습니다.</strong>
              <span>냉장고 재료를 등록해주세요.</span>
            </div>
          ) : null}
          {!isLoggedIn && !isListLoading && searchSuggestions.length === 0 ? (
            <p className="guide-empty">추천할 식재료가 없습니다.</p>
          ) : null}
        </div>
      </section>

      {!isDetailPage ? (
        <section className="guide-panel guide-all" aria-labelledby="guide-all-title">
          <div className="guide-category-tabs" aria-label="식재료 분류 선택">
            <div>
              <div className="guide-category-tab-list" role="group" aria-label="대분류">
                <button
                  className={!selectedMajorCategory ? 'is-active' : ''}
                  type="button"
                  aria-pressed={!selectedMajorCategory}
                  onClick={() => setSelectedMajorCategory('')}
                >
                  전체
                </button>
                {categoryOptions.major_categories.map((category) => (
                  <button
                    className={selectedMajorCategory === category ? 'is-active' : ''}
                    key={category}
                    type="button"
                    aria-pressed={selectedMajorCategory === category}
                    onClick={() => setSelectedMajorCategory(category)}
                  >
                    {category}
                  </button>
                ))}
              </div>
            </div>

            {selectedMajorCategory ? (
              <div>
                <div className="guide-category-tab-list" role="group" aria-label="중분류">
                  <button
                    className={!selectedMiddleCategory ? 'is-active' : ''}
                    type="button"
                    aria-pressed={!selectedMiddleCategory}
                    onClick={() => setSelectedMiddleCategory('')}
                  >
                    전체
                  </button>
                  {categoryOptions.middle_categories.map((category) => (
                    <button
                      className={selectedMiddleCategory === category ? 'is-active' : ''}
                      key={category}
                      type="button"
                      aria-pressed={selectedMiddleCategory === category}
                      onClick={() => setSelectedMiddleCategory(category)}
                    >
                      {category}
                    </button>
                  ))}
                </div>
              </div>
            ) : null}
          </div>

          <div className="guide-all__header">
            <div>
              <h2 id="guide-all-title">전체 재료 목록</h2>
              <p>분류별로 재료를 넘겨 보며 보관, 손질, 세척 정보를 확인해요.</p>
            </div>
            <span>{isListLoading ? '불러오는 중' : `${totalCount}개 · ${page}/${totalPages}`}</span>
          </div>

          <div className="guide-all-list" aria-label="전체 재료 목록">
            {guideItems.map((ingredient) => (
              <button
                className="guide-all-item"
                key={ingredient.code}
                type="button"
                onClick={() => selectIngredient(ingredient)}
              >
                <ImageSlot
                  alt=""
                  className="guide-all-item__image"
                  label={ingredient.name}
                  src={getGuideIcon(ingredient)}
                />
                <div>
                  <strong>{ingredient.name}</strong>
                  <p>{formatCategory(ingredient) || '분류 정보 없음'}</p>
                  <small>{formatMonths(ingredient.seasonal_months)}</small>
                </div>
                <span aria-hidden="true" />
              </button>
            ))}
          </div>

          <div className="guide-pagination" aria-label="식재료 목록 페이지">
            <button type="button" disabled={page <= 1 || isListLoading} onClick={() => goToPage(page - 1)}>
              이전
            </button>

            <span className="guide-pagination__status" aria-current="page">
              {page} / {totalPages}
            </span>

            <button type="button" disabled={!hasNextPage || isListLoading} onClick={() => goToPage(page + 1)}>
              다음
            </button>
          </div>
        </section>
      ) : (
        <>
          {isDetailLoading ? (
            <section className="guide-panel guide-detail guide-loading">가이드를 불러오는 중입니다.</section>
          ) : selectedGuide ? (
            <>
              <div className="guide-content-grid">
                <article className="guide-panel guide-detail">
                  <button
                    className="guide-detail-back"
                    type="button"
                    aria-label="전체 식재료 목록으로 돌아가기"
                    title="전체 목록"
                    onClick={() => navigate('/guide')}
                  >
                    ←
                  </button>
                  <div className="guide-detail__header">
                    <ImageSlot
                      alt=""
                      className="guide-detail__image"
                      label={selectedGuide.name}
                      src={getGuideIcon(selectedGuide)}
                    />
                    <div>
                      <h2>{selectedGuide.name}</h2>
                      <p>{formatCategory(selectedGuide) || '분류 정보 없음'}</p>
                      {normalizeSourceUrl(selectedGuide.seasonal_source_url) ? (
                        <a
                          className="guide-owned-badge"
                          href={normalizeSourceUrl(selectedGuide.seasonal_source_url)}
                          target="_blank"
                          rel="noreferrer"
                          title={selectedGuide.seasonal_source_name || '제철 출처'}
                        >
                          {formatMonths(selectedGuide.seasonal_months)}
                        </a>
                      ) : (
                        <span className="guide-owned-badge">{formatMonths(selectedGuide.seasonal_months)}</span>
                      )}
                    </div>
                  </div>

                  <div className="guide-tip-grid">
                    {guideTips.map((tip) => (
                      <section
                        className={`guide-tip-card ${selectedTip.title === tip.title ? 'is-active' : ''}`}
                        key={tip.title}
                        role="button"
                        tabIndex={0}
                        onClick={() => setSelectedTipTitle(tip.title)}
                        onKeyDown={(event) => {
                          if (event.key === 'Enter' || event.key === ' ') {
                            event.preventDefault()
                            setSelectedTipTitle(tip.title)
                          }
                        }}
                      >
                        <div className="guide-tip-card__title">
                          <span aria-hidden="true" />
                          <h3>{tip.title}</h3>
                        </div>
                        <ul>
                          {tip.points.map((point) => (
                            <li key={point}>{point}</li>
                          ))}
                        </ul>
                      </section>
                    ))}
                  </div>
                </article>

                <aside className="guide-panel guide-tip-detail" aria-labelledby="guide-tip-detail-title">
                  <span>{selectedGuide.name}</span>
                  <h2 id="guide-tip-detail-title">{selectedTip.title}</h2>
                  <ul>
                    {selectedTip.points.map((point) => (
                      <li key={point}>{point}</li>
                    ))}
                  </ul>
                  <div className="guide-tip-source">
                    {selectedTip.sourceUrl ? (
                      <a href={selectedTip.sourceUrl} target="_blank" rel="noreferrer">
                        {selectedTip.source}
                      </a>
                    ) : (
                      <span>{selectedTip.source}</span>
                    )}
                  </div>

                  {selectedTip.isMissing ? (
                    <section className="guide-suggestion" aria-labelledby="guide-suggestion-title">
                      <div className="guide-suggestion__intro">
                        <h3 id="guide-suggestion-title">나만의 가이드 제보</h3>
                        <p>직접 알고 있는 방법과 참고 출처를 남겨주세요. 개발자가 확인한 뒤 반영합니다.</p>
                      </div>

                      {isSuggestionFormOpen ? (
                        <form className="guide-suggestion__form" onSubmit={submitSuggestion}>
                          <label>
                            <span>가이드 내용</span>
                            <textarea
                              maxLength={2000}
                              minLength={10}
                              placeholder={`${selectedGuide.name} ${selectedTip.title}을 10자 이상 입력해주세요.`}
                              required
                              value={suggestionForm.content}
                              onChange={(event) =>
                                setSuggestionForm((current) => ({ ...current, content: event.target.value }))
                              }
                            />
                          </label>
                          <div className="guide-suggestion__source-fields">
                            <label>
                              <span>출처명 (선택)</span>
                              <input
                                maxLength={255}
                                placeholder="예: 농촌진흥청"
                                value={suggestionForm.sourceName}
                                onChange={(event) =>
                                  setSuggestionForm((current) => ({ ...current, sourceName: event.target.value }))
                                }
                              />
                            </label>
                            <label>
                              <span>출처 URL (선택)</span>
                              <input
                                placeholder="https://example.com"
                                type="url"
                                value={suggestionForm.sourceUrl}
                                onChange={(event) =>
                                  setSuggestionForm((current) => ({ ...current, sourceUrl: event.target.value }))
                                }
                              />
                            </label>
                          </div>
                          <div className="guide-suggestion__actions">
                            <button
                              type="button"
                              onClick={() => {
                                setIsSuggestionFormOpen(false)
                                setSuggestionMessage('')
                              }}
                            >
                              취소
                            </button>
                            <button disabled={isSuggestionSubmitting} type="submit">
                              {isSuggestionSubmitting ? '접수 중...' : '제보하기'}
                            </button>
                          </div>
                        </form>
                      ) : (
                        <button className="guide-suggestion__open" type="button" onClick={openSuggestionForm}>
                          {isLoggedIn ? '가이드 제보하기' : '로그인 후 제보하기'}
                        </button>
                      )}

                      {suggestionMessage ? <p className="guide-suggestion__message" role="status">{suggestionMessage}</p> : null}
                    </section>
                  ) : null}

                  <section className="guide-tip-nutrition" aria-labelledby="guide-nutrition-title">
                    <div className="guide-tip-nutrition__header">
                      <h3 id="guide-nutrition-title">영양성분</h3>
                      <span>{selectedGuide.nutrition_base_amount || '기준량 정보 없음'}</span>
                      {selectedGuide.nutrition_source_name ? <span>출처: {selectedGuide.nutrition_source_name}</span> : null}
                    </div>

                    <div className="guide-nutrition-grid">
                      <strong>에너지 {selectedGuide.energy_kcal ?? '-'} kcal</strong>
                      <strong>단백질 {selectedGuide.protein_g ?? '-'} g</strong>
                      <strong>지방 {selectedGuide.fat_g ?? '-'} g</strong>
                      <strong>탄수화물 {selectedGuide.carbohydrate_g ?? '-'} g</strong>
                      <strong>칼륨 {selectedGuide.potassium_mg ?? '-'} mg</strong>
                      <strong>나트륨 {selectedGuide.sodium_mg ?? '-'} mg</strong>
                    </div>
                  </section>
                </aside>
              </div>

              <section className="guide-panel guide-recipes" aria-labelledby="guide-recipes-title">
                <div className="guide-recipes__header">
                  <div>
                    <h2 id="guide-recipes-title">추천 레시피</h2>
                    <span>{selectedGuide.name} 활용</span>
                  </div>
                </div>

                {isRecipeLoading ? (
                  <p className="guide-recipe-status">추천 레시피를 불러오는 중입니다.</p>
                ) : recipeErrorMessage ? (
                  <p className="guide-recipe-status guide-recipe-status--error">{recipeErrorMessage}</p>
                ) : recommendedRecipes.length ? (
                  <div className="guide-recipe-carousel">
                    {canSlideRecipes ? (
                      <button
                        className="guide-recipe-arrow"
                        type="button"
                        aria-label="이전 추천 레시피"
                        disabled={!canShowPreviousRecipes}
                        onClick={() => slideRecipes(-1)}
                      >
                        ‹
                      </button>
                    ) : null}
                    <div className="guide-recipe-list" aria-label={`${selectedGuide.name} 추천 레시피`}>
                      {visibleRecommendedRecipes.map((recipe) => (
                        <article
                          className="guide-recipe-card"
                          key={recipe.recipe_id}
                          role="button"
                          tabIndex={0}
                          onClick={() => navigate(`/recipes/${recipe.recipe_id}`)}
                          onKeyDown={(event) => {
                            if (event.key === 'Enter' || event.key === ' ') {
                              event.preventDefault()
                              navigate(`/recipes/${recipe.recipe_id}`)
                            }
                          }}
                        >
                          <ImageSlot
                            alt=""
                            className="guide-recipe-card__image"
                            src={recipe.main_image_url}
                          />
                          <div>
                            <span>{recipe.category || '추천 메뉴'}</span>
                            <h3>{recipe.title}</h3>
                            <p>
                              {formatCookingTime(recipe.cooking_time_min)} · {recipe.difficulty || '난이도 정보 없음'}
                            </p>
                          </div>
                        </article>
                      ))}
                    </div>
                    {canSlideRecipes ? (
                      <button
                        className="guide-recipe-arrow"
                        type="button"
                        aria-label="다음 추천 레시피"
                        disabled={!canShowNextRecipes}
                        onClick={() => slideRecipes(1)}
                      >
                        ›
                      </button>
                    ) : null}
                  </div>
                ) : (
                  <article className="guide-recipe-more">
                    <ImageSlot alt="" className="guide-recipe-more__icon" src={iconBasket} />
                    <strong>{selectedGuide.name}로 바로 보여줄 추천 레시피가 아직 없습니다.</strong>
                  </article>
                )}
              </section>
            </>
          ) : (
            <section className="guide-panel guide-detail guide-empty">선택한 식재료를 찾을 수 없습니다.</section>
          )}
        </>
      )}
    </section>
  )
}

export default Guide
