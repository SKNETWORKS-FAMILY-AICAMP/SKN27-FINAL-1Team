import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { INDEXABLE_PATHS, SITE_ORIGIN } from './seo.js'

const publicDirectory = new URL('../public/', import.meta.url)
const indexHtml = readFileSync(new URL('../index.html', import.meta.url), 'utf8')

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

test('home page declares the stable, square favicon', () => {
  const favicon = readFileSync(new URL('favicon.png', publicDirectory))
  const pngSignature = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])
  const width = favicon.readUInt32BE(16)
  const height = favicon.readUInt32BE(20)

  assert.deepEqual(favicon.subarray(0, 8), pngSignature)
  assert.equal(width, height)
  assert.ok(width > 48)
  assert.match(
    indexHtml,
    /<link rel="icon" type="image\/png" sizes="128x128" href="\/favicon\.png" \/>/,
  )
})
