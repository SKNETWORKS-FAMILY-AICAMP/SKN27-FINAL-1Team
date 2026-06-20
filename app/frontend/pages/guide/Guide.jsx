import React, { useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import './Guide.css'

import iconBasket from '../../assets/extracted/icons/icon_basket.png'
import imageGuide from '../../assets/extracted/images/image_guide.png'
import {
  guideIngredients as ingredients,
  guideRecipes as recipes,
  guideTips,
} from '../../mock/guideMock.js'

function ImageSlot({ src, alt = '', className = '' }) {
  return (
    <span className={`guide-image-slot ${src ? 'is-filled' : ''} ${className}`}>
      {src ? <img src={src} alt={alt} /> : null}
    </span>
  )
}

function Guide() {
  const navigate = useNavigate()
  const { ingredientName } = useParams()
  const [selectedTipTitle, setSelectedTipTitle] = useState(guideTips[0].title)
  const [searchTerm, setSearchTerm] = useState('')
  const decodedIngredientName = ingredientName ? decodeURIComponent(ingredientName) : ''
  const isDetailPage = Boolean(decodedIngredientName)

  const filteredIngredients = useMemo(() => {
    const normalizedQuery = searchTerm.trim().toLowerCase()

    return ingredients.filter((ingredient) =>
      ingredient.name.toLowerCase().includes(normalizedQuery),
    )
  }, [searchTerm])

  const fridgeIngredients = ingredients.slice(0, 6)
  const selectedIngredient =
    ingredients.find((ingredient) => ingredient.name === decodedIngredientName) ?? ingredients[0]
  const selectedTip = guideTips.find((tip) => tip.title === selectedTipTitle) ?? guideTips[0]

  const selectIngredient = (name) => {
    navigate(`/guide/${encodeURIComponent(name)}`)
  }

  const openRecipes = () => {
    navigate(`/recipes?query=${encodeURIComponent(selectedIngredient.name)}`)
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

      <section className="guide-panel guide-ingredients" aria-labelledby="guide-ingredients-title">
        <div className="guide-section-title" id="guide-ingredients-title">
          내 냉장고 재료
        </div>
        <div className="guide-ingredient-list" aria-label="내 냉장고 재료 목록">
          {fridgeIngredients.map((ingredient) => (
            <button
              className={`guide-ingredient ${
                isDetailPage && selectedIngredient.name === ingredient.name ? 'is-active' : ''
              }`}
              key={ingredient.name}
              type="button"
              onClick={() => selectIngredient(ingredient.name)}
            >
              <ImageSlot alt="" className="guide-ingredient__image" src={ingredient.image} />
              <span>{ingredient.name}</span>
            </button>
          ))}
        </div>
      </section>

      {!isDetailPage ? (
        <section className="guide-panel guide-all" aria-labelledby="guide-all-title">
          <div className="guide-all__header">
            <div>
              <h2 id="guide-all-title">전체 재료 목록</h2>
              <p>궁금한 재료를 선택하면 보관, 손질, 세척 정보를 자세히 볼 수 있어요.</p>
            </div>
            <span>{filteredIngredients.length}개</span>
          </div>

          <div className="guide-all-list" aria-label="전체 재료 목록">
            {filteredIngredients.map((ingredient) => (
              <button
                className="guide-all-item"
                key={ingredient.name}
                type="button"
                onClick={() => selectIngredient(ingredient.name)}
              >
                <ImageSlot alt="" className="guide-all-item__image" src={ingredient.image} />
                <div>
                  <strong>{ingredient.name}</strong>
                  <p>{ingredient.name}의 보관, 손질, 세척 가이드를 확인해보세요.</p>
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

          <div className="guide-content-grid">
            <article className="guide-panel guide-detail">
              <div className="guide-detail__header">
                <ImageSlot alt="" className="guide-detail__image" src={selectedIngredient.image} />
                <div>
                  <h2>{selectedIngredient.name}</h2>
                  <p>{selectedIngredient.name}의 보관, 손질, 세척 팁을 확인해보세요.</p>
                  <span className="guide-owned-badge">내 냉장고에 있어요</span>
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
                    <strong>{tip.chip}</strong>
                  </section>
                ))}
              </div>
            </article>

            <aside className="guide-panel guide-tip-detail" aria-labelledby="guide-tip-detail-title">
              <span>{selectedIngredient.name}</span>
              <h2 id="guide-tip-detail-title">{selectedTip.title}</h2>
              <ul>
                {selectedTip.points.map((point) => (
                  <li key={point}>{point}</li>
                ))}
              </ul>
              <strong>{selectedTip.chip}</strong>
              <p>출처: {selectedTip.source}</p>
            </aside>
          </div>

          <section className="guide-panel guide-recipes" aria-labelledby="guide-recipes-title">
            <div className="guide-recipes__header">
              <h2 id="guide-recipes-title">연관 레시피</h2>
              <span>총 7개</span>
            </div>

            <div className="guide-recipe-list">
              {recipes.map((recipe) => (
                <article className="guide-recipe-card" key={recipe.title}>
                  <ImageSlot alt="" className="guide-recipe-card__image" />
                  <div>
                    <h3>{recipe.title}</h3>
                    <p>{recipe.meta}</p>
                  </div>
                  <button type="button" onClick={() => navigate(`/recipes/${recipe.id}`)}>
                    보기
                  </button>
                </article>
              ))}

              <article className="guide-recipe-more">
                <ImageSlot alt="" className="guide-recipe-more__icon" src={iconBasket} />
                <strong>더 많은 레시피를 확인해보세요!</strong>
                <button className="guide-primary-button" type="button" onClick={openRecipes}>
                  전체 보기
                </button>
              </article>
            </div>
          </section>
        </>
      )}
    </section>
  )
}

export default Guide
