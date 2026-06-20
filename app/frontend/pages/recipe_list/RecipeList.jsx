import React, { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import './RecipeList.css'

import imageRecommendation from '../../assets/extracted/images/image_recommendation.png'
import imageSearch from '../../assets/extracted/images/image_search.png'
import { recipeQuickMenus, recipes } from '../../mock/recipeListMock.js'

function ImageSlot({ src, alt = '', className = '' }) {
  return (
    <span className={`recipe-list-image-slot ${src ? 'is-filled' : ''} ${className}`}>
      {src ? <img src={src} alt={alt} /> : null}
    </span>
  )
}

function GridIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 20 20" focusable="false">
      <rect x="3" y="3" width="5" height="5" rx="1.2" />
      <rect x="12" y="3" width="5" height="5" rx="1.2" />
      <rect x="3" y="12" width="5" height="5" rx="1.2" />
      <rect x="12" y="12" width="5" height="5" rx="1.2" />
    </svg>
  )
}

function ListIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 20 20" focusable="false">
      <rect x="3" y="4" width="3" height="3" rx="0.8" />
      <rect x="8" y="4.5" width="9" height="2" rx="1" />
      <rect x="3" y="8.5" width="3" height="3" rx="0.8" />
      <rect x="8" y="9" width="9" height="2" rx="1" />
      <rect x="3" y="13" width="3" height="3" rx="0.8" />
      <rect x="8" y="13.5" width="9" height="2" rx="1" />
    </svg>
  )
}

function RecipeList() {
  const location = useLocation()
  const navigate = useNavigate()
  const [searchTerm, setSearchTerm] = useState(
    () => new URLSearchParams(location.search).get('query') ?? '',
  )
  const [category, setCategory] = useState('전체')
  const [timeFilter, setTimeFilter] = useState('전체')
  const [levelFilter, setLevelFilter] = useState('전체')
  const [sortBy, setSortBy] = useState('인기순')
  const [viewMode, setViewMode] = useState('grid')
  const [visibleCount, setVisibleCount] = useState(5)
  const [savedIds, setSavedIds] = useState([])
  const [showSavedOnly, setShowSavedOnly] = useState(false)

  useEffect(() => {
    setSearchTerm(new URLSearchParams(location.search).get('query') ?? '')
  }, [location.search])

  const filteredRecipes = useMemo(() => {
    const normalizedQuery = searchTerm.trim().toLowerCase()

    const result = recipes.filter((recipe) => {
      const matchesQuery =
        !normalizedQuery ||
        recipe.title.toLowerCase().includes(normalizedQuery) ||
        recipe.tags.some((tag) => tag.toLowerCase().includes(normalizedQuery))
      const matchesCategory = category === '전체' || recipe.category === category
      const minutes = Number.parseInt(recipe.time, 10)
      const matchesTime =
        timeFilter === '전체' ||
        (timeFilter === '15분 이하' && minutes <= 15) ||
        (timeFilter === '20분 이하' && minutes <= 20) ||
        (timeFilter === '30분 이하' && minutes <= 30)
      const matchesLevel = levelFilter === '전체' || recipe.level === levelFilter
      const matchesSaved = !showSavedOnly || savedIds.includes(recipe.id)

      return matchesQuery && matchesCategory && matchesTime && matchesLevel && matchesSaved
    })

    if (sortBy === '조리시간순') {
      return [...result].sort((a, b) => Number.parseInt(a.time, 10) - Number.parseInt(b.time, 10))
    }

    if (sortBy === '난이도순') {
      return [...result].sort((a, b) => a.level.localeCompare(b.level, 'ko'))
    }

    return result
  }, [category, levelFilter, savedIds, searchTerm, showSavedOnly, sortBy, timeFilter])

  const visibleRecipes = filteredRecipes.slice(0, visibleCount)
  const hasActiveFilter =
    Boolean(searchTerm.trim()) ||
    category !== '전체' ||
    timeFilter !== '전체' ||
    levelFilter !== '전체' ||
    showSavedOnly

  const submitSearch = (event) => {
    event.preventDefault()
    setVisibleCount(5)
  }

  const handleQuickMenu = (title) => {
    setShowSavedOnly(false)
    setCategory('전체')
    setLevelFilter('전체')
    setTimeFilter('전체')
    setVisibleCount(5)

    if (title === '인기 레시피') {
      setSortBy('인기순')
      setSearchTerm('')
      return
    }

    if (title === '간단 레시피') {
      setTimeFilter('15분 이하')
      setLevelFilter('쉬움')
      setSearchTerm('')
      return
    }

    if (title === '요리 입문') {
      setLevelFilter('쉬움')
      setSearchTerm('')
      return
    }

    if (title === '저장한 레시피') {
      setShowSavedOnly(true)
      setSearchTerm('')
    }
  }

  const toggleSaved = (recipeId) => {
    setSavedIds((prev) =>
      prev.includes(recipeId) ? prev.filter((id) => id !== recipeId) : [...prev, recipeId],
    )
  }

  const resetFilters = () => {
    setSearchTerm('')
    setCategory('전체')
    setTimeFilter('전체')
    setLevelFilter('전체')
    setShowSavedOnly(false)
    setSortBy('인기순')
    setVisibleCount(5)
  }

  return (
    <section className="recipe-list-page" aria-labelledby="recipe-list-title">
      <div className="recipe-list-hero">
        <div className="recipe-list-hero__copy">
          <h1 id="recipe-list-title">
            다양한 레시피를
            <strong>한곳에서 만나보세요</strong>
          </h1>
          <p>국, 볶음, 반찬, 파스타까지 오늘 끌리는 메뉴를 자유롭게 둘러보세요.</p>
          <form className="recipe-list-search" aria-label="레시피 검색" onSubmit={submitSearch}>
            <span aria-hidden="true" />
            <input
              type="search"
              placeholder="레시피명, 재료명을 검색해보세요"
              value={searchTerm}
              onChange={(event) => {
                setSearchTerm(event.target.value)
                setVisibleCount(5)
              }}
            />
            <button type="submit">검색</button>
          </form>
        </div>

        <ImageSlot className="recipe-list-hero__image" src={imageSearch} />
      </div>

      <div className="recipe-list-quick" aria-label="레시피 바로가기">
        {recipeQuickMenus.map((menu) => (
          <button
            className="recipe-list-quick-card"
            type="button"
            key={menu.title}
            onClick={() => handleQuickMenu(menu.title)}
          >
            <ImageSlot className={`recipe-list-quick-card__icon is-${menu.mark || 'image'}`} src={menu.image} />
            <span>
              <strong>{menu.title}</strong>
              <small>{menu.description}</small>
            </span>
          </button>
        ))}
      </div>

      <section className="recipe-list-filter" aria-labelledby="recipe-filter-title">
        <h2 id="recipe-filter-title">레시피 필터</h2>
        <div className="recipe-list-filter__controls">
          <select
            aria-label="카테고리"
            value={category}
            onChange={(event) => {
              setCategory(event.target.value)
              setVisibleCount(5)
            }}
          >
            <option value="전체">카테고리 전체</option>
            <option value="국/찌개">국/찌개</option>
            <option value="볶음">볶음</option>
            <option value="반찬">반찬</option>
            <option value="파스타">파스타</option>
          </select>
          <select
            aria-label="조리시간"
            value={timeFilter}
            onChange={(event) => {
              setTimeFilter(event.target.value)
              setVisibleCount(5)
            }}
          >
            <option value="전체">조리시간 전체</option>
            <option value="15분 이하">15분 이하</option>
            <option value="20분 이하">20분 이하</option>
            <option value="30분 이하">30분 이하</option>
          </select>
          <select
            aria-label="난이도"
            value={levelFilter}
            onChange={(event) => {
              setLevelFilter(event.target.value)
              setVisibleCount(5)
            }}
          >
            <option value="전체">난이도 전체</option>
            <option value="쉬움">쉬움</option>
            <option value="보통">보통</option>
          </select>
          <div className="recipe-list-filter__right">
            <select
              aria-label="정렬"
              value={sortBy}
              onChange={(event) => {
                setSortBy(event.target.value)
                setVisibleCount(5)
              }}
            >
              <option value="인기순">인기순</option>
              <option value="조리시간순">조리시간순</option>
              <option value="난이도순">난이도순</option>
            </select>
            <div className="recipe-list-view" aria-label="보기 방식">
              <button
                className={viewMode === 'grid' ? 'is-active' : ''}
                type="button"
                aria-label="그리드 보기"
                title="그리드 보기"
                onClick={() => setViewMode('grid')}
              >
                <GridIcon />
              </button>
              <button
                className={viewMode === 'list' ? 'is-active' : ''}
                type="button"
                aria-label="리스트 보기"
                title="리스트 보기"
                onClick={() => setViewMode('list')}
              >
                <ListIcon />
              </button>
            </div>
          </div>
        </div>
      </section>

      <section className="recipe-list-results" aria-labelledby="recipe-results-title">
        <h2 id="recipe-results-title">
          {showSavedOnly ? '저장한 레시피' : '전체 레시피'} <span>({filteredRecipes.length})</span>
          {hasActiveFilter ? (
            <button className="recipe-list-reset" type="button" onClick={resetFilters}>
              필터 초기화
            </button>
          ) : null}
        </h2>
        <div className={viewMode === 'list' ? 'recipe-list-grid is-list' : 'recipe-list-grid'}>
          {visibleRecipes.map((recipe) => (
            <article
              className="recipe-card"
              key={recipe.title}
              role="button"
              tabIndex={0}
              onClick={() => navigate(`/recipes/${recipe.id}`)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault()
                  navigate(`/recipes/${recipe.id}`)
                }
              }}
            >
              <div className="recipe-card__media">
                {recipe.badge ? <span className="recipe-card__badge">{recipe.badge}</span> : null}
                <button
                  type="button"
                  aria-label={`${recipe.title} 저장`}
                  aria-pressed={savedIds.includes(recipe.id)}
                  onClick={(event) => {
                    event.stopPropagation()
                    toggleSaved(recipe.id)
                  }}
                >
                  {savedIds.includes(recipe.id) ? '♥' : '♡'}
                </button>
                <ImageSlot className="recipe-card__image" src={recipe.image} />
              </div>
              <div className="recipe-card__body">
                <h3>{recipe.title}</h3>
                <p>{recipe.time} · {recipe.level}</p>
                <div>
                  {recipe.tags.map((tag) => (
                    <span key={tag}>{tag}</span>
                  ))}
                </div>
              </div>
            </article>
          ))}
          {visibleRecipes.length === 0 ? (
            <article className="recipe-card recipe-card--empty">
              <div className="recipe-card__body">
                <h3>조건에 맞는 레시피가 없어요.</h3>
                <p>검색어를 바꾸거나 필터를 초기화해보세요.</p>
              </div>
            </article>
          ) : null}
        </div>

        <button
          className="recipe-list-more"
          type="button"
          disabled={visibleCount >= filteredRecipes.length}
          onClick={() => {
            setVisibleCount((prev) => prev + 5)
          }}
        >
          {visibleCount >= filteredRecipes.length ? '모든 레시피를 보고 있어요' : '더 많은 레시피 보기'}
        </button>
      </section>

      <ImageSlot className="recipe-list-mobile-art" src={imageRecommendation} />
    </section>
  )
}

export default RecipeList
