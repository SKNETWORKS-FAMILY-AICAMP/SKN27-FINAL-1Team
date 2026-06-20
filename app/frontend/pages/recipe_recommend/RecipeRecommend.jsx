import React from 'react'
import { Link } from 'react-router-dom'

function RecipeRecommend({
  title = '레시피 추천',
  description = '냉장고 재료 기반 추천과 취향 기반 메뉴 추천 중 원하는 흐름을 선택해보세요.',
}) {
  return (
    <div className="page-container">
      <h1>{title}</h1>
      <p>{description}</p>
      <div className="page-container__actions">
        <Link to="/recipe-fridge">냉장고파먹기 추천</Link>
        <Link to="/menu-recommend">메뉴 추천 받기</Link>
      </div>
    </div>
  )
}

export default RecipeRecommend
