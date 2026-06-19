import React, { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import './MenuRecommend.css'

import iconAlarm from '../../assets/extracted/icons/icon_alarm.png'
import iconBasket from '../../assets/extracted/icons/icon_basket.png'
import iconRefrigerator from '../../assets/extracted/icons/icon_refrigerator.png'
import imageEatRefrigerator from '../../assets/extracted/images/image_eat_refrigerator.png'
import imageHello from '../../assets/extracted/images/image_hello.png'
import imageMenuRecommendation from '../../assets/extracted/images/image_menu_recommendation.png'
import imageSearch from '../../assets/extracted/images/image_search.png'

const countOptions = [3, 5, 7]

const recipes = [
  {
    id: 'green-onion-tofu-egg-stew',
    title: '대파 두부 계란찌개',
    category: '든든한 한 끼',
    time: '20분',
    level: '쉬움',
    reason: '국물과 단백질을 같이 챙길 수 있는 균형 메뉴예요.',
    image: imageEatRefrigerator,
  },
  {
    id: 'tomato-pasta',
    title: '토마토 파스타',
    category: '간단 요리',
    time: '15분',
    level: '쉬움',
    reason: '조리 시간이 짧고 실패 확률이 낮아 바쁜 날에 좋아요.',
  },
  {
    id: 'mushroom-perilla-soup',
    title: '버섯 들깨탕',
    category: '따뜻한 국물',
    time: '25분',
    level: '보통',
    reason: '부드럽고 고소한 맛이라 가볍게 먹고 싶은 날에 잘 맞아요.',
  },
  {
    id: 'kimchi-fried-rice',
    title: '김치 볶음밥',
    category: '빠른 한 끼',
    time: '15분',
    level: '쉬움',
    reason: '익숙한 맛에 만족감이 좋아 점심 메뉴로 추천해요.',
  },
  {
    id: 'rolled-egg',
    title: '계란말이',
    category: '반찬 겸 식사',
    time: '10분',
    level: '쉬움',
    reason: '간단한 재료로 만들 수 있고 다른 메뉴와 곁들이기 좋아요.',
  },
  {
    id: 'tofu-soy-braise',
    title: '두부 간장조림',
    category: '절약 메뉴',
    time: '20분',
    level: '쉬움',
    reason: '재료비 부담이 적고 밥반찬으로 활용하기 좋아요.',
  },
  {
    id: 'pork-soy-stir-fry',
    title: '돼지고기 간장볶음',
    category: '고기 메뉴',
    time: '18분',
    level: '쉬움',
    reason: '진한 메인 요리가 필요할 때 만족도가 높은 메뉴예요.',
  },
]

function ImageSlot({ src, alt = '', className = '' }) {
  return (
    <span className={`menu-recommend-image-slot ${src ? 'is-filled' : ''} ${className}`}>
      {src ? <img src={src} alt={alt} /> : null}
    </span>
  )
}

function MenuRecommend() {
  const [selectedCount, setSelectedCount] = useState(5)
  const [generatedCount, setGeneratedCount] = useState(0)
  const [selectedIds, setSelectedIds] = useState([])
  const [savedIds, setSavedIds] = useState([])

  const generatedRecipes = useMemo(
    () => recipes.slice(0, generatedCount),
    [generatedCount],
  )

  const handleGenerate = () => {
    setGeneratedCount(selectedCount)
    setSelectedIds([])
    setSavedIds([])
  }

  const handleSelect = (recipeId) => {
    setSelectedIds((prev) =>
      prev.includes(recipeId) ? prev.filter((id) => id !== recipeId) : [...prev, recipeId],
    )
  }

  const handleSave = () => {
    setSavedIds((prev) => Array.from(new Set([...prev, ...selectedIds])))
  }

  return (
    <section className="menu-recommend-page" aria-labelledby="menu-recommend-title">
      <div className="menu-recommend-hero">
        <div className="menu-recommend-hero__copy">
          <h1 id="menu-recommend-title">메뉴 추천</h1>
          <p>
            냉장고 재료와 상관없이 지금 먹고 싶은 분위기에 맞춰
            만들기 좋은 레시피를 추천받아보세요.
          </p>
        </div>
        <ImageSlot
          className="menu-recommend-hero__image"
          src={imageMenuRecommendation}
          alt="메뉴를 추천하는 밥벌이 캐릭터"
        />
      </div>

      <section className="menu-recommend-builder" aria-labelledby="builder-title">
        <div>
          <h2 id="builder-title">레시피 몇 개 받을래요?</h2>
          <p>원하는 개수를 고르면 그만큼 메뉴 후보를 생성해드려요.</p>
        </div>
        <div className="menu-recommend-counts" role="group" aria-label="추천 개수 선택">
          {countOptions.map((count) => (
            <button
              className={selectedCount === count ? 'is-active' : ''}
              key={count}
              type="button"
              onClick={() => setSelectedCount(count)}
            >
              {count}개
            </button>
          ))}
        </div>
        <button className="menu-recommend-primary" type="button" onClick={handleGenerate}>
          {selectedCount}개 추천받기
        </button>
      </section>

      <div className="menu-recommend-summary" aria-label="추천 상태 요약">
        <article>
          <ImageSlot src={iconAlarm} alt="추천 방식" />
          <span>추천 방식</span>
          <strong>취향 기반</strong>
        </article>
        <article>
          <ImageSlot src={iconBasket} alt="생성 개수" />
          <span>생성 개수</span>
          <strong>{generatedCount || selectedCount}개</strong>
        </article>
        <article>
          <ImageSlot src={iconRefrigerator} alt="재료 조건" />
          <span>재료 조건</span>
          <strong>상관없음</strong>
        </article>
      </div>

      <div className="menu-recommend-content">
        <main className="menu-recommend-results">
          <div className="menu-recommend-results__header">
            <div>
              <h2>추천 결과</h2>
              <p>
                {generatedCount
                  ? `${generatedCount}개의 레시피가 생성됐어요. 저장할 레시피를 선택해보세요.`
                  : '아직 추천을 생성하지 않았어요.'}
              </p>
            </div>
            <button
              className="menu-recommend-save"
              type="button"
              disabled={selectedIds.length === 0}
              onClick={handleSave}
            >
              선택 레시피 저장
            </button>
          </div>

          {generatedCount === 0 ? (
            <div className="menu-recommend-empty">
              <ImageSlot src={imageSearch} alt="추천 전 빈 상태" />
              <strong>몇 개 추천받을지 먼저 골라주세요.</strong>
              <p>추천 생성 후 마음에 드는 카드를 선택해 저장할 수 있어요.</p>
            </div>
          ) : (
            <div className="menu-recommend-grid">
              {generatedRecipes.map((recipe) => {
                const isSelected = selectedIds.includes(recipe.id)
                const isSaved = savedIds.includes(recipe.id)

                return (
                  <article
                    className={[
                      'menu-recommend-card',
                      isSelected ? 'is-selected' : '',
                      isSaved ? 'is-saved' : '',
                    ]
                      .filter(Boolean)
                      .join(' ')}
                    key={recipe.id}
                  >
                    <button
                      className="menu-recommend-card__select"
                      type="button"
                      onClick={() => handleSelect(recipe.id)}
                      aria-pressed={isSelected}
                    >
                      {isSelected ? '선택됨' : '선택'}
                    </button>
                    <div className="menu-recommend-card__media">
                      <span>{recipe.category}</span>
                      <ImageSlot
                        className="menu-recommend-card__image"
                        src={recipe.image}
                        alt={recipe.image ? recipe.title : ''}
                      />
                    </div>
                    <div className="menu-recommend-card__body">
                      <h3>{recipe.title}</h3>
                      <p>
                        {recipe.time} · {recipe.level}
                      </p>
                      <div>
                        <b>추천 이유</b>
                        <span>{recipe.reason}</span>
                      </div>
                      <div className="menu-recommend-card__actions">
                        <Link to={`/recipes/${recipe.id}`}>레시피 보기</Link>
                        <button
                          type="button"
                          disabled={isSaved}
                          onClick={() => handleSelect(recipe.id)}
                        >
                          {isSaved ? '저장 완료' : '저장 후보'}
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
          <h2 id="guide-title">추천은 이렇게 진행돼요</h2>
          <ol>
            <li>
              <strong>추천 개수 선택</strong>
              <p>3개, 5개, 7개 중 원하는 후보 수를 골라요.</p>
            </li>
            <li>
              <strong>메뉴 후보 생성</strong>
              <p>냉장고 재료와 상관없이 먹고 싶은 한 끼를 추천해요.</p>
            </li>
            <li>
              <strong>레시피 저장</strong>
              <p>마음에 드는 카드를 선택하고 저장할 수 있어요.</p>
            </li>
          </ol>
          <ImageSlot className="menu-recommend-guide__image" src={imageHello} alt="인사하는 밥벌이" />
        </aside>
      </div>
    </section>
  )
}

export default MenuRecommend
