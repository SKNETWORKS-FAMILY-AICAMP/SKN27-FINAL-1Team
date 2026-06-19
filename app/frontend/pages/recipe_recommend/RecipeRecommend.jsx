import React from 'react'

function RecipeRecommend({
  title = '레시피 추천',
  description = '레시피 조회 및 추천 결과 화면입니다.',
}) {
  return (
    <div className="page-container">
      <h1>{title}</h1>
      <p>{description}</p>
    </div>
  )
}

export default RecipeRecommend
