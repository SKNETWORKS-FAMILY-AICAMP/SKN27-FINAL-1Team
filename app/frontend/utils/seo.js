export const SITE_ORIGIN = 'https://www.bobbeori.com'
export const DEFAULT_OG_IMAGE = `${SITE_ORIGIN}/og-image.png`

const DEFAULT_DESCRIPTION =
  '밥벌이는 냉장고 재료 관리, 영수증 OCR, 레시피 추천, 장보기 목록, Google Calendar 알림 연동을 제공하는 AI 기반 식재료 관리 서비스입니다.'

export const INDEXABLE_ROUTE_SEO = Object.freeze({
  '/': {
    title: '밥벌이 | AI 기반 식재료 관리 서비스',
    description: DEFAULT_DESCRIPTION,
  },
  '/faq': {
    title: '자주 묻는 질문 | 밥벌이',
    description:
      '밥벌이의 냉장고 관리, 영수증 OCR, 레시피 추천, 장보기 목록 및 서비스 이용에 관한 자주 묻는 질문을 확인하세요.',
  },
  '/terms': {
    title: '이용약관 | 밥벌이',
    description: '밥벌이 서비스 이용 조건과 회원의 권리·의무를 안내하는 이용약관입니다.',
  },
  '/privacy': {
    title: '개인정보처리방침 | 밥벌이',
    description: '밥벌이의 개인정보 수집, 이용, 보관, 파기 및 이용자 권리 처리 기준을 안내합니다.',
  },
})

const NOINDEX_ROUTE_TITLES = Object.freeze({
  '/fridge': '내 냉장고 | 밥벌이',
  '/receipt-ocr': '영수증 등록 | 밥벌이',
  '/recipes': '레시피 | 밥벌이',
  '/guide': '식재료 가이드 | 밥벌이',
  '/recipe-fridge': '냉장고 레시피 | 밥벌이',
  '/recipe-recommend': '레시피 추천 | 밥벌이',
  '/login': '로그인 | 밥벌이',
  '/mypage': '마이페이지 | 밥벌이',
  '/shopping-list': '장보기 목록 | 밥벌이',
  '/support': '고객 지원 | 밥벌이',
  '/refund-policy': '반품 및 환불 정책 | 밥벌이',
  '/privacy-policy': '개인정보처리방침 | 밥벌이',
})

export const INDEXABLE_PATHS = Object.freeze(Object.keys(INDEXABLE_ROUTE_SEO))

export function normalizePathname(pathname = '/') {
  if (!pathname || pathname === '/') return '/'
  return `/${pathname.split('/').filter(Boolean).join('/')}`
}

function getNoindexTitle(pathname) {
  if (NOINDEX_ROUTE_TITLES[pathname]) return NOINDEX_ROUTE_TITLES[pathname]
  if (pathname.startsWith('/recipes/')) return '레시피 상세 | 밥벌이'
  if (pathname.startsWith('/guide/')) return '식재료 가이드 | 밥벌이'
  if (pathname.startsWith('/auth/callback/')) return '로그인 처리 중 | 밥벌이'
  return '페이지를 찾을 수 없습니다 | 밥벌이'
}

export function getSeoConfig(pathname) {
  const normalizedPath = normalizePathname(pathname)
  const indexableConfig = INDEXABLE_ROUTE_SEO[normalizedPath]

  if (indexableConfig) {
    return {
      ...indexableConfig,
      pathname: normalizedPath,
      canonical: `${SITE_ORIGIN}${normalizedPath === '/' ? '/' : normalizedPath}`,
      robots: 'index, follow',
      indexable: true,
    }
  }

  const isAuthCallback = normalizedPath.startsWith('/auth/callback/')

  return {
    title: getNoindexTitle(normalizedPath),
    description: DEFAULT_DESCRIPTION,
    pathname: normalizedPath,
    canonical: null,
    robots: isAuthCallback ? 'noindex, nofollow' : 'noindex, follow',
    indexable: false,
  }
}

