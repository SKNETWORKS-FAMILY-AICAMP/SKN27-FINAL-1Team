import React, { useEffect, useMemo, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import './RecipeList.css'

import iconRefrigerator from '../../assets/extracted/icons/icon_refrigerator.png'
import imageEatRefrigerator from '../../assets/extracted/images/image_eat_refrigerator.png'
import imagePutting from '../../assets/extracted/images/image_putting.png'
import imageRecommendation from '../../assets/extracted/images/image_recommendation.png'
import imageSearch from '../../assets/extracted/images/image_search.png'
import { serviceBadges, userProfile } from '../../data/userService.js'

const quickMenus = [
  { title: '인기 레시피', description: '요즘 많이 찾는 레시피', mark: 'hot' },
  { title: '간단 레시피', description: '쉽고 빠르게 만들어요', mark: 'easy' },
  { title: '저장한 레시피', description: '내가 저장한 레시피', mark: 'save' },
  { title: '재료로 찾기', description: '냉장고 재료로 검색', image: iconRefrigerator },
]

const recipes = [
  {
    id: 'green-onion-tofu-egg-stew',
    title: '대파 두부 계란찌개',
    category: '국/찌개',
    time: '20분',
    level: '쉬움',
    tags: ['대파', '두부', '계란', '양파'],
    badge: '인기',
    image: imageEatRefrigerator,
  },
  {
    id: 'mushroom-perilla-soup',
    title: '버섯 들깨탕',
    category: '국/찌개',
    time: '25분',
    level: '보통',
    tags: ['버섯', '두부', '들깨'],
    badge: '간단',
  },
  {
    id: 'kimchi-fried-rice',
    title: '김치 볶음밥',
    category: '볶음',
    time: '15분',
    level: '쉬움',
    tags: ['김치', '밥', '대파', '계란'],
  },
  {
    id: 'tofu-soy-braise',
    title: '두부 간장조림',
    category: '반찬',
    time: '20분',
    level: '쉬움',
    tags: ['두부', '간장', '대파'],
  },
  {
    id: 'rolled-egg',
    title: '계란말이',
    category: '반찬',
    time: '10분',
    level: '쉬움',
    tags: ['계란', '대파', '소금'],
  },
  {
    id: 'tomato-pasta',
    title: '토마토 파스타',
    category: '파스타',
    time: '15분',
    level: '쉬움',
    tags: ['토마토', '양파', '파스타면'],
  },
  {
    id: 'pork-soy-stir-fry',
    title: '돼지고기 간장볶음',
    category: '볶음',
    time: '18분',
    level: '쉬움',
    tags: ['돼지고기', '양파', '간장'],
  },
  {
    id: 'green-onion-pasta',
    title: '대파 파스타',
    category: '파스타',
    time: '25분',
    level: '보통',
    tags: ['대파', '마늘', '파스타면'],
  },
]

function ImageSlot({ src, alt = '', className = '' }) {
  return (
    <span className={`recipe-list-image-slot ${src ? 'is-filled' : ''} ${className}`}>
      {src ? <img src={src} alt={alt} /> : null}
    </span>
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
  const [fridgeOnly, setFridgeOnly] = useState(false)
  const [sortBy, setSortBy] = useState('인기순')
  const [viewMode, setViewMode] = useState('grid')
  const [visibleCount, setVisibleCount] = useState(5)
  const [savedIds, setSavedIds] = useState([])
  const [showSavedOnly, setShowSavedOnly] = useState(false)
  const [selectedRecipeId, setSelectedRecipeId] = useState('green-onion-tofu-egg-stew')
  const [progressStep, setProgressStep] = useState(1)

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
      const matchesFridge = !fridgeOnly || recipe.tags.some((tag) => ['대파', '두부', '계란', '양파', '김치', '버섯'].includes(tag))

      return matchesQuery && matchesCategory && matchesTime && matchesLevel && matchesSaved && matchesFridge
    })

    if (sortBy === '조리시간순') {
      return [...result].sort((a, b) => Number.parseInt(a.time, 10) - Number.parseInt(b.time, 10))
    }

    if (sortBy === '난이도순') {
      return [...result].sort((a, b) => a.level.localeCompare(b.level, 'ko'))
    }

    return result
  }, [category, fridgeOnly, levelFilter, savedIds, searchTerm, showSavedOnly, sortBy, timeFilter])

  const visibleRecipes = filteredRecipes.slice(0, visibleCount)
  const selectedRecipe =
    recipes.find((recipe) => recipe.id === selectedRecipeId) ?? filteredRecipes[0] ?? recipes[0]
  const hasActiveFilter =
    Boolean(searchTerm.trim()) ||
    category !== '전체' ||
    timeFilter !== '전체' ||
    levelFilter !== '전체' ||
    fridgeOnly ||
    showSavedOnly
  const progressPercent = Math.round((progressStep / 4) * 100)
  const progressCopy = [
    '먹고 싶은 조건을 검색하거나 빠른 메뉴를 골라주세요.',
    `${filteredRecipes.length}개 후보를 찾았어요. 마음에 드는 레시피를 선택해보세요.`,
    `${selectedRecipe.title}을 선택했어요. 상세를 보거나 부족 재료를 장보기로 넘길 수 있어요.`,
    '레시피 선택이 끝났어요. 상세 확인 후 바로 요리하거나 장보기로 이어가세요.',
  ]

  const submitSearch = (event) => {
    event.preventDefault()
    setVisibleCount(5)
    setProgressStep(2)
  }

  const handleQuickMenu = (title) => {
    setShowSavedOnly(false)
    setCategory('전체')
    setLevelFilter('전체')
    setTimeFilter('전체')
    setVisibleCount(5)
    setProgressStep(2)

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

    if (title === '저장한 레시피') {
      setShowSavedOnly(true)
      setSearchTerm('')
      setProgressStep(2)
      return
    }

    navigate('/recipe-fridge')
  }

  const toggleSaved = (recipeId) => {
    setSavedIds((prev) =>
      prev.includes(recipeId) ? prev.filter((id) => id !== recipeId) : [...prev, recipeId],
    )
    setProgressStep((prev) => Math.max(prev, 3))
  }

  const selectRecipe = (recipeId) => {
    setSelectedRecipeId(recipeId)
    setProgressStep(3)
  }

  const resetFilters = () => {
    setSearchTerm('')
    setCategory('전체')
    setTimeFilter('전체')
    setLevelFilter('전체')
    setFridgeOnly(false)
    setShowSavedOnly(false)
    setSortBy('인기순')
    setVisibleCount(5)
    setProgressStep(1)
  }

  return (
    <section className="recipe-list-page" aria-labelledby="recipe-list-title">
      <div className="recipe-list-hero">
        <div className="recipe-list-hero__copy">
          <h1 id="recipe-list-title">
            냉장고 속 재료로
            <strong>맛있는 한 끼 레시피</strong>
          </h1>
          <p>냉장고 재료로 만들 수 있는 다양한 레시피를 검색하고 확인해 보세요.</p>
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

        <aside className="recipe-list-featured" aria-label="오늘의 추천 레시피">
          <div>
            <h2>오늘의 추천 레시피</h2>
            <article>
              <ImageSlot className="recipe-list-featured__image" src={imageEatRefrigerator} />
              <div>
                <strong>대파 두부 계란찌개</strong>
                <p>냉장고 속 재료로 쉽고 맛있게!</p>
                <Link className="recipe-list-featured__button" to="/recipes/green-onion-tofu-egg-stew">
                  레시피 보기
                </Link>
              </div>
            </article>
          </div>
        </aside>
      </div>

      <section className="recipe-list-progress" aria-labelledby="recipe-progress-title">
        <div>
          <span>{progressPercent}% 진행</span>
          <h2 id="recipe-progress-title">{userProfile.mealTarget} 레시피 고르기</h2>
          <p>{progressCopy[progressStep - 1]}</p>
          <div className="recipe-list-progress__badges" aria-label="추천 기준">
            {serviceBadges.map((badge) => (
              <em key={badge}>{badge}</em>
            ))}
          </div>
        </div>
        <div className="recipe-list-progress__bar" aria-label={`진행률 ${progressPercent}%`}>
          <span style={{ width: `${progressPercent}%` }} />
        </div>
        <div className="recipe-list-progress__actions">
          <button type="button" onClick={() => selectRecipe(visibleRecipes[0]?.id ?? selectedRecipe.id)}>
            첫 번째 후보 선택
          </button>
          <button type="button" onClick={() => navigate(`/recipes/${selectedRecipe.id}`)}>
            상세 보기
          </button>
          <button type="button" onClick={() => navigate('/shopping-list')}>
            장보기 연결
          </button>
        </div>
      </section>

      <div className="recipe-list-quick" aria-label="레시피 바로가기">
        {quickMenus.map((menu) => (
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
              setProgressStep(2)
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
              setProgressStep(2)
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
              setProgressStep(2)
            }}
          >
            <option value="전체">난이도 전체</option>
            <option value="쉬움">쉬움</option>
            <option value="보통">보통</option>
          </select>
          <label>
            <input
              type="checkbox"
              checked={fridgeOnly}
              onChange={(event) => {
                setFridgeOnly(event.target.checked)
                setVisibleCount(5)
                setProgressStep(2)
              }}
            />
            냉장고 재료로만 보기
          </label>
          <select
            aria-label="정렬"
            value={sortBy}
            onChange={(event) => {
              setSortBy(event.target.value)
              setVisibleCount(5)
              setProgressStep(2)
            }}
          >
            <option value="인기순">인기순</option>
            <option value="조리시간순">조리시간순</option>
            <option value="난이도순">난이도순</option>
          </select>
          <div className="recipe-list-view">
            <button
              className={viewMode === 'grid' ? 'is-active' : ''}
              type="button"
              aria-label="그리드 보기"
              onClick={() => setViewMode('grid')}
            >
              <span />
            </button>
            <button
              className={viewMode === 'list' ? 'is-active' : ''}
              type="button"
              aria-label="리스트 보기"
              onClick={() => setViewMode('list')}
            >
              <span />
            </button>
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
              className={`recipe-card ${selectedRecipe.id === recipe.id ? 'is-selected' : ''}`}
              key={recipe.title}
            >
              <div className="recipe-card__media">
                {recipe.badge ? <span className="recipe-card__badge">{recipe.badge}</span> : null}
                <button
                  type="button"
                  aria-label={`${recipe.title} 저장`}
                  aria-pressed={savedIds.includes(recipe.id)}
                  onClick={() => toggleSaved(recipe.id)}
                >
                  {savedIds.includes(recipe.id) ? '♥' : '♡'}
                </button>
                <Link to={`/recipes/${recipe.id}`} aria-label={`${recipe.title} 상세 보기`}>
                  <ImageSlot className="recipe-card__image" src={recipe.image} />
                </Link>
              </div>
              <div className="recipe-card__body">
                <h3>{recipe.title}</h3>
                <p>{recipe.time} · {recipe.level}</p>
                <div>
                  {recipe.tags.map((tag) => (
                    <span key={tag}>{tag}</span>
                  ))}
                </div>
                <div className="recipe-card__actions">
                  <button type="button" onClick={() => selectRecipe(recipe.id)}>
                    {selectedRecipe.id === recipe.id ? '선택됨' : '선택'}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      selectRecipe(recipe.id)
                      navigate(`/recipes/${recipe.id}`)
                    }}
                  >
                    상세
                  </button>
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
            setProgressStep(2)
          }}
        >
          {visibleCount >= filteredRecipes.length ? '모든 레시피를 보고 있어요' : '더 많은 레시피 보기'}
        </button>
      </section>

      <section className="recipe-list-cta">
        <ImageSlot className="recipe-list-cta__image" src={imagePutting} />
        <div>
          <h2>냉장고 속 재료로 맞춤 레시피를 찾아보세요!</h2>
          <p>지금 냉장고 재료를 확인하고, 만들 수 있는 레시피를 추천받아보세요.</p>
        </div>
        <button type="button" onClick={() => navigate('/fridge')}>냉장고 재료 확인하기</button>
      </section>

      <ImageSlot className="recipe-list-mobile-art" src={imageRecommendation} />
    </section>
  )
}

export default RecipeList
