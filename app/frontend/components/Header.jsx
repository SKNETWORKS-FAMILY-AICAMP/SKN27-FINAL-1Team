import React, { useEffect, useState } from 'react'
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom'
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

function getAuthMode() {
  if (typeof window === 'undefined') {
    return null
  }

  const token = window.localStorage.getItem('bobbeori-token')
  const mode = window.localStorage.getItem('bobbeori-auth-mode')
  return token ? 'user' : mode
}

function Header() {
  const location = useLocation()
  const { pathname } = location
  const navigate = useNavigate()
  const isRecipeActive = recipeItems.some((item) => item.to === pathname) || pathname.startsWith('/recipes/')
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false)
  const [searchTerm, setSearchTerm] = useState('')
  const [authMode, setAuthMode] = useState(getAuthMode)
  const isLoggedIn = authMode === 'user' || authMode === 'guest'

  const closeMobileMenu = () => {
    setIsMobileMenuOpen(false)
  }

  const handleSearchSubmit = (event) => {
    event.preventDefault()
    const query = searchTerm.trim()

    if (pathname.startsWith('/recipes')) {
      const params = new URLSearchParams(location.search)
      if (query) {
        params.set('query', query)
      } else {
        params.delete('query')
      }
      params.delete('browse')
      const search = params.toString()
      navigate(search ? `/recipes?${search}` : '/recipes')
    } else {
      navigate(query ? `/recipes?query=${encodeURIComponent(query)}` : '/recipes')
    }
    closeMobileMenu()
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
          <form className="site-header__search" aria-label="재료명 또는 레시피 검색" onSubmit={handleSearchSubmit}>
            <span className="site-header__sr-only">재료명 또는 레시피 검색</span>
            <input
              type="search"
              placeholder="재료명, 레시피 검색"
              value={searchTerm}
              onChange={(event) => setSearchTerm(event.target.value)}
            />
          </form>
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
