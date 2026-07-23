const measurementId = import.meta.env.VITE_GA_MEASUREMENT_ID?.trim()

export function initAnalytics() {
  if (!measurementId || typeof window === 'undefined' || window.gtag) return Boolean(measurementId)

  window.dataLayer = window.dataLayer || []
  window.gtag = function gtag() {
    window.dataLayer.push(arguments)
  }
  window.gtag('js', new Date())
  window.gtag('config', measurementId, { send_page_view: false })

  const script = document.createElement('script')
  script.async = true
  script.src = `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(measurementId)}`
  document.head.appendChild(script)
  return true
}

export function trackEvent(name, parameters = {}) {
  if (!initAnalytics()) return
  window.gtag('event', name, parameters)
}

export function trackPageView(path) {
  trackEvent('page_view', {
    page_path: path,
    page_location: window.location.href,
    page_title: document.title,
  })
}
