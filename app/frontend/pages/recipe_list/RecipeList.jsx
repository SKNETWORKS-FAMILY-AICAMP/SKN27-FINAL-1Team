import React from 'react'
import { Link } from 'react-router-dom'
import './RecipeList.css'

import iconRefrigerator from '../../assets/extracted/icons/icon_refrigerator.png'
import imageEatRefrigerator from '../../assets/extracted/images/image_eat_refrigerator.png'
import imagePutting from '../../assets/extracted/images/image_putting.png'
import imageRecommendation from '../../assets/extracted/images/image_recommendation.png'
import imageSearch from '../../assets/extracted/images/image_search.png'

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
    time: '20분',
    level: '쉬움',
    tags: ['대파', '두부', '계란', '양파'],
    badge: '인기',
    image: imageEatRefrigerator,
  },
  {
    id: 'mushroom-perilla-soup',
    title: '버섯 들깨탕',
    time: '25분',
    level: '보통',
    tags: ['버섯', '두부', '들깨'],
    badge: '간단',
  },
  {
    id: 'kimchi-fried-rice',
    title: '김치 볶음밥',
    time: '15분',
    level: '쉬움',
    tags: ['김치', '밥', '대파', '계란'],
  },
  {
    id: 'tofu-soy-braise',
    title: '두부 간장조림',
    time: '20분',
    level: '쉬움',
    tags: ['두부', '간장', '대파'],
  },
  {
    id: 'rolled-egg',
    title: '계란말이',
    time: '10분',
    level: '쉬움',
    tags: ['계란', '대파', '소금'],
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
  return (
    <section className="recipe-list-page" aria-labelledby="recipe-list-title">
      <div className="recipe-list-hero">
        <div className="recipe-list-hero__copy">
          <h1 id="recipe-list-title">
            냉장고 속 재료로
            <strong>맛있는 한 끼 레시피</strong>
          </h1>
          <p>냉장고 재료로 만들 수 있는 다양한 레시피를 검색하고 확인해 보세요.</p>
          <label className="recipe-list-search" aria-label="레시피 검색">
            <span aria-hidden="true" />
            <input type="search" placeholder="레시피명, 재료명을 검색해보세요" />
            <button type="button">검색</button>
          </label>
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

      <div className="recipe-list-quick" aria-label="레시피 바로가기">
        {quickMenus.map((menu) => (
          <button className="recipe-list-quick-card" type="button" key={menu.title}>
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
          <select aria-label="카테고리">
            <option>카테고리 전체</option>
          </select>
          <select aria-label="조리시간">
            <option>조리시간 전체</option>
          </select>
          <select aria-label="난이도">
            <option>난이도 전체</option>
          </select>
          <label>
            <input type="checkbox" />
            냉장고 재료로만 보기
          </label>
          <select aria-label="정렬">
            <option>인기순</option>
          </select>
          <div className="recipe-list-view">
            <button className="is-active" type="button" aria-label="그리드 보기">
              <span />
            </button>
            <button type="button" aria-label="리스트 보기">
              <span />
            </button>
          </div>
        </div>
      </section>

      <section className="recipe-list-results" aria-labelledby="recipe-results-title">
        <h2 id="recipe-results-title">전체 레시피 <span>(128)</span></h2>
        <div className="recipe-list-grid">
          {recipes.map((recipe) => (
            <article className="recipe-card" key={recipe.title}>
              <div className="recipe-card__media">
                {recipe.badge ? <span className="recipe-card__badge">{recipe.badge}</span> : null}
                <button type="button" aria-label={`${recipe.title} 저장`}>
                  ♡
                </button>
                <Link to={`/recipes/${recipe.id}`} aria-label={`${recipe.title} 상세 보기`}>
                  <ImageSlot className="recipe-card__image" src={recipe.image} />
                </Link>
              </div>
              <Link className="recipe-card__body" to={`/recipes/${recipe.id}`}>
                <h3>{recipe.title}</h3>
                <p>{recipe.time} · {recipe.level}</p>
                <div>
                  {recipe.tags.map((tag) => (
                    <span key={tag}>{tag}</span>
                  ))}
                </div>
              </Link>
            </article>
          ))}
        </div>

        <button className="recipe-list-more" type="button">
          더 많은 레시피 보기
        </button>
      </section>

      <section className="recipe-list-cta">
        <ImageSlot className="recipe-list-cta__image" src={imagePutting} />
        <div>
          <h2>냉장고 속 재료로 맞춤 레시피를 찾아보세요!</h2>
          <p>지금 냉장고 재료를 확인하고, 만들 수 있는 레시피를 추천받아보세요.</p>
        </div>
        <button type="button">냉장고 재료 확인하기</button>
      </section>

      <ImageSlot className="recipe-list-mobile-art" src={imageRecommendation} />
    </section>
  )
}

export default RecipeList
