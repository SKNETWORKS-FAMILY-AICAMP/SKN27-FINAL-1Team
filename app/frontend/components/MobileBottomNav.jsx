import { NavLink } from 'react-router-dom'

const tabs = [
  { to: '/', label: '홈', icon: 'home' },
  { to: '/fridge', label: '냉장고', icon: 'fridge' },
  { to: '/recipes', label: '레시피', icon: 'recipe' },
  { to: '/shopping-list', label: '장보기', icon: 'cart' },
  { to: '/mypage', label: '마이', icon: 'user' },
]

function MobileNavIcon({ name }) {
  const paths = {
    home: <><path d="M3.5 10.5 12 3.8l8.5 6.7" /><path d="M5.8 9.2v10.2h12.4V9.2M9.5 19.4v-5.8h5v5.8" /></>,
    fridge: <><rect x="5.2" y="2.8" width="13.6" height="18.4" rx="2.2" /><path d="M5.2 10.2h13.6M8.3 6.2v1.5M8.3 13.3v2.2" /></>,
    recipe: <><path d="M6 3.5h10.2A1.8 1.8 0 0 1 18 5.3v15.2H7.8A1.8 1.8 0 0 1 6 18.7V3.5Z" /><path d="M6 17.2h9.4M9.2 7.2h5.6M9.2 10.5h5.6" /></>,
    cart: <><path d="M3 4.5h2l1.9 9.1h9.8l2.1-6.2H6" /><circle cx="9" cy="18.5" r="1.2" /><circle cx="16" cy="18.5" r="1.2" /></>,
    user: <><circle cx="12" cy="7.5" r="3.4" /><path d="M5.2 20c.5-4 3-6.1 6.8-6.1s6.3 2.1 6.8 6.1" /></>,
  }

  return <svg viewBox="0 0 24 24">{paths[name]}</svg>
}

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
          <span className="mobile-bottom-nav__icon" aria-hidden="true">
            <MobileNavIcon name={tab.icon} />
          </span>
          {tab.label}
        </NavLink>
      ))}
    </nav>
  )
}

export default MobileBottomNav
