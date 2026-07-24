import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { INDEXABLE_PATHS, SITE_ORIGIN } from './seo.js'

const publicDirectory = new URL('../public/', import.meta.url)

test('sitemap contains exactly the approved canonical public URLs', () => {
  const sitemap = readFileSync(new URL('sitemap.xml', publicDirectory), 'utf8')
  const sitemapUrls = [...sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].map((match) => match[1])
  const expectedUrls = INDEXABLE_PATHS.map(
    (pathname) => `${SITE_ORIGIN}${pathname === '/' ? '/' : pathname}`,
  )

  assert.match(sitemap, /^<\?xml version="1\.0" encoding="UTF-8"\?>/)
  assert.match(sitemap, /<urlset xmlns="http:\/\/www\.sitemaps\.org\/schemas\/sitemap\/0\.9">/)
  assert.deepEqual(sitemapUrls, expectedUrls)
})

test('robots.txt allows crawling and advertises the production sitemap', () => {
  const robots = readFileSync(new URL('robots.txt', publicDirectory), 'utf8')

  assert.match(robots, /^User-agent: \*\r?\nAllow: \//)
  assert.match(robots, /Sitemap: https:\/\/www\.bobbeori\.com\/sitemap\.xml/)
})
