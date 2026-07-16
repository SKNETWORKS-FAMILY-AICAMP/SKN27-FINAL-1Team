import assert from 'node:assert/strict'
import test from 'node:test'

import {
  createIngredientImageCatalog,
  getIngredientImageUrl,
} from './ingredientImages.js'

const catalog = createIngredientImageCatalog({
  items: [
    { id: 'first', name: '달걀', category: '유제품·달걀', aliases: ['계란', '공통'], imageUrl: 'egg.webp' },
    { id: 'second', name: '두부', category: '콩·견과·묵', aliases: ['공통'], imageUrl: 'tofu.webp' },
  ],
  fallbacks: [
    { id: 'vegetable', name: '채소 기본 이미지', category: '채소', aliases: [], imageUrl: 'vegetable.webp' },
    { id: 'dairy', name: '유제품 기본 이미지', category: '유제품·달걀', aliases: [], imageUrl: 'dairy.webp' },
    { id: 'other', name: '기타 기본 이미지', category: '기타', aliases: [], imageUrl: 'other.webp' },
  ],
})

test('대표명, 별칭, 카테고리, 기타 순서로 이미지 URL을 찾는다', () => {
  assert.equal(getIngredientImageUrl(catalog, ' 두 부 ', '기타'), 'tofu.webp')
  assert.equal(getIngredientImageUrl(catalog, ' 계 란 ', '기타'), 'egg.webp')
  assert.equal(getIngredientImageUrl(catalog, '알 수 없음', '유제품'), 'dairy.webp')
  assert.equal(getIngredientImageUrl(catalog, '알 수 없음', '없는 분류'), 'other.webp')
})

test('같은 별칭은 매니페스트에 먼저 등록된 대표 이미지를 유지한다', () => {
  assert.equal(getIngredientImageUrl(catalog, '공 통'), 'egg.webp')
})
