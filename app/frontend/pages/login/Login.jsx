import React from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import logoText from '../../assets/logo_text_extracted.png'
import imageHello from '../../assets/extracted/images/image_hello.png'
import iconReceipt from '../../assets/extracted/icons/icon_receipt.png'
import iconFridge from '../../assets/extracted/icons/icon_refrigerator.png'
import iconBasket from '../../assets/extracted/icons/icon_basket.png'
import './Login.css'

const loginMethods = [
  { label: '카카오로 로그인', mark: 'K', className: 'kakao', provider: 'kakao', envKey: 'VITE_KAKAO_CLIENT_ID' },
  { label: '네이버로 로그인', mark: 'N', className: 'naver', provider: 'naver', envKey: 'VITE_NAVER_CLIENT_ID' },
  { label: '구글로 로그인', mark: 'G', className: 'google', provider: 'google', envKey: 'VITE_GOOGLE_CLIENT_ID' },
]

const serviceFeatures = [
  { title: '냉장고 재료로', description: '똑똑한 요리', image: iconFridge },
  { title: '식재료 낭비 줄이고', description: '알뜰하게', image: iconReceipt },
  { title: '매일 맛있는', description: '식탁 완성', image: iconBasket },
]

const calendarFeatures = [
  { title: '소비기한 일정', description: '오늘 쓸 재료 알림', image: iconFridge },
  { title: '오늘의 메뉴', description: '추천 메뉴 등록', image: iconBasket },
  { title: '레시피 만료', description: '삭제 전 확인', image: iconReceipt },
]

// OAuth state 값을 매 요청마다 새로 만들어 콜백 검증에 사용합니다.
function createOAuthState(provider) {
  const randomValue = window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`
  return `bobbeori-${provider}-${randomValue}`
}

function Login() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const isCalendarMode = searchParams.get('calendar') === '1'
  const features = isCalendarMode ? calendarFeatures : serviceFeatures

  const startLocalSession = (mode) => {
    window.localStorage.setItem('bobbeori-auth-mode', mode)
    window.dispatchEvent(new Event('bobbeori-auth-change'))
    navigate('/')
  }

  const handleSocialLogin = (method) => {
    const clientId = import.meta.env[method.envKey] || ''

    if (!clientId) {
      window.alert(`${method.label} 설정이 필요합니다. 환경 변수 ${method.envKey}를 확인해주세요.`)
      return
    }

    const redirectUri = `${window.location.origin}/auth/callback/${method.provider}`
    const state = createOAuthState(method.provider)
    window.sessionStorage.setItem(`bobbeori-oauth-state-${method.provider}`, state)

    let baseUrl = ''
    const params = new URLSearchParams({
      client_id: clientId,
      redirect_uri: redirectUri,
      response_type: 'code',
      state,
    })

    if (method.provider === 'kakao') {
      baseUrl = 'https://kauth.kakao.com/oauth/authorize'
    } else if (method.provider === 'naver') {
      baseUrl = 'https://nid.naver.com/oauth2.0/authorize'
    } else if (method.provider === 'google') {
      baseUrl = 'https://accounts.google.com/o/oauth2/v2/auth'
      params.set('scope', 'openid profile email')
    }

    if (baseUrl) {
      window.location.href = `${baseUrl}?${params.toString()}`
    }
  }

  const handleCalendarLogin = () => {
    const token = window.localStorage.getItem('bobbeori-token')
    if (!token) {
      window.alert('캘린더 연동은 밥벌이 로그인 후 사용할 수 있어요.')
      return
    }

    const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID
    if (!clientId) {
      window.alert('VITE_GOOGLE_CLIENT_ID가 필요합니다.')
      return
    }

    const redirectUri = encodeURIComponent(`${window.location.origin}/auth/callback/google-calendar`)
    const scope = encodeURIComponent('openid profile email https://www.googleapis.com/auth/calendar.events')
    window.location.href =
      `https://accounts.google.com/o/oauth2/v2/auth?client_id=${clientId}` +
      `&redirect_uri=${redirectUri}` +
      '&response_type=code' +
      `&scope=${scope}` +
      '&access_type=offline' +
      '&prompt=consent'
  }

  return (
    <section className="login-page" aria-labelledby="login-title">
      <div className="login-browser">
        <Link className="login-back-link" to={isCalendarMode ? '/mypage' : '/'}>
          <span aria-hidden="true" />
          {isCalendarMode ? '마이페이지로' : '돌아가기'}
        </Link>

        <div className="login-card">
          <div className="login-card__visual" aria-label={isCalendarMode ? '캘린더 연동 소개' : '밥벌이 로그인 소개'}>
            <img className="login-card__brand-logo" src={logoText} alt="밥벌이" />

            <div className="login-card__copy">
              <p className="login-card__eyebrow">
                {isCalendarMode ? '캘린더에 필요한 알림만' : '맛있는 한 끼,'}
              </p>
              <h1>
                <strong>{isCalendarMode ? '깔끔하게 연결해요!' : '밥벌이와 함께해요!'}</strong>
              </h1>
              <p className="login-card__description">
                {isCalendarMode ? (
                  <>
                    소비기한, 오늘의 메뉴, 레시피 만료일만
                    <br />
                    Google Calendar에 등록할게요.
                  </>
                ) : (
                  <>
                    냉장고 재료로 오늘의 한 끼를 쉽게 만들고,
                    <br />
                    식재료 낭비는 줄이고, 맛있는 일상은 더해요.
                  </>
                )}
              </p>
            </div>

            <div className="login-card__art-wrap">
              <img className="login-card__art" src={imageHello} alt="" />
            </div>

            <div className="login-card__features">
              {features.map((feature) => (
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
            <div className={`login-card__form ${isCalendarMode ? 'is-calendar' : ''}`} aria-label={isCalendarMode ? '캘린더 연동' : '소셜 로그인'}>
              <h2 id="login-title">{isCalendarMode ? '캘린더를 연결할게요' : '환영해요!'}</h2>
              <p className="login-card__helper">
                {isCalendarMode
                  ? '밥벌이 알림을 Google Calendar에 등록하려면 캘린더 권한 연결이 필요해요.'
                  : '간편 로그인으로 밥벌이의 모든 서비스를 이용해보세요.'}
              </p>

              <div className="login-card__buttons">
                {isCalendarMode ? (
                  <button className="login-card__button calendar" type="button" onClick={handleCalendarLogin}>
                    <span className="login-card__provider google">G</span>
                    Google Calendar 연결
                  </button>
                ) : (
                  loginMethods.map((method) => (
                    <button
                      className={`login-card__button ${method.className}`}
                      type="button"
                      key={method.label}
                      onClick={() => handleSocialLogin(method)}
                    >
                      <span className={`login-card__provider ${method.className}`}>{method.mark}</span>
                      {method.label.replace('로그인', '시작하기')}
                    </button>
                  ))
                )}
              </div>

              {!isCalendarMode ? (
                <button className="login-card__guest-button" type="button" onClick={() => startLocalSession('guest')}>
                  게스트로 사용하기
                </button>
              ) : null}

              <p className="login-card__terms">
                {isCalendarMode ? (
                  '연결 후 캘린더에는 밥벌이 알림 일정만 등록됩니다.'
                ) : (
                  <>
                    로그인하면 밥벌이의 <a href="/terms">이용약관</a> 및{' '}
                    <a href="/privacy">개인정보 처리방침</a>에 동의한 것으로 간주합니다.
                  </>
                )}
              </p>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

export default Login
