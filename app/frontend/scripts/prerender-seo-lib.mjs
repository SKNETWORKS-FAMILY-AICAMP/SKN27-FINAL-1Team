function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('"', '&quot;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
}

function replaceRequired(html, pattern, replacement, label) {
  if (!pattern.test(html)) {
    throw new Error(`Unable to prerender SEO metadata: ${label} tag was not found`)
  }

  return html.replace(pattern, replacement)
}

function metaTag(attribute, key, content) {
  return `<meta ${attribute}="${key}" content="${escapeHtml(content)}" />`
}

export function renderSeoHtml(template, config) {
  let html = template

  html = replaceRequired(
    html,
    /<title>[\s\S]*?<\/title>/i,
    `<title>${escapeHtml(config.title)}</title>`,
    'title',
  )
  html = replaceRequired(
    html,
    /<meta\s+[^>]*\bname=(["'])description\1[^>]*>/i,
    metaTag('name', 'description', config.description),
    'description',
  )
  html = replaceRequired(
    html,
    /<meta\s+[^>]*\bname=(["'])robots\1[^>]*>/i,
    metaTag('name', 'robots', config.robots),
    'robots',
  )
  html = replaceRequired(
    html,
    /<link\s+[^>]*\brel=(["'])canonical\1[^>]*>/i,
    `<link rel="canonical" href="${escapeHtml(config.canonical)}" />`,
    'canonical',
  )
  html = replaceRequired(
    html,
    /<meta\s+[^>]*\bproperty=(["'])og:title\1[^>]*>/i,
    metaTag('property', 'og:title', config.title),
    'og:title',
  )
  html = replaceRequired(
    html,
    /<meta\s+[^>]*\bproperty=(["'])og:description\1[^>]*>/i,
    metaTag('property', 'og:description', config.description),
    'og:description',
  )
  html = replaceRequired(
    html,
    /<meta\s+[^>]*\bproperty=(["'])og:url\1[^>]*>/i,
    metaTag('property', 'og:url', config.canonical),
    'og:url',
  )
  html = replaceRequired(
    html,
    /<meta\s+[^>]*\bname=(["'])twitter:title\1[^>]*>/i,
    metaTag('name', 'twitter:title', config.title),
    'twitter:title',
  )
  html = replaceRequired(
    html,
    /<meta\s+[^>]*\bname=(["'])twitter:description\1[^>]*>/i,
    metaTag('name', 'twitter:description', config.description),
    'twitter:description',
  )

  return html
}

export function routeOutputSegments(pathname) {
  if (pathname === '/') return ['index.html']
  return [...pathname.split('/').filter(Boolean), 'index.html']
}

