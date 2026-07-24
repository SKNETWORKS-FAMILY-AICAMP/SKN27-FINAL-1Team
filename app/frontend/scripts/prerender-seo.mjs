import { mkdir, readFile, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { INDEXABLE_PATHS, getSeoConfig } from '../utils/seo.js'
import { renderSeoHtml, routeOutputSegments } from './prerender-seo-lib.mjs'

const frontendDirectory = fileURLToPath(new URL('../', import.meta.url))
const distDirectory = path.resolve(frontendDirectory, 'dist')
const templatePath = path.join(distDirectory, 'index.html')
const template = await readFile(templatePath, 'utf8')

for (const pathname of INDEXABLE_PATHS) {
  const config = getSeoConfig(pathname)
  const outputPath = path.join(distDirectory, ...routeOutputSegments(pathname))

  await mkdir(path.dirname(outputPath), { recursive: true })
  await writeFile(outputPath, renderSeoHtml(template, config), 'utf8')
  console.log(`Prerendered SEO HTML: ${pathname} -> ${path.relative(frontendDirectory, outputPath)}`)
}

