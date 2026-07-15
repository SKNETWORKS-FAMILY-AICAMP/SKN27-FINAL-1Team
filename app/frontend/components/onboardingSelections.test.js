import assert from 'node:assert/strict'
import test from 'node:test'

import { splitIngredientSelections } from './onboardingSelections.js'

test('저장된 재료를 기본 선택과 직접 입력 태그로 나눈다', () => {
  assert.deepEqual(
    splitIngredientSelections(['우유', '복숭아', '우유', '  새우  '], ['우유', '계란']),
    { selected: ['우유'], custom: ['복숭아', '새우'] },
  )
})
