import assert from 'node:assert/strict'
import test from 'node:test'

import { getFridgeNameClass } from './fridgeName.js'

test('냉장고 카드의 재료명 길이에 맞는 폰트 단계를 반환한다', () => {
  assert.equal(getFridgeNameClass('12345'), '')
  assert.equal(getFridgeNameClass('123456'), 'is-name-medium')
  assert.equal(getFridgeNameClass('123456789'), 'is-name-long')
  assert.equal(getFridgeNameClass('123456789012'), 'is-name-very-long')
})
