import React, { useEffect, useState } from 'react'
import { Link, NavLink, useLocation } from 'react-router-dom'
import logoText from '../assets/logo_text_extracted.png'
import './Header.css'

const navItems = [
  { to: '/fridge', label: '냉장고' },
  { to: '/receipt-ocr', label: '영수증 등록' },
]

const recipeItems = [
  { to: '/recipes', label: '레시피 목록' },
  { to: '/recipe-fridge', label: '냉장고 파먹기' },
  { to: '/menu-recommend', label: '메뉴 추천' },
]

function Header() {
  const { pathname } = useLocation()
  const isRecipeActive = recipeItems.some((item) => item.to === pathname)
  const [authMode, setAuthMode] = useState(() => {
    if (typeof window === 'undefined') {
      return null
    }

    return window.localStorage.getItem('bobbeori-auth-mode')
  })
  const isGuest = authMode === 'guest'

  useEffect(() => {
    const syncAuthMode = () => {
      setAuthMode(window.localStorage.getItem('bobbeori-auth-mode'))
    }

    window.addEventListener('storage', syncAuthMode)
    window.addEventListener('bobbeori-auth-change', syncAuthMode)

    return () => {
      window.removeEventListener('storage', syncAuthMode)
      window.removeEventListener('bobbeori-auth-change', syncAuthMode)
    }
  }, [])

  return (
    <header className="site-header" aria-label="밥벌이 주요 메뉴">
      <div className="site-header__inner">
        <button className="site-header__mobile-icon" type="button" aria-label="메뉴 열기">
          <span />
        </button>
        <Link
          to="/"
          className="site-header__brand"
          aria-label="밥벌이 홈"
        >
          <img className="site-header__logo-text" src={logoText} alt="밥벌이" />
        </Link>

        <nav className="site-header__nav" aria-label="주요 메뉴">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                isActive ? 'site-header__nav-link active' : 'site-header__nav-link'
              }
            >
              {item.label}
            </NavLink>
          ))}

          <div className="site-header__dropdown">
            <button
              className={
                isRecipeActive
                  ? 'site-header__nav-link site-header__dropdown-trigger active'
                  : 'site-header__nav-link site-header__dropdown-trigger'
              }
              type="button"
              aria-haspopup="menu"
            >
              레시피
            </button>
            <div className="site-header__dropdown-menu" role="menu">
              {recipeItems.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    isActive
                      ? 'site-header__dropdown-link active'
                      : 'site-header__dropdown-link'
                  }
                  role="menuitem"
                >
                  {item.label}
                </NavLink>
              ))}
            </div>
          </div>

          <NavLink
            to="/guide"
            className={({ isActive }) =>
              isActive ? 'site-header__nav-link active' : 'site-header__nav-link'
            }
          >
            가이드
          </NavLink>

          <NavLink
            to="/shopping-list"
            className={({ isActive }) =>
              isActive ? 'site-header__nav-link active' : 'site-header__nav-link'
            }
          >
            장보기
          </NavLink>
        </nav>

        <div className="site-header__actions">
          <label className="site-header__search">
            <span className="site-header__sr-only">재료명 또는 레시피 검색</span>
            <input type="search" placeholder="재료명, 레시피 검색" />
          </label>
          <Link className="site-header__start" to={isGuest ? '/mypage' : '/login'}>
            {isGuest ? '마이페이지' : '로그인'}
          </Link>
        </div>
        <button className="site-header__mobile-bell" type="button" aria-label="알림 보기" />
      </div>
    </header>
  )
}

export default Header
