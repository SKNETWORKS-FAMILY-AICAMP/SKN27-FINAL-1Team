import React from 'react'
import { Link, useLocation } from 'react-router-dom'
import './Breadcrumbs.css'

const breadcrumbMap = {
  '/fridge': [{ label: '홈', to: '/' }, { label: '냉장고' }],
  '/receipt-ocr': [{ label: '홈', to: '/' }, { label: '영수증 등록' }],
  '/recipes': [{ label: '홈', to: '/' }, { label: '레시피' }, { label: '레시피 목록' }],
  '/recipe-fridge': [{ label: '홈', to: '/' }, { label: '레시피' }, { label: '냉장고 파먹기' }],
  '/menu-recommend': [{ label: '홈', to: '/' }, { label: '레시피' }, { label: '메뉴 추천' }],
  '/recipe-recommend': [{ label: '홈', to: '/' }, { label: '레시피' }, { label: '레시피 추천' }],
  '/login': [{ label: '홈', to: '/' }, { label: '로그인' }],
  '/mypage': [{ label: '홈', to: '/' }, { label: '마이페이지' }],
  '/guide': [{ label: '홈', to: '/' }, { label: '보관 가이드' }],
  '/shopping-list': [{ label: '홈', to: '/' }, { label: '장보기' }],
  '/faq': [{ label: '홈', to: '/' }, { label: '고객 서비스' }, { label: '자주 묻는 질문' }],
  '/support': [{ label: '홈', to: '/' }, { label: '고객 서비스' }, { label: '고객 지원' }],
  '/refund-policy': [{ label: '홈', to: '/' }, { label: '고객 서비스' }, { label: '반품 및 환불 정책' }],
  '/terms': [{ label: '홈', to: '/' }, { label: '정책 및 안내' }, { label: '이용약관' }],
  '/privacy': [{ label: '홈', to: '/' }, { label: '정책 및 안내' }, { label: '개인정보처리방침' }],
}

function Breadcrumbs() {
  const { pathname, search } = useLocation()

  if (pathname === '/') {
    return null
  }

  const mypageTab = new URLSearchParams(search).get('tab')
  const mypageTabLabels = {
    saved: '저장된 레시피',
    alerts: '알림 및 캘린더',
  }

  const items = pathname === '/mypage'
    ? [
        { label: '홈', to: '/' },
        { label: '마이페이지', to: mypageTabLabels[mypageTab] ? '/mypage' : undefined },
        { label: mypageTabLabels[mypageTab] || '내 정보' },
      ]
    : pathname.startsWith('/guide/') && pathname !== '/guide'
    ? [
        { label: '홈', to: '/' },
        { label: '보관 가이드', to: '/guide' },
        { label: '식재료가이드' },
      ]
    : pathname.startsWith('/recipes/') && pathname !== '/recipes'
      ? [
          { label: '홈', to: '/' },
          { label: '레시피', to: '/recipes' },
          { label: '레시피 상세' },
        ]
      : breadcrumbMap[pathname] ?? [{ label: '홈', to: '/' }]

  return (
    <nav className="breadcrumbs" aria-label="현재 위치">
      <ol className="breadcrumbs__list">
        {items.map((item, index) => {
          const isLast = index === items.length - 1

          return (
            <li className="breadcrumbs__item" key={`${item.label}-${index}`}>
              {item.to && !isLast ? (
                <Link className="breadcrumbs__link" to={item.to}>
                  {item.label}
                </Link>
              ) : (
                <span className="breadcrumbs__current" aria-current={isLast ? 'page' : undefined}>
                  {item.label}
                </span>
              )}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}

export default Breadcrumbs
