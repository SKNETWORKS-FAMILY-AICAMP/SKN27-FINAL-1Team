import assert from 'node:assert/strict'
import test from 'node:test'
import { INDEXABLE_PATHS, getSeoConfig } from '../utils/seo.js'
import { renderSeoHtml, routeOutputSegments } from './prerender-seo-lib.mjs'

const template = `<!doctype html>
<html lang="ko">
  <head>
    <title>기본 제목</title>
    <meta name="description" content="기본 설명" />
    <meta name="robots" content="index, follow" />
    <link rel="canonical" href="https://www.bobbeori.com/" />
    <meta property="og:title" content="기본 제목" />
    <meta property="og:description" content="기본 설명" />
    <meta property="og:url" content="https://www.bobbeori.com/" />
    <meta name="twitter:title" content="기본 제목" />
    <meta name="twitter:description" content="기본 설명" />
  </head>
  <body><div id="root"></div></body>
</html>`

test('prerendered HTML contains route-specific metadata for every public URL', () => {
  for (const pathname of INDEXABLE_PATHS) {
    const config = getSeoConfig(pathname)
    const html = renderSeoHtml(template, config)

    assert.ok(html.includes(`<title>${config.title}</title>`))
    assert.ok(html.includes(`content="${config.description}"`))
    assert.ok(html.includes(`href="${config.canonical}"`))
    assert.ok(html.includes(`property="og:url" content="${config.canonical}"`))
    assert.ok(html.includes('name="robots" content="index, follow"'))
  }
})

test('public routes map to nested static index files', () => {
  assert.deepEqual(routeOutputSegments('/'), ['index.html'])
  assert.deepEqual(routeOutputSegments('/faq'), ['faq', 'index.html'])
  assert.deepEqual(routeOutputSegments('/terms'), ['terms', 'index.html'])
  assert.deepEqual(routeOutputSegments('/privacy'), ['privacy', 'index.html'])
})

test('prerendering fails when a required SEO tag disappears from the template', () => {
  assert.throws(
    () => renderSeoHtml('<html><head><title>제목</title></head></html>', getSeoConfig('/faq')),
    /description tag was not found/,
  )
})
