import React, { useEffect, useState } from 'react'
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom'
import appIcon from '../assets/app_icon.png'
import logoText from '../assets/logo_text_extracted.png'
import './Header.css'

const APP_STORE_URL = 'https://play.google.com/store/apps/details?id=com.bobbeori.bobbeori_app'

const navItems = [
  { to: '/fridge', label: '냉장고' },
  { to: '/receipt-ocr', label: '영수증 등록' },
]

const recipeItems = [
  { to: '/recipes', label: '레시피 목록' },
  { to: '/recipe-fridge', label: '냉장고 파먹기' },
  { to: '/menu-recommend', label: '메뉴 추천' },
]

function getAuthMode() {
  if (typeof window === 'undefined') {
    return null
  }

  const token = window.localStorage.getItem('bobbeori-token')
  const mode = window.localStorage.getItem('bobbeori-auth-mode')
  return token ? 'user' : mode
}

function Header() {
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const isRecipeActive = recipeItems.some((item) => item.to === pathname) || pathname.startsWith('/recipes/')
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false)
  const [authMode, setAuthMode] = useState(getAuthMode)
  const isLoggedIn = authMode === 'user'

  const closeMobileMenu = () => {
    setIsMobileMenuOpen(false)
  }

  useEffect(() => {
    const syncAuthMode = () => {
      setAuthMode(getAuthMode())
    }

    window.addEventListener('storage', syncAuthMode)
    window.addEventListener('bobbeori-auth-change', syncAuthMode)

    return () => {
      window.removeEventListener('storage', syncAuthMode)
      window.removeEventListener('bobbeori-auth-change', syncAuthMode)
    }
  }, [])

  useEffect(() => {
    closeMobileMenu()
  }, [pathname])

  return (
    <header className="site-header" aria-label="밥벌이 주요 메뉴">
      <a
        className="site-header__app-banner"
        href={APP_STORE_URL}
        target="_blank"
        rel="noreferrer"
        aria-label="Google Play에서 밥벌이 앱 다운로드하기"
      >
        <img src={appIcon} alt="" />
        <span>밥벌이 앱 다운로드하고 냉장고 관리를 더 편하게 시작해보세요!</span>
      </a>
      <div className="site-header__inner">
        <button
          className="site-header__mobile-icon"
          type="button"
          aria-label={isMobileMenuOpen ? '메뉴 닫기' : '메뉴 열기'}
          aria-expanded={isMobileMenuOpen}
          onClick={() => setIsMobileMenuOpen((prev) => !prev)}
        >
          <span />
        </button>
        <Link to="/" className="site-header__brand" aria-label="밥벌이 홈">
          <img className="site-header__logo-text" src={logoText} alt="밥벌이" />
        </Link>

        <nav
          className={isMobileMenuOpen ? 'site-header__nav is-mobile-open' : 'site-header__nav'}
          aria-label="주요 메뉴"
        >
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                isActive ? 'site-header__nav-link active' : 'site-header__nav-link'
              }
              onClick={closeMobileMenu}
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
              onClick={() => navigate('/recipes')}
            >
              레시피
            </button>
            <div className="site-header__dropdown-menu" role="menu">
              {recipeItems.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={({ isActive }) =>
                    isActive ? 'site-header__dropdown-link active' : 'site-header__dropdown-link'
                  }
                  role="menuitem"
                  onClick={closeMobileMenu}
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
            onClick={closeMobileMenu}
          >
            가이드
          </NavLink>

          <NavLink
            to="/shopping-list"
            className={({ isActive }) =>
              isActive ? 'site-header__nav-link active' : 'site-header__nav-link'
            }
            onClick={closeMobileMenu}
          >
            장보기
          </NavLink>
        </nav>

        <div className="site-header__actions">
          <Link className="site-header__start" to={isLoggedIn ? '/mypage' : '/login'}>
            {isLoggedIn ? '마이페이지' : '로그인'}
          </Link>
        </div>
        <button
          className="site-header__mobile-bell"
          type="button"
          aria-label="알림 보기"
          onClick={() => navigate('/mypage')}
        />
      </div>
    </header>
  )
}

export default Header
