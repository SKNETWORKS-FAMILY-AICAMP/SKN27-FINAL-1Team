import assert from 'node:assert/strict'
import test from 'node:test'

import { RecipeFilterConfig } from './recipeFilterConfig.js'

test('URL 키·필터 code는 짧고 고정 길이며 검색어만 한글을 유지한다', () => {
  const params = RecipeFilterConfig.buildSearchParams({
    query: '소고기',
    category: 'main',
    timeFilter: 'le30',
    levelFilter: 'easy',
  })

  assert.equal(params.get('q'), '소고기')
  assert.equal(params.get('c'), 'ct03')
  assert.equal(params.get('t'), 'tm02')
  assert.equal(params.get('d'), 'df02')
  assert.equal(params.get('c').length, 4)
  assert.equal(params.get('t').length, 4)
  assert.equal(params.get('d').length, 4)
  assert.equal(params.toString(), 'q=%EC%86%8C%EA%B3%A0%EA%B8%B0&c=ct03&t=tm02&d=df02')
})

test('짧은 URL을 criteria name으로 파싱하고 API에는 한글 값을 보낸다', () => {
  const criteria = RecipeFilterConfig.parseSearchParams('?q=소고기&t=tm02&d=df02&c=ct03')

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

test('구버전 긴 키·한글 값도 name으로 해석한다', () => {
  const criteria = RecipeFilterConfig.parseSearchParams(
    '?cooking_time=30분이내&difficulty=쉬움&category=국·탕',
  )
  assert.equal(criteria.timeFilter, 'le30')
  assert.equal(criteria.levelFilter, 'easy')
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
