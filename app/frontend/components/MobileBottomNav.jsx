import React from 'react'
import { NavLink } from 'react-router-dom'

const tabs = [
  { to: '/fridge', label: '냉장고', icon: 'fridge' },
  { to: '/receipt-ocr', label: '영수증', icon: 'receipt' },
  { to: '/recipes', label: '레시피', icon: 'recipe' },
  { to: '/shopping-list', label: '장보기', icon: 'cart' },
  { to: '/guide', label: '가이드', icon: 'guide' },
]

function MobileNavIcon({ name }) {
  const paths = {
    fridge: <><rect x="5.2" y="2.8" width="13.6" height="18.4" rx="2.2" /><path d="M5.2 10.2h13.6M8.3 6.2v1.5M8.3 13.3v2.2" /></>,
    receipt: <><path d="M7 3.5h10v17l-2-1.2-2 1.2-2-1.2-2 1.2-2-1.2V3.5Z" /><path d="M9.5 7.5h5M9.5 10.8h5M9.5 14.1h3.2" /></>,
    recipe: <><path d="M6 3.5h10.2A1.8 1.8 0 0 1 18 5.3v15.2H7.8A1.8 1.8 0 0 1 6 18.7V3.5Z" /><path d="M6 17.2h9.4M9.2 7.2h5.6M9.2 10.5h5.6" /></>,
    cart: <><path d="M3 4.5h2l1.9 9.1h9.8l2.1-6.2H6" /><circle cx="9" cy="18.5" r="1.2" /><circle cx="16" cy="18.5" r="1.2" /></>,
    guide: <><path d="M5.5 4.5h9.2A3.8 3.8 0 0 1 18.5 8.3v11.2H8.2a2.7 2.7 0 0 1-2.7-2.7V4.5Z" /><path d="M8.5 8h6M8.5 11.2h6M8.5 14.4h4.2" /></>,
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
