import React from 'react'
import { Link } from 'react-router-dom'
import './Footer.css'

const customerServiceLinks = [
  { to: '/faq', label: '자주 묻는 질문(FAQ)' },
  { to: '/support', label: '고객 지원/고객 센터' },
]

const utilityLinks = [
  { href: 'mailto:bobbeori@bobbeori.com', label: '연락처' },
  { to: '/terms', label: '이용약관' },
  { to: '/privacy', label: '개인정보처리방침' },
]

function FooterLink({ item }) {
  if (item.href) {
    return <a href={item.href}>{item.label}</a>
  }

  return <Link to={item.to}>{item.label}</Link>
}

function Footer() {
  return (
    <footer className="site-footer" aria-label="밥벌이 하단 정보">
      <div className="site-footer__inner">
        <section className="site-footer__brand" aria-labelledby="footer-brand-title">
          <Link to="/" className="site-footer__logo" id="footer-brand-title" aria-label="밥벌이 홈">
            밥벌이
          </Link>
          <p>
            냉장고 속 남은 재료와 소비기한을 기준으로 오늘 먹기 좋은 메뉴를 추천하고,
            부족한 재료는 장보기까지 이어주는 식재료 절약 서비스입니다.
          </p>
          <a className="site-footer__mail" href="mailto:bobbeori@bobbeori.com">
            bobbeori@bobbeori.com
          </a>
        </section>

        <div className="site-footer__menus">
          <nav className="site-footer__group" aria-labelledby="footer-customer-title">
            <h2 id="footer-customer-title">고객 서비스</h2>
            <div className="site-footer__links">
              {customerServiceLinks.map((link) => (
                <FooterLink key={link.to} item={link} />
              ))}
            </div>
          </nav>

          <nav className="site-footer__group" aria-labelledby="footer-policy-title">
            <h2 id="footer-policy-title">정책 및 안내</h2>
            <div className="site-footer__links site-footer__links--utility">
              {utilityLinks.map((link) => (
                <FooterLink key={link.to ?? link.href} item={link} />
              ))}
            </div>
          </nav>
        </div>
      </div>

      <div className="site-footer__bottom">
        <span>© 2026 Babbeori. All rights reserved.</span>
      </div>
    </footer>
  )
}

export default Footer
