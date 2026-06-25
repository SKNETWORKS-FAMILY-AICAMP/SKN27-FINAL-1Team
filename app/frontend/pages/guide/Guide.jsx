import React, { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import './Guide.css'

import iconBasket from '../../assets/extracted/icons/icon_basket.png'
import imageGuide from '../../assets/extracted/images/image_guide.png'

const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const TIP_DEFINITIONS = [
  { title: '보관방법', key: 'storage_tips', sourceName: 'storage_source_name', sourceUrl: 'storage_source_url' },
  { title: '손질방법', key: 'prep_tips', sourceName: 'prep_source_name', sourceUrl: 'prep_source_url' },
  { title: '세척방법', key: 'washing_tips', sourceName: 'washing_source_name', sourceUrl: 'washing_source_url' },
  { title: '신선도 확인법', key: 'freshness_tips', sourceName: 'freshness_source_name', sourceUrl: 'freshness_source_url' },
  { title: '섭취방법', key: 'intake_tips', sourceName: 'nutrition_source_name', sourceUrl: null },
]

function getAuthHeaders() {
  const token = window.localStorage.getItem('bobbeori-token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

function splitTipText(text) {
  if (!text) return ['등록된 정보가 없습니다.']
  return String(text)
    .split(/\n{2,}|\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .slice(0, 4)
}

function buildGuideTips(guide) {
  return TIP_DEFINITIONS.map((definition) => {
    const points = splitTipText(guide?.[definition.key])
    const source = definition.sourceName ? guide?.[definition.sourceName] : null
    const sourceUrl = definition.sourceUrl ? guide?.[definition.sourceUrl] : null
    return {
      ...definition,
      points,
      chip: source || '가이드 정보',
      source: source || '출처 정보 없음',
      sourceUrl,
      hasContent: Boolean(guide?.[definition.key]),
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
  const [guideItems, setGuideItems] = useState([])
  const [totalCount, setTotalCount] = useState(0)
  const [selectedGuide, setSelectedGuide] = useState(null)
  const [isListLoading, setIsListLoading] = useState(true)
  const [isDetailLoading, setIsDetailLoading] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    const timer = window.setTimeout(async () => {
      setIsListLoading(true)
      setErrorMessage('')
      try {
        const params = new URLSearchParams({ limit: '60' })
        if (searchTerm.trim()) params.set('keyword', searchTerm.trim())
        const response = await fetch(`${apiUrl}/api/v1/guide?${params}`, {
          headers: getAuthHeaders(),
          signal: controller.signal,
        })
        if (!response.ok) throw new Error('식재료 가이드를 불러오지 못했습니다.')
        const data = await response.json()
        setGuideItems(data.items || [])
        setTotalCount(data.total || 0)
      } catch (error) {
        if (error.name !== 'AbortError') {
          setErrorMessage(error.message)
          setGuideItems([])
          setTotalCount(0)
        }
      } finally {
        if (!controller.signal.aborted) setIsListLoading(false)
      }
    }, 180)

    return () => {
      controller.abort()
      window.clearTimeout(timer)
    }
  }, [searchTerm])

  useEffect(() => {
    if (!selectedCode) {
      setSelectedGuide(null)
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

  const fridgeIngredients = guideItems.slice(0, 6)
  const guideTips = useMemo(() => buildGuideTips(selectedGuide), [selectedGuide])
  const selectedTip = guideTips.find((tip) => tip.title === selectedTipTitle) ?? guideTips[0]

  useEffect(() => {
    if (!guideTips.some((tip) => tip.title === selectedTipTitle)) {
      setSelectedTipTitle(guideTips[0].title)
    }
  }, [guideTips, selectedTipTitle])

  const selectIngredient = (ingredient) => {
    navigate(`/guide/${encodeURIComponent(ingredient.code)}`)
  }

  const openRecipes = () => {
    const query = selectedGuide?.raw_name || selectedGuide?.representative_name || selectedGuide?.name || ''
    navigate(`/recipes?query=${encodeURIComponent(query)}`)
  }

  return (
    <section className="guide-page" aria-labelledby="guide-title">
      <div className="guide-hero">
        <div className="guide-hero__copy">
          <h1 id="guide-title">식재료 가이드</h1>
          <p>재료별 보관, 손질, 세척, 신선도 팁을 한눈에 확인해요!</p>
        </div>

        <label className="guide-search guide-hero__search" aria-label="식재료명 검색">
          <span aria-hidden="true" />
          <input
            placeholder="식재료명을 검색해보세요"
            type="search"
            value={searchTerm}
            onChange={(event) => setSearchTerm(event.target.value)}
          />
        </label>

        <div className="guide-hero__art" aria-hidden="true">
          <img src={imageGuide} alt="" />
        </div>
      </div>

      {errorMessage ? <p className="guide-error">{errorMessage}</p> : null}

      <section className="guide-panel guide-ingredients" aria-labelledby="guide-ingredients-title">
        <div className="guide-section-title" id="guide-ingredients-title">
          추천 식재료
        </div>
        <div className="guide-ingredient-list" aria-label="추천 식재료 목록">
          {fridgeIngredients.map((ingredient) => (
            <button
              className={`guide-ingredient ${
                isDetailPage && selectedGuide?.code === ingredient.code ? 'is-active' : ''
              }`}
              key={ingredient.code}
              type="button"
              onClick={() => selectIngredient(ingredient)}
            >
              <ImageSlot alt="" className="guide-ingredient__image" label={ingredient.name} />
              <span>{ingredient.name}</span>
            </button>
          ))}
          {!isListLoading && fridgeIngredients.length === 0 ? (
            <p className="guide-empty">검색 결과가 없습니다.</p>
          ) : null}
        </div>
      </section>

      {!isDetailPage ? (
        <section className="guide-panel guide-all" aria-labelledby="guide-all-title">
          <div className="guide-all__header">
            <div>
              <h2 id="guide-all-title">전체 재료 목록</h2>
              <p>궁금한 재료를 선택하면 보관, 손질, 세척 정보를 자세히 볼 수 있어요.</p>
            </div>
            <span>{isListLoading ? '불러오는 중' : `${totalCount}개`}</span>
          </div>

          <div className="guide-all-list" aria-label="전체 재료 목록">
            {guideItems.map((ingredient) => (
              <button
                className="guide-all-item"
                key={ingredient.code}
                type="button"
                onClick={() => selectIngredient(ingredient)}
              >
                <ImageSlot alt="" className="guide-all-item__image" label={ingredient.name} />
                <div>
                  <strong>{ingredient.name}</strong>
                  <p>{formatCategory(ingredient) || '분류 정보 없음'}</p>
                  <small>{formatMonths(ingredient.seasonal_months)}</small>
                </div>
                <span aria-hidden="true" />
              </button>
            ))}
          </div>
        </section>
      ) : (
        <>
          <button className="guide-list-back" type="button" onClick={() => navigate('/guide')}>
            전체 목록
          </button>

          {isDetailLoading ? (
            <section className="guide-panel guide-detail guide-loading">가이드를 불러오는 중입니다.</section>
          ) : selectedGuide ? (
            <>
              <div className="guide-content-grid">
                <article className="guide-panel guide-detail">
                  <div className="guide-detail__header">
                    <ImageSlot alt="" className="guide-detail__image" label={selectedGuide.name} />
                    <div>
                      <h2>{selectedGuide.name}</h2>
                      <p>{formatCategory(selectedGuide) || '분류 정보 없음'}</p>
                      <span className="guide-owned-badge">{formatMonths(selectedGuide.seasonal_months)}</span>
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
                        <strong>{tip.hasContent ? '정보 있음' : '정보 없음'}</strong>
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
                  <strong>{selectedTip.chip}</strong>
                  {selectedTip.sourceUrl ? (
                    <p>
                      출처:{' '}
                      <a href={selectedTip.sourceUrl} target="_blank" rel="noreferrer">
                        {selectedTip.source}
                      </a>
                    </p>
                  ) : (
                    <p>출처: {selectedTip.source}</p>
                  )}
                </aside>
              </div>

              <section className="guide-panel guide-recipes" aria-labelledby="guide-recipes-title">
                <div className="guide-recipes__header">
                  <h2 id="guide-recipes-title">영양 정보</h2>
                  <span>{selectedGuide.nutrition_base_amount || '기준량 정보 없음'}</span>
                </div>

                <div className="guide-nutrition-grid">
                  <strong>에너지 {selectedGuide.energy_kcal ?? '-'} kcal</strong>
                  <strong>단백질 {selectedGuide.protein_g ?? '-'} g</strong>
                  <strong>지방 {selectedGuide.fat_g ?? '-'} g</strong>
                  <strong>탄수화물 {selectedGuide.carbohydrate_g ?? '-'} g</strong>
                  <strong>칼륨 {selectedGuide.potassium_mg ?? '-'} mg</strong>
                  <strong>나트륨 {selectedGuide.sodium_mg ?? '-'} mg</strong>
                </div>

                <article className="guide-recipe-more">
                  <ImageSlot alt="" className="guide-recipe-more__icon" src={iconBasket} />
                  <strong>{selectedGuide.name}로 만들 수 있는 레시피를 찾아보세요.</strong>
                  <button className="guide-primary-button" type="button" onClick={openRecipes}>
                    레시피 보기
                  </button>
                </article>
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
