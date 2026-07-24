import assert from 'node:assert/strict'
import test from 'node:test'
import { INDEXABLE_PATHS, getSeoConfig, normalizePathname } from './seo.js'

test('only the approved public routes are indexable', () => {
  assert.deepEqual(INDEXABLE_PATHS, ['/', '/faq', '/terms', '/privacy'])

  for (const pathname of INDEXABLE_PATHS) {
    const config = getSeoConfig(pathname)
    assert.equal(config.indexable, true)
    assert.equal(config.robots, 'index, follow')
    assert.ok(config.canonical)
  }
})

test('indexable routes use a self-referencing canonical URL', () => {
  assert.equal(getSeoConfig('/').canonical, 'https://www.bobbeori.com/')
  assert.equal(getSeoConfig('/faq').canonical, 'https://www.bobbeori.com/faq')
  assert.equal(getSeoConfig('/terms/').canonical, 'https://www.bobbeori.com/terms')
  assert.equal(getSeoConfig('/privacy').canonical, 'https://www.bobbeori.com/privacy')
})

test('personalized and authentication routes are noindex', () => {
  for (const pathname of [
    '/login',
    '/mypage',
    '/fridge',
    '/receipt-ocr',
    '/shopping-list',
    '/recipes/123',
    '/guide/감자',
  ]) {
    const config = getSeoConfig(pathname)
    assert.equal(config.indexable, false)
    assert.equal(config.robots, 'noindex, follow')
    assert.equal(config.canonical, null)
  }
})

test('authentication callbacks are noindex and nofollow', () => {
  const config = getSeoConfig('/auth/callback/google')

  assert.equal(config.indexable, false)
  assert.equal(config.robots, 'noindex, nofollow')
  assert.equal(config.canonical, null)
})

test('unknown routes default to noindex', () => {
  const config = getSeoConfig('/not-a-real-page')

  assert.equal(config.indexable, false)
  assert.equal(config.robots, 'noindex, follow')
  assert.equal(config.canonical, null)
})

test('pathname normalization removes duplicate and trailing slashes', () => {
  assert.equal(normalizePathname(''), '/')
  assert.equal(normalizePathname('/faq/'), '/faq')
  assert.equal(normalizePathname('//terms//'), '/terms')
})

