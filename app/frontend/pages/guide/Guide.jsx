import React, { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import './Guide.css'

import iconBasket from '../../assets/extracted/icons/icon_basket.png'
import imageGuide from '../../assets/extracted/images/image_guide_v2.webp'
import { API_URL } from '../../utils/api.js'
import { getIngredientImageUrl, useIngredientImageCatalog } from '../../utils/ingredientImages.js'

const GUIDE_PAGE_SIZE = 12
const FRIDGE_PAGE_SIZE = 16
const GUEST_RECOMMENDATION_PAGE_SIZE = 8
const SEASONAL_RECOMMENDATION_SIZE = 60
const GUIDE_RECIPE_LIMIT = 12
const EMPTY_SUGGESTION_FORM = { content: '', sourceUrl: '' }
const GUIDE_IMAGE_IDS = {
  ingredient_0003: 'ingredient_51dca13d2627a424',
  ingredient_0030: 'ingredient_4b16a7f04f2247a6',
  ingredient_0055: 'ingredient_8fb8d89ced712eb0',
  ingredient_0070: 'ingredient_0be95d89abe806ff',
  ingredient_0144: 'ingredient_50dfae78057c79cf',
  ingredient_0147: 'ingredient_140a705c797b2b38',
  ingredient_0209: 'ingredient_04969005d14278f7',
  ingredient_0254: 'ingredient_8a4b20bb8def6d4a',
  ingredient_0255: 'ingredient_6ec8fa4ace72e30e',
  ingredient_0332: 'ingredient_7bf3f7a2700a542a',
  ingredient_0365: 'ingredient_7ab9f2a8c9750517',
  ingredient_0368: 'ingredient_b4117056b351c9b6',
  ingredient_0472: 'ingredient_e68143b756f0b610',
  ingredient_0474: 'ingredient_b422625dd360b54d',
  ingredient_0479: 'ingredient_5cf37d871691fe94',
  ingredient_0482: 'ingredient_ccdc5f2d5acb130c',
  ingredient_0484: 'ingredient_36722c46ccc9a8d1',
  ingredient_0492: 'ingredient_55bade89cf4082fe',
  ingredient_0534: 'ingredient_79db0b3ebc94daa7',
  ingredient_0545: 'ingredient_00b2205322c7f2b9',
  ingredient_0548: 'ingredient_bfd8c560497bbfa8',
  ingredient_0576: 'ingredient_ebaa36583b3f0eac',
  ingredient_0627: 'ingredient_a7f7ec597ecbc841',
  ingredient_0633: 'ingredient_07cff3f1a2bfcaf1',
  ingredient_0660: 'ingredient_ccc4da97bcead35b',
  ingredient_0708: 'ingredient_6a3d8245ace0ee9c',
  ingredient_0715: 'ingredient_62689689a23bd56f',
  ingredient_0719: 'ingredient_8cc673fe50722433',
  ingredient_0736: 'ingredient_087be49a1ecfb668',
}

const TIP_DEFINITIONS = [
  { title: '보관방법', key: 'storage_tips', guideType: 'storage', sourceName: 'storage_source_name', sourceUrl: 'storage_source_url' },
  { title: '손질방법', key: 'prep_tips', guideType: 'prep', sourceName: 'prep_source_name', sourceUrl: 'prep_source_url' },
  { title: '세척방법', key: 'washing_tips', guideType: 'washing', sourceName: 'washing_source_name', sourceUrl: 'washing_source_url' },
  { title: '신선도 확인법', key: 'freshness_tips', guideType: 'freshness', sourceName: 'freshness_source_name', sourceUrl: 'freshness_source_url' },
]

const SOURCE_URL_FALLBACKS = {
  '해물류 기존 가이드 참고': 'https://fsis.go.kr/front/contents/cmsView.do?cate_id=0101&cnts_id=16951&select_list_no=7',
  '건어물류 기존 가이드 참고': 'https://fsis.go.kr/front/contents/cmsView.do?cate_id=0101&cnts_id=16951&select_list_no=7',
  '닭고기 분류 기존 가이드 참고': 'https://www.nics.go.kr/food/kfi/foodMonth/view?fd_se=286&fd_snn=70&menuId=PS03599',
  '닭고기 분류 기준 가이드 참고': 'https://www.nics.go.kr/food/kfi/foodMonth/view?fd_se=286&fd_snn=70&menuId=PS03599',
  '돼지고기 분류 기존 가이드 참고': 'https://www.nics.go.kr/food/kfi/foodMonth/view?fd_se=286&fd_snn=42&menuId=PS03599',
  '소고기 분류 기존 가이드 참고': 'https://www.nics.go.kr/food/kfi/foodMonth/view?fd_se=286&fd_snn=109&menuId=PS03599',
}

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
    const sourceUrl =
      (definition.sourceUrl ? normalizeSourceUrl(guide?.[definition.sourceUrl]) : null) ||
      normalizeSourceUrl(SOURCE_URL_FALLBACKS[source])
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

function shouldShowMissingGuideTip(guide, tip) {
  const major = guide?.major_category || ''
  const middle = guide?.middle_category || ''

  if (tip.guideType === 'storage' || tip.guideType === 'freshness') return true
  if (['소스·양념류', '유지류', '음료·당류'].includes(middle)) return false
  if (tip.guideType === 'washing') return major === '농산물' || major === '수산물'
  return true
}

function formatCategory(ingredient) {
  return [ingredient?.major_category, ingredient?.middle_category, ingredient?.minor_category]
    .filter(Boolean)
    .join(' > ')
}

function formatMonths(months = []) {
  const sortedMonths = [...months].sort((a, b) => Number(a) - Number(b))
  return sortedMonths.length ? `${sortedMonths.join(', ')}월 제철` : '상시 확인'
}

function formatCookingTime(minutes) {
  return minutes == null ? '시간 정보 없음' : `${minutes}분`
}

function getGuideIcon(catalog, ingredient) {
  const imageId = GUIDE_IMAGE_IDS[ingredient?.code]
  const mappedImage = imageId && catalog?.items.find((item) => item.id === imageId)
  if (mappedImage) return mappedImage.imageUrl

  return getIngredientImageUrl(
    catalog,
    [
      ingredient?.name,
      ingredient?.raw_name,
      ingredient?.representative_name,
    ],
    [ingredient?.middle_category, ingredient?.major_category],
    false,
  )
}

function getFridgeNameFontSize(name = '') {
  const length = String(name).replace(/\s/g, '').length
  if (length > 16) return '9px'
  if (length > 12) return '10px'
  if (length > 8) return '11px'
  if (length > 5) return '13px'
  return '16px'
}

function ImageSlot({ src, alt = '', className = '' }) {
  return (
    <span className={`guide-image-slot is-filled ${src ? '' : 'is-placeholder'} ${className}`}>
      {src ? (
        <img src={src} alt={alt} decoding="async" />
      ) : (
        <span className="guide-image-placeholder" aria-hidden="true">
          <svg viewBox="0 0 48 48">
            <path d="M10 34h28M14 31a10 10 0 0 1 20 0M21 18h6M24 18v3" />
          </svg>
        </span>
      )}
    </span>
  )
}

function Guide() {
  const navigate = useNavigate()
  const { ingredientName } = useParams()
  const ingredientImageCatalog = useIngredientImageCatalog()
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
  const [seasonalGuideItems, setSeasonalGuideItems] = useState([])
  const [totalCount, setTotalCount] = useState(0)
  const [hasNextPage, setHasNextPage] = useState(false)
  const [selectedGuide, setSelectedGuide] = useState(null)
  const [recommendedRecipes, setRecommendedRecipes] = useState([])
  const [recipeSlideIndex, setRecipeSlideIndex] = useState(0)
  const [recipeSlideDirection, setRecipeSlideDirection] = useState('next')
  const recipeDragStartY = useRef(null)
  const recipeDidDrag = useRef(false)
  const [isListLoading, setIsListLoading] = useState(true)
  const [isDetailLoading, setIsDetailLoading] = useState(false)
  const [isRecipeLoading, setIsRecipeLoading] = useState(false)
  const [isLoggedIn, setIsLoggedIn] = useState(hasLoginToken)
  const [fridgeIngredients, setFridgeIngredients] = useState([])
  const [fridgePage, setFridgePage] = useState(1)
  const [guestRecommendationPage, setGuestRecommendationPage] = useState(1)
  const [selectedSeasonalMonth, setSelectedSeasonalMonth] = useState(() => new Date().getMonth() + 1)
  const [isSeasonalMonthMenuOpen, setIsSeasonalMonthMenuOpen] = useState(false)
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
      setFridgePage(1)
      setFridgeErrorMessage('')
      setIsFridgeLoading(false)
      return undefined
    }

    const controller = new AbortController()
    async function loadFridgeIngredients() {
      setIsFridgeLoading(true)
      setFridgeErrorMessage('')
      try {
        const response = await fetch(`${API_URL}/api/v1/inventory`, {
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
        setFridgeIngredients(ingredients)
        setFridgePage(1)
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
        const response = await fetch(`${API_URL}/api/v1/guide?${params}`, {
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
    const controller = new AbortController()
    async function loadSeasonalRecommendations() {
      try {
        const seasonalItems = []
        for (let nextPage = 1; ; nextPage += 1) {
          const params = new URLSearchParams({
            page: String(nextPage),
            page_size: String(SEASONAL_RECOMMENDATION_SIZE),
          })
          const response = await fetch(`${API_URL}/api/v1/guide?${params}`, {
            headers: getAuthHeaders(),
            signal: controller.signal,
          })
          if (!response.ok) return
          const data = await response.json()
          seasonalItems.push(
            ...(data.items || []).filter((ingredient) => ingredient.seasonal_months?.includes(selectedSeasonalMonth)),
          )
          if (!data.has_next) break
        }
        setSeasonalGuideItems(seasonalItems)
        setGuestRecommendationPage(1)
      } catch (error) {
        if (error.name !== 'AbortError') setSeasonalGuideItems([])
      }
    }

    loadSeasonalRecommendations()
    return () => controller.abort()
  }, [selectedSeasonalMonth])

  useEffect(() => {
    setPage(1)
    setGuestRecommendationPage(1)
  }, [searchTerm, selectedMajorCategory, selectedMiddleCategory])

  const selectMajorCategory = (category) => {
    setSelectedMajorCategory(category)
    setSelectedMiddleCategory('')
    setCategoryOptions((current) => ({ ...current, middle_categories: [] }))
  }

  useEffect(() => {
    const controller = new AbortController()
    async function loadCategories() {
      try {
        const params = new URLSearchParams()
        if (searchTerm.trim()) params.set('keyword', searchTerm.trim())
        if (selectedMajorCategory) params.set('major_category', selectedMajorCategory)
        if (selectedMiddleCategory) params.set('middle_category', selectedMiddleCategory)
        const response = await fetch(`${API_URL}/api/v1/guide/categories?${params}`, {
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
        const response = await fetch(`${API_URL}/api/v1/guide/detail/${encodeURIComponent(selectedCode)}`, {
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
    setRecipeSlideIndex(0)
    setRecipeSlideDirection('next')

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
        const response = await fetch(`${API_URL}/api/v1/recipes/search?${params}`, {
          signal: controller.signal,
        })
        if (!response.ok) throw new Error('추천 레시피를 불러오지 못했습니다.')
        const data = await response.json()
        setRecommendedRecipes(data.items || [])
      } catch (error) {
        if (error.name !== 'AbortError') {
          setRecommendedRecipes([])
          setRecipeErrorMessage(error.message)
        }
      } finally {
        if (!controller.signal.aborted) setIsRecipeLoading(false)
      }
    }

    loadRecommendedRecipes()
    return () => controller.abort()
  }, [selectedGuide])

  const currentRecommendedRecipe = recommendedRecipes[recipeSlideIndex]
  const slideRecommendedRecipe = (direction) => {
    setRecipeSlideDirection(direction)
    setRecipeSlideIndex((current) => (
      current + (direction === 'next' ? 1 : -1) + recommendedRecipes.length
    ) % recommendedRecipes.length)
  }

  useEffect(() => {
    if (recommendedRecipes.length <= 1) return undefined

    const intervalId = window.setInterval(() => {
      if (document.hidden || recipeDragStartY.current != null) return
      setRecipeSlideDirection('next')
      setRecipeSlideIndex((current) => (current + 1) % recommendedRecipes.length)
    }, 5000)

    return () => window.clearInterval(intervalId)
  }, [recommendedRecipes.length])

  const resetRecipeDragVisual = (target) => {
    target.classList.remove('is-dragging')
    target.querySelector('.guide-recipe-card')?.style.removeProperty('transform')
  }
  const handleRecipeDragStart = (event) => {
    if (recommendedRecipes.length <= 1 || !event.isPrimary || (event.pointerType === 'mouse' && event.button !== 0)) return
    recipeDragStartY.current = event.clientY
    recipeDidDrag.current = false
    event.currentTarget.setPointerCapture(event.pointerId)
  }
  const handleRecipeDragMove = (event) => {
    if (recipeDragStartY.current == null) return
    const distance = event.clientY - recipeDragStartY.current
    if (Math.abs(distance) > 6) recipeDidDrag.current = true
    event.currentTarget.classList.toggle('is-dragging', recipeDidDrag.current)
    const card = event.currentTarget.querySelector('.guide-recipe-card')
    if (card) card.style.transform = `translateY(${Math.max(-80, Math.min(80, distance))}px)`
  }
  const handleRecipeDragEnd = (event) => {
    if (recipeDragStartY.current == null) return
    const distance = event.clientY - recipeDragStartY.current
    recipeDragStartY.current = null
    resetRecipeDragVisual(event.currentTarget)
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId)
    if (Math.abs(distance) >= 48) slideRecommendedRecipe(distance < 0 ? 'next' : 'previous')
    window.setTimeout(() => { recipeDidDrag.current = false }, 0)
  }

  const searchSuggestions = guideItems
  const currentMonth = selectedSeasonalMonth
  const seasonalMonthControl = (
    <div
      className="guide-seasonal-month-control"
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) setIsSeasonalMonthMenuOpen(false)
      }}
    >
      <button
        className="guide-seasonal-month-button"
        type="button"
        aria-expanded={isSeasonalMonthMenuOpen}
        aria-label="제철 식재료 월 선택"
      onClick={() => setIsSeasonalMonthMenuOpen((isOpen) => !isOpen)}
    >
      {currentMonth}월
      <svg aria-hidden="true" viewBox="0 0 12 12">
        <path d="m3 4.5 3 3 3-3" />
      </svg>
      </button>
      {isSeasonalMonthMenuOpen ? (
        <div className="guide-seasonal-month-menu" role="menu">
          {Array.from({ length: 12 }, (_, index) => index + 1).map((month) => (
            <button
              className={month === selectedSeasonalMonth ? 'is-active' : ''}
              key={month}
              type="button"
              role="menuitem"
              onClick={() => {
                setSelectedSeasonalMonth(month)
                setIsSeasonalMonthMenuOpen(false)
              }}
            >
              {month}월
            </button>
          ))}
        </div>
      ) : null}
    </div>
  )
  const seasonalTotalPages = Math.max(1, Math.ceil(seasonalGuideItems.length / GUEST_RECOMMENDATION_PAGE_SIZE))
  const seasonalFeaturedIngredients = seasonalGuideItems.slice(
    (guestRecommendationPage - 1) * GUEST_RECOMMENDATION_PAGE_SIZE,
    guestRecommendationPage * GUEST_RECOMMENDATION_PAGE_SIZE,
  )
  const guestRecommendationItems = seasonalGuideItems
  const guestTotalPages = Math.max(1, Math.ceil(guestRecommendationItems.length / GUEST_RECOMMENDATION_PAGE_SIZE))
  const guestSuggestions = guestRecommendationItems.slice(
    (guestRecommendationPage - 1) * GUEST_RECOMMENDATION_PAGE_SIZE,
    guestRecommendationPage * GUEST_RECOMMENDATION_PAGE_SIZE,
  )
  const fridgeTotalPages = Math.max(1, Math.ceil(fridgeIngredients.length / FRIDGE_PAGE_SIZE))
  const fridgeFeaturedIngredients = fridgeIngredients.slice(
    (fridgePage - 1) * FRIDGE_PAGE_SIZE,
    fridgePage * FRIDGE_PAGE_SIZE,
  )
  const featuredTotalPages = isLoggedIn ? fridgeTotalPages : guestTotalPages
  const canPageFeaturedIngredients = featuredTotalPages > 1
  const featuredIngredients = isLoggedIn ? fridgeFeaturedIngredients : guestSuggestions
  const totalPages = Math.max(1, Math.ceil(totalCount / GUIDE_PAGE_SIZE))
  const guideTips = useMemo(() => buildGuideTips(selectedGuide), [selectedGuide])
  const visibleGuideTips = useMemo(
    () => guideTips.filter((tip) => !tip.isMissing || shouldShowMissingGuideTip(selectedGuide, tip)),
    [guideTips, selectedGuide],
  )
  const selectedTip = visibleGuideTips.find((tip) => tip.title === selectedTipTitle) ?? visibleGuideTips[0]
  useEffect(() => {
    setGuestRecommendationPage((current) => Math.min(current, isLoggedIn ? seasonalTotalPages : guestTotalPages))
  }, [guestTotalPages, isLoggedIn, seasonalTotalPages])

  useEffect(() => {
    if (!visibleGuideTips.some((tip) => tip.title === selectedTipTitle)) {
      setSelectedTipTitle(visibleGuideTips[0]?.title ?? TIP_DEFINITIONS[0].title)
    }
  }, [visibleGuideTips, selectedTipTitle])

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
      const response = await fetch(`${API_URL}/api/v1/guide?${params}`, { headers: getAuthHeaders() })
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

  const renderIngredientButton = (ingredient, { isFridge = false } = {}) => (
    <button
      className={`guide-ingredient ${isDetailPage && selectedGuide?.code === ingredient.code ? 'is-active' : ''}`}
      key={isFridge ? `fridge-${ingredient.id}` : ingredient.code}
      type="button"
      onClick={() => (isFridge ? selectFridgeIngredient(ingredient) : selectIngredient(ingredient))}
    >
      <ImageSlot
        alt=""
        className="guide-ingredient__image"
        label={ingredient.name}
        src={getGuideIcon(ingredientImageCatalog, ingredient)}
      />
      <span
        className={`guide-ingredient__name ${
          String(ingredient.name || '').replace(/\s/g, '').length <= 5 ? 'is-short' : ''
        }`}
        style={{ '--guide-ingredient-name-size': getFridgeNameFontSize(ingredient.name) }}
      >
        {ingredient.name}
      </span>
    </button>
  )

  const goToPage = (nextPage) => {
    const normalizedPage = Math.min(Math.max(Number(nextPage) || 1, 1), totalPages)
    setPage(normalizedPage)
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
      const response = await fetch(`${API_URL}/api/v1/guide/suggestions`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...getAuthHeaders(),
        },
        body: JSON.stringify({
          ingredient_code: selectedGuide.code,
          guide_type: selectedTip.guideType,
          content: suggestionForm.content,
          source_name: null,
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
    <section
      className={`guide-page${isDetailPage ? ' guide-page--detail' : ''}`}
      aria-label={isDetailPage ? '식재료 가이드 상세' : undefined}
      aria-labelledby={isDetailPage ? undefined : 'guide-title'}
    >
      {!isDetailPage ? (
        <>
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

      <section
        className={`guide-ingredients${isLoggedIn ? '' : ' guide-ingredients--seasonal'}`}
        aria-labelledby="guide-ingredients-title"
      >
          <div className="guide-ingredients__header">
            <div className="guide-section-title" id="guide-ingredients-title">
            {isLoggedIn ? '내 냉장고 재료' : `${currentMonth}월 제철 식재료`}
          </div>
          <div className="guide-ingredients__actions">
            {!isLoggedIn ? seasonalMonthControl : null}
              {isLoggedIn && canPageFeaturedIngredients ? (
                <span className="guide-list-summary" aria-current="page">
                  {fridgeIngredients.length}개 · {fridgePage}/{fridgeTotalPages}
                </span>
              ) : null}
          </div>
        </div>
        <div className="guide-fridge-pager">
          {canPageFeaturedIngredients ? (
            <button
              className="guide-fridge-page-button is-previous"
              type="button"
              aria-label={isLoggedIn ? '이전 냉장고 재료 페이지' : '이전 제철 식재료 페이지'}
              disabled={isLoggedIn ? fridgePage <= 1 : guestRecommendationPage <= 1}
              onClick={() =>
                isLoggedIn
                  ? setFridgePage((current) => Math.max(1, current - 1))
                  : setGuestRecommendationPage((current) => Math.max(1, current - 1))
              }
            >
              ‹
            </button>
          ) : null}
          <div
            className="guide-ingredient-list"
            aria-label={isLoggedIn ? '내 냉장고 재료 목록' : '추천 식재료 목록'}
          >
          {featuredIngredients.map((ingredient) => renderIngredientButton(ingredient, { isFridge: isLoggedIn }))}
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
          {!isLoggedIn && !isListLoading && guestSuggestions.length === 0 ? (
            <p className="guide-empty">{currentMonth}월 제철 식재료가 없습니다.</p>
          ) : null}
          </div>
          {canPageFeaturedIngredients ? (
            <button
              className="guide-fridge-page-button is-next"
              type="button"
              aria-label={isLoggedIn ? '다음 냉장고 재료 페이지' : '다음 제철 식재료 페이지'}
              disabled={isLoggedIn ? fridgePage >= fridgeTotalPages : guestRecommendationPage >= guestTotalPages}
              onClick={() =>
                isLoggedIn
                  ? setFridgePage((current) => Math.min(fridgeTotalPages, current + 1))
                  : setGuestRecommendationPage((current) => Math.min(guestTotalPages, current + 1))
              }
            >
              ›
            </button>
          ) : null}
        </div>
      </section>
        </>
      ) : null}

      {!isDetailPage ? (
        <section className="guide-all" aria-label="전체 재료 목록">
          <div className="guide-category-tabs" aria-label="식재료 분류 선택">
            <div>
              <div className="guide-category-tab-list guide-category-tab-list--major" role="group" aria-label="대분류">
                <button
                  className={!selectedMajorCategory ? 'is-active' : ''}
                  type="button"
                  aria-pressed={!selectedMajorCategory}
                  onClick={() => selectMajorCategory('')}
                >
                  전체
                </button>
                {categoryOptions.major_categories.map((category) => (
                  <button
                    className={selectedMajorCategory === category ? 'is-active' : ''}
                    key={category}
                    type="button"
                    aria-pressed={selectedMajorCategory === category}
                    onClick={() => selectMajorCategory(category)}
                  >
                    {category}
                  </button>
                ))}
              </div>
            </div>

            {selectedMajorCategory ? (
              <div>
                <div className="guide-category-tab-list guide-category-tab-list--middle" role="group" aria-label="중분류">
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
            <span className="guide-list-summary">
              {isListLoading ? '불러오는 중' : `${totalCount}개 · ${page}/${totalPages}`}
            </span>
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
                  src={getGuideIcon(ingredientImageCatalog, ingredient)}
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
              <nav className="guide-detail-nav" aria-label="가이드 목록으로 돌아가기">
                <button type="button" onClick={() => navigate('/guide')}>← 가이드 목록</button>
              </nav>

              <div className="guide-detail-primary">
                <div className="guide-detail-heading">
                  <p className="guide-detail-category">
                    {[selectedGuide.major_category, selectedGuide.middle_category, selectedGuide.minor_category]
                      .filter((category) => category && category !== selectedGuide.name)
                      .join(' > ') || '식재료'}
                  </p>
                  <h1 id="guide-detail-title">{selectedGuide.name}</h1>
                </div>
                <article className="guide-detail-summary">
                  <div className="guide-detail-visual">
                    <ImageSlot
                      alt=""
                      className="guide-detail-visual__image"
                      label={selectedGuide.name}
                      src={getGuideIcon(ingredientImageCatalog, selectedGuide)}
                    />
                    <span className="guide-detail-season">
                      <i aria-hidden="true" />
                      {formatMonths(selectedGuide.seasonal_months)}
                    </span>
                  </div>
                </article>

                <aside className={`guide-detail-guide ${selectedTip.isMissing ? 'is-missing' : ''}`} aria-label="식재료 가이드 상세">
                  <div
                    className={`guide-tip-grid ${selectedTip.isMissing ? 'is-missing' : ''}`}
                    role="tablist"
                    aria-label="식재료 가이드 종류"
                    style={{ gridTemplateColumns: `repeat(${visibleGuideTips.length}, minmax(0, 1fr))` }}
                  >
                    {visibleGuideTips.map((tip) => (
                      <button
                        type="button"
                        className={`guide-tip-card ${tip.isMissing ? 'is-missing' : ''} ${
                          selectedTip.title === tip.title ? 'is-active' : ''
                        }`}
                        key={tip.title}
                        role="tab"
                        aria-selected={selectedTip.title === tip.title}
                        onClick={() => setSelectedTipTitle(tip.title)}
                      >
                        <div className="guide-tip-card__title">
                          <span aria-hidden="true" />
                          <h3>{tip.title}</h3>
                        </div>
                      </button>
                    ))}
                  </div>
                  <div className={`guide-tip-body ${selectedTip.isMissing ? 'is-missing' : ''}`}>
                    <div className="guide-tip-copy-stack">
                      {visibleGuideTips.map((tip) => {
                        const isActive = selectedTip.title === tip.title
                        const suggestionTitleId = `guide-suggestion-title-${tip.guideType}`
                        const isSuggestionAccepted =
                          isActive && suggestionMessage === '제보가 접수되었습니다. 검토 후 가이드에 반영됩니다.'
                        const shouldShowPoints = !(tip.isMissing && isActive)

                        return (
                          <div
                            aria-hidden={!isActive}
                            className={`guide-tip-copy ${isActive ? 'is-active' : ''}`}
                            key={tip.title}
                          >
                            {shouldShowPoints ? (
                              <ul>
                                {tip.points.map((point) => (
                                  <li key={point}>{point}</li>
                                ))}
                              </ul>
                            ) : null}

                            {!tip.isMissing ? (
                              <div className="guide-tip-source">
                                {tip.sourceUrl ? (
                                  <a href={tip.sourceUrl} target="_blank" rel="noreferrer">
                                    {tip.source}
                                  </a>
                                ) : (
                                  <span>{tip.source}</span>
                                )}
                              </div>
                            ) : (
                              <section
                                className={`guide-suggestion ${isSuggestionAccepted ? 'is-complete' : ''} ${
                                  isActive && isSuggestionFormOpen ? 'is-form-open' : ''
                                }`}
                                aria-labelledby={suggestionTitleId}
                              >
                                {isSuggestionAccepted ? (
                                  <div className="guide-suggestion__complete" role="status">
                                    <strong>제보가 접수되었습니다.</strong>
                                    <span>검토 후 가이드에 반영됩니다.</span>
                                  </div>
                                ) : (
                                  <div className="guide-suggestion__panel">
                                    <div className="guide-suggestion__intro">
                                      <h3 id={suggestionTitleId}>나만의 가이드 제보</h3>
                                      <p>직접 알고 있는 방법이나 참고한 링크를 남겨주세요. 확인 후 서비스에 반영될 수 있어요.</p>
                                    </div>

                                    {isActive && isSuggestionFormOpen ? (
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
                                        </div>
                                      </form>
                                    ) : (
                                      <button className="guide-suggestion__open" type="button" onClick={openSuggestionForm}>
                                        {isLoggedIn ? '가이드 제보하기' : '로그인 후 제보하기'}
                                      </button>
                                    )}

                                    {isActive && suggestionMessage ? (
                                      <p className="guide-suggestion__message" role="status">{suggestionMessage}</p>
                                    ) : null}
                                  </div>
                                )}
                              </section>
                            )}
                          </div>
                        )
                      })}
                    </div>
                  </div>

                </aside>
              </div>

              <div className="guide-detail-secondary">
                <section className="guide-detail-recipes" aria-labelledby="guide-recipes-title">
                  <div className="guide-recipes__header">
                    <h2 id="guide-recipes-title">추천 레시피</h2>
                    {recommendedRecipes.length ? (
                      <div className="guide-recipe-pager" aria-label="추천 레시피 페이지">
                        <span>{recipeSlideIndex + 1}/{recommendedRecipes.length}</span>
                      </div>
                    ) : null}
                  </div>

                  {isRecipeLoading ? (
                    <p className="guide-recipe-status">추천 레시피를 불러오는 중입니다.</p>
                  ) : recipeErrorMessage ? (
                    <p className="guide-recipe-status guide-recipe-status--error">{recipeErrorMessage}</p>
                  ) : recommendedRecipes.length ? (
                    <>
                      <div
                        className="guide-recipe-list"
                        aria-label={`${selectedGuide.name} 추천 레시피`}
                        aria-live="polite"
                        onPointerDown={handleRecipeDragStart}
                        onPointerMove={handleRecipeDragMove}
                        onPointerUp={handleRecipeDragEnd}
                        onPointerCancel={(event) => {
                          recipeDragStartY.current = null
                          recipeDidDrag.current = false
                          resetRecipeDragVisual(event.currentTarget)
                        }}
                      >
                        <Link
                          className={`guide-recipe-card is-${recipeSlideDirection}`}
                          key={currentRecommendedRecipe.recipe_id}
                          to={`/recipes/${currentRecommendedRecipe.recipe_id}`}
                          onClick={(event) => {
                            if (recipeDidDrag.current) event.preventDefault()
                          }}
                        >
                          <ImageSlot alt="" className="guide-recipe-card__image" src={currentRecommendedRecipe.main_image_url} />
                          <div>
                            <span>{currentRecommendedRecipe.category || '추천 메뉴'}</span>
                            <h3>{currentRecommendedRecipe.title}</h3>
                            <p>
                              {formatCookingTime(currentRecommendedRecipe.cooking_time_min)} · {currentRecommendedRecipe.difficulty || '난이도 정보 없음'}
                            </p>
                          </div>
                        </Link>
                      </div>
                    </>
                  ) : (
                    <article className="guide-recipe-more">
                      <ImageSlot alt="" className="guide-recipe-more__icon" src={iconBasket} />
                      <strong>{selectedGuide.name}로 바로 보여줄 추천 레시피가 아직 없습니다.</strong>
                    </article>
                  )}
                </section>

                <div className="guide-detail-nutrition-column">
                  <h2 className="guide-detail-section-title" id="guide-nutrition-title">영양성분</h2>
                  <section className="guide-detail-nutrition" aria-labelledby="guide-nutrition-title">
                    <div className="guide-detail-nutrition__header">
                      <div>
                        <small>기준량 {selectedGuide.nutrition_base_amount || '정보 없음'}</small>
                        <strong>{selectedGuide.energy_kcal ?? '-'} kcal</strong>
                      </div>
                      {selectedGuide.nutrition_source_name ? (
                        <span className="guide-detail-nutrition__source">출처: {selectedGuide.nutrition_source_name}</span>
                      ) : null}
                    </div>

                    <div className="guide-nutrition-grid">
                      <strong><span>탄수화물</span><b>{selectedGuide.carbohydrate_g ?? '-'} g</b></strong>
                      <strong><span>단백질</span><b>{selectedGuide.protein_g ?? '-'} g</b></strong>
                      <strong><span>지방</span><b>{selectedGuide.fat_g ?? '-'} g</b></strong>
                      <strong><span>포화지방</span><b>{selectedGuide.saturated_fat_g ?? '-'} g</b></strong>
                      <strong><span>트랜스지방</span><b>{selectedGuide.trans_fat_g ?? '-'} g</b></strong>
                      <strong><span>당류</span><b>{selectedGuide.sugar_g ?? '-'} g</b></strong>
                      <strong><span>식이섬유</span><b>{selectedGuide.fiber_g ?? '-'} g</b></strong>
                      <strong><span>나트륨</span><b>{selectedGuide.sodium_mg ?? '-'} mg</b></strong>
                      <strong><span>칼륨</span><b>{selectedGuide.potassium_mg ?? '-'} mg</b></strong>
                      <strong><span>수분</span><b>{selectedGuide.water_g ?? '-'} g</b></strong>
                    </div>
                  </section>
                </div>
              </div>
            </>
          ) : (
            <section className="guide-panel guide-detail guide-empty">선택한 식재료를 찾을 수 없습니다.</section>
          )}
        </>
      )}

      {isLoggedIn && !isDetailPage ? (
        <section className="guide-ingredients guide-ingredients--seasonal" aria-labelledby="guide-seasonal-title">
          <div className="guide-ingredients__header">
            <div className="guide-section-title" id="guide-seasonal-title">
              {currentMonth}월 제철 식재료
            </div>
            <div className="guide-ingredients__actions">
              {seasonalMonthControl}
            </div>
          </div>
          <div className="guide-fridge-pager">
            {seasonalTotalPages > 1 ? (
              <button
                className="guide-fridge-page-button is-previous"
                type="button"
                aria-label="이전 제철 식재료 페이지"
                disabled={guestRecommendationPage <= 1}
                onClick={() => setGuestRecommendationPage((current) => Math.max(1, current - 1))}
              >
                ‹
              </button>
            ) : null}
            <div className="guide-ingredient-list" aria-label="제철 식재료 목록">
              {seasonalFeaturedIngredients.map((ingredient) => renderIngredientButton(ingredient))}
              {!isListLoading && seasonalFeaturedIngredients.length === 0 ? (
                <p className="guide-empty">{currentMonth}월 제철 식재료가 없습니다.</p>
              ) : null}
            </div>
            {seasonalTotalPages > 1 ? (
              <button
                className="guide-fridge-page-button is-next"
                type="button"
                aria-label="다음 제철 식재료 페이지"
                disabled={guestRecommendationPage >= seasonalTotalPages}
                onClick={() => setGuestRecommendationPage((current) => Math.min(seasonalTotalPages, current + 1))}
              >
                ›
              </button>
            ) : null}
          </div>
        </section>
      ) : null}
    </section>
  )
}

export default Guide
