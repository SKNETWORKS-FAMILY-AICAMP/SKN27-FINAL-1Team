import React from 'react'
import { Link, useNavigate } from 'react-router-dom'
import logoText from '../../assets/logo_text_extracted.png'
import imageHello from '../../assets/extracted/images/image_hello.png'
import iconReceipt from '../../assets/extracted/icons/icon_receipt.png'
import iconFridge from '../../assets/extracted/icons/icon_refrigerator.png'
import iconBasket from '../../assets/extracted/icons/icon_basket.png'
import './Login.css'

const loginMethods = [
  { label: '카카오로 로그인', mark: '●', className: 'kakao' },
  { label: '네이버로 로그인', mark: 'N', className: 'naver' },
  { label: '구글로 로그인', mark: 'G', className: 'google' },
]

const featureCards = [
  {
    title: '냉장고 재료로',
    description: '똑똑한 요리',
    image: iconFridge,
  },
  {
    title: '식재료 낭비 줄이고',
    description: '알뜰하게',
    image: iconReceipt,
  },
  {
    title: '매일 맛있는',
    description: '식탁 완성',
    image: iconBasket,
  },
]

function Login() {
  const navigate = useNavigate()

  const handleGuestStart = () => {
    window.localStorage.setItem('bobbeori-auth-mode', 'guest')
    window.dispatchEvent(new Event('bobbeori-auth-change'))
    navigate('/')
  }

  return (
    <section className="login-page" aria-labelledby="login-title">
      <div className="login-browser">
        <Link className="login-back-link" to="/">
          <span aria-hidden="true" />
          돌아가기
        </Link>

        <div className="login-card">
          <div className="login-card__visual" aria-label="밥벌이 로그인 소개">
            <img className="login-card__brand-logo" src={logoText} alt="밥벌이" />

            <div className="login-card__copy">
              <p className="login-card__eyebrow">맛있는 한 끼,</p>
              <h1>
                <strong>밥벌이와 함께해요!</strong>
              </h1>
              <p className="login-card__description">
                냉장고 재료로 오늘의 한 끼를 쉽게 만들고,
                <br />
                식재료 낭비는 줄이고, 맛있는 일상은 더해요.
              </p>
            </div>

            <div className="login-card__art-wrap">
              <img className="login-card__art" src={imageHello} alt="" />
            </div>

            <div className="login-card__features">
              {featureCards.map((feature) => (
                <div className="login-card__feature" key={feature.title}>
                  <img src={feature.image} alt="" />
                  <div>
                    <strong>{feature.title}</strong>
                    <span>{feature.description}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="login-card__form-wrap">
            <div className="login-card__form" aria-label="소셜 로그인">
              <h2 id="login-title">환영해요!</h2>
              <p className="login-card__helper">간편 로그인으로 밥벌이의 모든 서비스를 이용해보세요.</p>

              <div className="login-card__buttons">
                {loginMethods.map((method) => (
                  <button
                    className={`login-card__button ${method.className}`}
                    type="button"
                    key={method.label}
                  >
                    <span className={`login-card__provider ${method.className}`}>
                      {method.mark}
                    </span>
                    {method.label.replace('로그인', '시작하기')}
                  </button>
                ))}
              </div>

              <button className="login-card__guest-button" type="button" onClick={handleGuestStart}>
                게스트로 사용하기
              </button>

              <p className="login-card__terms">
                로그인하면 밥벌이의 <a href="/terms">이용약관</a> 및{' '}
                <a href="/privacy-policy">개인정보 처리방침</a>에 동의한 것으로 간주됩니다.
              </p>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

export default Login
