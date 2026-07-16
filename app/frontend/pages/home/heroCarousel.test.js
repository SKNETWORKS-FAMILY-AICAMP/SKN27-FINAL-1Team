import assert from 'node:assert/strict'
import test from 'node:test'
import { getDragDirection, wrapSlideIndex } from './heroCarousel.js'

test('hero slides wrap in both directions', () => {
  assert.equal(wrapSlideIndex(5, 5), 0)
  assert.equal(wrapSlideIndex(-1, 5), 4)
})

test('hero drag only moves after crossing the threshold', () => {
  assert.equal(getDragDirection(20), 0)
  assert.equal(getDragDirection(-80), 1)
  assert.equal(getDragDirection(80), -1)
})
