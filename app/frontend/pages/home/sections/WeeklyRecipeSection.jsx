import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { API_URL } from '../../../utils/api.js'

const recommendationLabels = ['이번 주 추천', '든든한 메뉴', '별미 추천']
const weeklyRecipeIds = [175, 50, 88]

function WeeklyRecipeSection() {
  const [recipes, setRecipes] = useState([])

  useEffect(() => {
    const controller = new AbortController()

    Promise.all(
      weeklyRecipeIds.map(async (recipeId) => {
        const response = await fetch(`${API_URL}/api/v1/recipes/${recipeId}`, {
          signal: controller.signal,
        })
        if (!response.ok) throw new Error(`레시피 ${recipeId} 조회 실패`)
        return response.json()
      }),
    )
      .then(setRecipes)
      .catch((error) => {
        if (error.name !== 'AbortError') setRecipes([])
      })

    return () => controller.abort()
  }, [])

  return (
    <section className="home-section home-weekly-recipes" aria-labelledby="home-weekly-recipe-title">
      <header className="home-weekly-recipes__heading">
        <h2 id="home-weekly-recipe-title">금주의 추천 레시피</h2>
        <p>이번 주 밥상에 잘 어울리는 메뉴를 골라봤어요.</p>
      </header>

      <div className="home-weekly-recipes__grid">
        {recipes.map((recipe, index) => (
          <Link className="home-weekly-recipe" to={`/recipes/${recipe.recipe_id}`} key={recipe.recipe_id}>
            <div className="home-weekly-recipe__image">
              <img src={recipe.main_image_url} alt={recipe.title} loading="lazy" />
              <span>{recommendationLabels[index]}</span>
            </div>
            <div className="home-weekly-recipe__body">
              <p>{recipe.cooking_time_min ? `${recipe.cooking_time_min}분` : '시간 정보 없음'} · {recipe.difficulty || '난이도 정보 없음'}</p>
              <h3>{recipe.title}</h3>
            </div>
          </Link>
        ))}
      </div>
    </section>
  )
}

export default WeeklyRecipeSection
