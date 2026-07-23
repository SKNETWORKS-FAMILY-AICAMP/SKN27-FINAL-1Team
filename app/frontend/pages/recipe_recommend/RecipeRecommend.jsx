import React from 'react'
import { Link } from 'react-router-dom'

function RecipeRecommend({
  title = '레시피 추천',
  description = '냉장고에 있는 재료로 만들 수 있는 레시피를 확인해보세요.',
}) {
  return (
    <div className="page-container">
      <h1>{title}</h1>
      <p>{description}</p>
      <div className="page-container__actions">
        <Link to="/recipe-fridge">냉장고파먹기 추천</Link>
      </div>
    </div>
  )
}

export default RecipeRecommend
