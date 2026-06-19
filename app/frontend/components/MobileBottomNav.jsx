import { NavLink } from 'react-router-dom'

const tabs = [
  { to: '/', label: '홈' },
  { to: '/fridge', label: '냉장고' },
  { to: '/recipes', label: '레시피' },
  { to: '/recipe-recommend', label: '장보기' },
  { to: '/guide', label: '마이' },
]

function MobileBottomNav() {
  return (
    <nav className="mobile-bottom-nav" aria-label="모바일 하단 메뉴">
      {tabs.map((tab) => (
        <NavLink
          className={({ isActive }) =>
            isActive ? 'mobile-bottom-nav__item active' : 'mobile-bottom-nav__item'
          }
          key={tab.label}
          to={tab.to}
        >
          <span aria-hidden="true" />
          {tab.label}
        </NavLink>
      ))}
    </nav>
  )
}

export default MobileBottomNav
