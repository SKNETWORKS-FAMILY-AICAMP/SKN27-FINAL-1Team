import assert from 'node:assert/strict'
import test from 'node:test'
import { shouldRevealAppBanner } from './headerBanner.js'

test('the app banner waits for home scrolling but shows immediately elsewhere', () => {
  assert.equal(shouldRevealAppBanner('/', 200, 800), false)
  assert.equal(shouldRevealAppBanner('/', 320, 800), true)
  assert.equal(shouldRevealAppBanner('/fridge', 0, 800), true)
})
