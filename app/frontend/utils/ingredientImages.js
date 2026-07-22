import { useEffect, useState } from 'react'
import { API_URL } from './api.js'

export const INGREDIENT_IMAGE_MANIFEST_URL =
  `${API_URL}/api/v1/guide/images/manifest`

const CATEGORY_ALIASES = {
  가공식품: '가공식품·음료',
  가공식품류: '가공식품·음료',
  기타가공식품: '가공식품·음료',
  발효식품: '가공식품·음료',
  '음료·당류': '가공식품·음료',
  곡류: '곡류·면·빵',
  '곡류·두류·견과류': '곡류·면·빵',
  '면·떡·빵류': '곡류·면·빵',
  과일류: '과일',
  농산물: '채소',
  버섯류: '채소',
  채소류: '채소',
  '향신·허브·약재류': '채소',
  유제품: '유제품·달걀',
  '달걀·유제품': '유제품·달걀',
  축산물: '육류',
  소고기: '육류',
  돼지고기: '육류',
  '닭·오리고기': '육류',
  육가공품: '육류',
  '부산물·뼈류': '육류',
  기타축산물: '육류',
  생선류: '수산물',
  조개류: '수산물',
  갑각류: '수산물',
  '오징어·문어류': '수산물',
  해조류: '수산물',
  수산가공품: '수산물',
  기타수산물: '수산물',
  조미료: '조미료·소스',
  '소스·양념류': '조미료·소스',
  '장류·절임류': '조미료·소스',
  유지류: '조미료·소스',
  두류: '콩·견과·묵',
  견과류: '콩·견과·묵',
  묵류: '콩·견과·묵',
}

let catalogPromise

export function normalizeIngredientImageName(value = '') {
  return String(value).replace(/\s/g, '').toLowerCase()
}

function registerFirst(map, value, item) {
  const key = normalizeIngredientImageName(value)
  if (key && !map.has(key)) map.set(key, item)
}

export function createIngredientImageCatalog(manifest = {}) {
  const items = Array.isArray(manifest.items)
    ? manifest.items.filter((item) => item?.name && item?.imageUrl)
    : []
  const fallbacks = Array.isArray(manifest.fallbacks)
    ? manifest.fallbacks.filter((item) => item?.category && item?.imageUrl)
    : []
  const names = new Map()
  const aliases = new Map()
  const fallbacksByCategory = new Map()

  for (const item of items) {
    registerFirst(names, item.name, item)
    for (const alias of item.aliases || []) registerFirst(aliases, alias, item)
  }
  for (const fallback of fallbacks) registerFirst(fallbacksByCategory, fallback.category, fallback)

  return {
    items,
    names,
    aliases,
    fallbacksByCategory,
    otherFallback: fallbacksByCategory.get(normalizeIngredientImageName('기타')),
  }
}

export function loadIngredientImageCatalog() {
  if (!catalogPromise) {
    catalogPromise = fetch(INGREDIENT_IMAGE_MANIFEST_URL)
      .then((response) => {
        if (!response.ok) throw new Error(`식재료 이미지 매니페스트 요청 실패: ${response.status}`)
        return response.json()
      })
      .then(createIngredientImageCatalog)
      .catch((error) => {
        catalogPromise = null
        throw error
      })
  }
  return catalogPromise
}

export function useIngredientImageCatalog() {
  const [catalog, setCatalog] = useState(null)

  useEffect(() => {
    let active = true
    loadIngredientImageCatalog()
      .then((loadedCatalog) => {
        if (active) setCatalog(loadedCatalog)
      })
      .catch(() => {})
    return () => {
      active = false
    }
  }, [])

  return catalog
}

function candidateKeys(values) {
  const candidates = (Array.isArray(values) ? values : [values]).flatMap((value) => {
    const text = String(value || '')
    return [text, ...text.split(/[,/|;·]/)]
  })
  return [...new Set(candidates.map(normalizeIngredientImageName).filter(Boolean))]
}

function categoryKeys(values) {
  return (Array.isArray(values) ? values : [values])
    .map(normalizeIngredientImageName)
    .filter(Boolean)
}

export function getIngredientImageUrl(catalog, names, categories = []) {
  if (!catalog) return ''

  const keys = candidateKeys(names)
  for (const key of keys) {
    const item = catalog.names.get(key)
    if (item) return item.imageUrl
  }
  for (const key of keys) {
    const item = catalog.aliases.get(key)
    if (item) return item.imageUrl
  }

  for (const key of categoryKeys(categories)) {
    const category = CATEGORY_ALIASES[key] || key
    const fallback = catalog.fallbacksByCategory.get(normalizeIngredientImageName(category))
    if (fallback) return fallback.imageUrl
  }
  return catalog.otherFallback?.imageUrl || ''
}

export function searchIngredientImages(catalog, keyword, limit = 6) {
  const key = normalizeIngredientImageName(keyword)
  if (!catalog || !key) return []

  const rank = (item) => {
    const name = normalizeIngredientImageName(item.name)
    const aliases = (item.aliases || []).map(normalizeIngredientImageName)
    if (name === key) return 0
    if (aliases.includes(key)) return 1
    if (name.startsWith(key)) return 2
    if (aliases.some((alias) => alias.startsWith(key))) return 3
    return 4
  }

  return catalog.items
    .filter((item) => [item.name, ...(item.aliases || [])]
      .some((value) => normalizeIngredientImageName(value).includes(key)))
    .map((item, index) => ({ item, index }))
    .sort((a, b) => rank(a.item) - rank(b.item) || a.index - b.index)
    .slice(0, limit)
    .map(({ item }) => item)
}
