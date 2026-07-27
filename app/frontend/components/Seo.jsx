import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { DEFAULT_OG_IMAGE, SITE_ORIGIN, getSeoConfig } from '../utils/seo.js'

function setMeta(attribute, key, content) {
  let element = document.head.querySelector(`meta[${attribute}="${key}"]`)

  if (!element) {
    element = document.createElement('meta')
    element.setAttribute(attribute, key)
    document.head.appendChild(element)
  }

  element.setAttribute('content', content)
}

function setCanonical(href) {
  const existing = document.head.querySelector('link[rel="canonical"]')

  if (!href) {
    existing?.remove()
    return
  }

  const element = existing ?? document.createElement('link')
  element.setAttribute('rel', 'canonical')
  element.setAttribute('href', href)

  if (!existing) {
    document.head.appendChild(element)
  }
}

function applySeoConfig(config) {
  const pageUrl = `${SITE_ORIGIN}${config.pathname === '/' ? '/' : config.pathname}`

  document.title = config.title
  setMeta('name', 'description', config.description)
  setMeta('name', 'robots', config.robots)
  setCanonical(config.canonical)

  setMeta('property', 'og:type', 'website')
  setMeta('property', 'og:site_name', '밥벌이')
  setMeta('property', 'og:title', config.title)
  setMeta('property', 'og:description', config.description)
  setMeta('property', 'og:url', pageUrl)
  setMeta('property', 'og:image', DEFAULT_OG_IMAGE)
  setMeta('property', 'og:image:alt', '밥벌이 AI 기반 식재료 관리 서비스')

  setMeta('name', 'twitter:card', 'summary_large_image')
  setMeta('name', 'twitter:title', config.title)
  setMeta('name', 'twitter:description', config.description)
  setMeta('name', 'twitter:image', DEFAULT_OG_IMAGE)
}

function Seo() {
  const { pathname } = useLocation()

  useEffect(() => {
    applySeoConfig(getSeoConfig(pathname))
  }, [pathname])

  return null
}

export default Seo

