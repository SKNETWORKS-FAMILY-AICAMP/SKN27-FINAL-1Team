import assert from 'node:assert/strict'
import test from 'node:test'

import { RecipeFilterConfig } from './recipeFilterConfig.js'

test('URL에는 검색·필터 쿼리를 넣지 않는다', () => {
  const params = RecipeFilterConfig.buildSearchParams({
    query: '소고기',
    category: 'main',
    timeFilter: 'le30',
    levelFilter: 'easy',
  })
  assert.equal(params.toString(), '')
})

test('criteria는 location.state에서 읽고 API에는 한글 값을 보낸다', () => {
  const criteria = RecipeFilterConfig.parseCriteria('', {
    query: '소고기',
    ingredient: '',
    category: 'main',
    timeFilter: 'le30',
    levelFilter: 'easy',
    browseAll: false,
  })

  assert.deepEqual(criteria, {
    query: '소고기',
    ingredient: '',
    category: 'main',
    timeFilter: 'le30',
    levelFilter: 'easy',
    browseAll: false,
  })

  const api = RecipeFilterConfig.toApiParams(criteria, 1, 20)
  assert.equal(api.query, '소고기')
  assert.equal(api.category, '메인요리')
  assert.equal(api.cooking_time_label, '30분이내')
  assert.equal(api.difficulty, '쉬움')
})

test('구버전 URL 검색어·필터도 해석한다', () => {
  const criteria = RecipeFilterConfig.parseCriteria(
    '?q=소고기&t=tm02&d=df02&c=ct02',
  )
  assert.equal(criteria.query, '소고기')
  assert.equal(criteria.timeFilter, 'le30')
  assert.equal(criteria.levelFilter, 'easy')
  assert.equal(criteria.category, 'soup')
  assert.equal(RecipeFilterConfig.hasLegacyCriteriaInUrl('?c=ct03'), true)
  assert.equal(RecipeFilterConfig.hasLegacyCriteriaInUrl(''), false)
})

test('location.state가 있으면 구버전 URL보다 우선한다', () => {
  const criteria = RecipeFilterConfig.parseCriteria('?q=돼지고기&c=ct03', {
    query: '소고기',
    category: 'soup',
  })
  assert.equal(criteria.query, '소고기')
  assert.equal(criteria.category, 'soup')
})

test('필터 code는 클래스약자+두자리 번호 형식이다', () => {
  for (const def of [
    ...RecipeFilterConfig.recipeTypes,
    ...RecipeFilterConfig.difficulties,
    ...RecipeFilterConfig.cookingTimes,
  ]) {
    assert.match(def.code, /^(ct|df|tm)\d{2}$/)
    assert.equal(def.code.length, 4)
  }
})
