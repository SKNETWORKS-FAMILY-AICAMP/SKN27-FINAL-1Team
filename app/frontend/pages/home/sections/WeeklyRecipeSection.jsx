import { Link } from 'react-router-dom'

const recommendationLabels = ['이번 주 추천', '든든한 메뉴', '별미 추천']
const recipes = [
  {
    recipe_id: 7039515,
    title: '야채찜',
    cooking_time_min: 15,
    difficulty: '고급',
    main_image_url: 'https://recipe1.ezmember.co.kr/cache/recipe/2024/11/28/c551a8c329145b190d44e9f11a9833761.jpg?w=1000',
  },
  {
    recipe_id: 7038839,
    title: '통삼겹수육',
    cooking_time_min: 60,
    difficulty: '중급',
    main_image_url: 'https://recipe1.ezmember.co.kr/cache/recipe/2024/11/18/daca23c1a9d9fc0241e9e546d911d96a1.jpg',
  },
  {
    recipe_id: 7036298,
    title: '생오리불고기',
    cooking_time_min: 60,
    difficulty: '중급',
    main_image_url: 'https://recipe1.ezmember.co.kr/cache/recipe/2024/10/12/f608d6ce0a03652073bf6a55a13cf1d31.jpg',
  },
]

function WeeklyRecipeSection() {
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
              <img src={recipe.main_image_url} alt="" />
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
