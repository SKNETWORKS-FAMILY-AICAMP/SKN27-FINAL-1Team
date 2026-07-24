import assert from 'node:assert/strict'
import test from 'node:test'

import { buildRecipeFilterOptions, mergeRecipePages } from './recipeListState.js'
import { RecipeFilterConfig } from './recipeFilterConfig.js'

test('검색 결과가 있으면 facets로 필터 옵션을 구성한다', () => {
  const options = buildRecipeFilterOptions(4, {
    categories: ['국·탕', '국·탕', '', null],
    difficulties: ['쉬움'],
    cooking_time_labels: ['15분이내', '30분이상'],
  })

  assert.deepEqual(
    options.recipeTypes.map((option) => option.value),
    [RecipeFilterConfig.FILTER_ALL, 'soup'],
  )
  assert.deepEqual(
    options.difficulties.map((option) => option.value),
    [RecipeFilterConfig.FILTER_ALL, 'easy'],
  )
  assert.deepEqual(
    options.cookingTimes.map((option) => option.value),
    [RecipeFilterConfig.FILTER_ALL, 'le15', 'ge30'],
  )
  assert.equal(options.cookingTimes.find((option) => option.value === 'le15')?.label, '15분')
})

test('검색 결과가 없으면 기존 기본 필터 옵션을 사용한다', () => {
  const options = buildRecipeFilterOptions(0, {
    categories: [],
    difficulties: [],
    cooking_time_labels: [],
  })

  assert.ok(options.recipeTypes.length > 1)
  assert.ok(options.difficulties.length > 1)
  assert.ok(options.cookingTimes.length > 1)
})

test('결과는 있지만 속성값이 없는 필터 축에는 전체 옵션만 표시한다', () => {
  const options = buildRecipeFilterOptions(2, {
    categories: [],
    difficulties: [],
    cooking_time_labels: [],
  })

  assert.deepEqual(options.recipeTypes.map((option) => option.value), [RecipeFilterConfig.FILTER_ALL])
  assert.deepEqual(options.difficulties.map((option) => option.value), [RecipeFilterConfig.FILTER_ALL])
  assert.deepEqual(options.cookingTimes.map((option) => option.value), [RecipeFilterConfig.FILTER_ALL])
})

test('다음 페이지를 recipe_id 기준으로 중복 없이 누적한다', () => {
  assert.deepEqual(
    mergeRecipePages(
      [{ recipe_id: 1 }, { recipe_id: 2 }],
      [{ recipe_id: 2 }, { recipe_id: 3 }],
    ).map((recipe) => recipe.recipe_id),
    [1, 2, 3],
  )
})
