import React from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import logoText from '../../assets/logo_text_extracted.png'
import imageHello from '../../assets/extracted/images/image_hello.png'
import imageCalender from '../../assets/extracted/images/image_calender.png'
import iconReceipt from '../../assets/extracted/icons/icon_receipt.png'
import iconFridge from '../../assets/extracted/icons/icon_refrigerator.png'
import iconBasket from '../../assets/extracted/icons/icon_basket.png'
import './Login.css'

const loginMethods = [
  {
    label: '카카오 로그인', className: 'kakao', provider: 'kakao', envKey: 'VITE_KAKAO_CLIENT_ID',
    icon: <svg viewBox="0 0 24 24" fill="currentColor" xmlns="http://www.w3.org/2000/svg"><path d="M12 3c-5.52 0-10 3.58-10 8 0 2.85 1.83 5.34 4.58 6.74-.24.89-.86 3.19-.9 3.39-.05.24.11.24.23.16.09-.06 2.97-1.99 4.14-2.77.62.08 1.28.13 1.95.13 5.52 0 10-3.58 10-8s-4.48-8-10-8z" /></svg>
  },
  {
    label: '네이버 로그인', className: 'naver', provider: 'naver', envKey: 'VITE_NAVER_CLIENT_ID',
    icon: <svg viewBox="0 0 24 24" fill="currentColor" xmlns="http://www.w3.org/2000/svg"><path d="M16.7 13.78L8.6 3H3.2v18h5.1v-10.8l8.1 10.8h5.4V3h-5.1v10.78z" /></svg>
  },
  {
    label: 'Google 로그인', className: 'google', provider: 'google', envKey: 'VITE_GOOGLE_CLIENT_ID',
    icon: <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path fill="#4285F4" d="M23.74 12.27c0-.85-.08-1.67-.22-2.47H12v4.67h6.58c-.28 1.5-1.12 2.78-2.38 3.63v3h3.86c2.26-2.08 3.56-5.14 3.56-8.83z" /><path fill="#34A853" d="M12 24c3.31 0 6.08-1.1 8.11-2.97l-3.86-3c-1.1.74-2.51 1.18-4.25 1.18-3.26 0-6.03-2.2-7.02-5.16H1.05v3.1A11.984 11.984 0 0 0 12 24z" /><path fill="#FBBC05" d="M4.98 14.05A7.16 7.16 0 0 1 4.6 12c0-.71.12-1.4.35-2.05v-3.1H1.05A11.964 11.964 0 0 0 0 12c0 1.94.46 3.76 1.25 5.4l3.73-3.35z" /><path fill="#EA4335" d="M12 4.75c1.8 0 3.42.62 4.69 1.83l3.52-3.52C18.08 1.1 15.31 0 12 0 7.42 0 3.52 2.61 1.05 6.85l3.93 3.1c.99-2.96 3.76-5.2 7.02-5.2z" /></svg>
  },
]

const serviceFeatures = [
  { title: '냉장고 재료로', description: '똑똑한 요리', image: iconFridge },
  { title: '식재료 낭비 줄이고', description: '알뜰하게', image: iconReceipt },
  { title: '매일 맛있는', description: '식탁 완성', image: iconBasket },
]

const calendarFeatures = [
  { title: '자동 등록', description: '필요한 일정만', image: iconFridge },
  { title: '중복 방지', description: '같은 알림은 한 번만', image: iconBasket },
  { title: '언제든 해제', description: '마이페이지에서 관리', image: iconReceipt },
]

const calendarPreviewEvents = [
  { time: '08:30', title: '소비 임박 재료 확인', description: '오늘 써야 할 재료를 한 번에 알려드려요.', tone: 'green' },
  { time: '17:30', title: '오늘의 추천 메뉴', description: '저녁에 만들기 좋은 메뉴를 캘린더에 남겨요.', tone: 'coral' },
  { time: '09:00', title: '저장 레시피 만료 예정', description: '7일 보관이 끝나기 전에 다시 확인해요.', tone: 'yellow' },
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
  const visualImage = isCalendarMode ? imageCalender : imageHello

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
          <div className={`login-card__visual ${isCalendarMode ? 'is-calendar' : ''}`} aria-label={isCalendarMode ? '캘린더 연동 소개' : '밥벌이 로그인 소개'}>
            <img className="login-card__brand-logo" src={logoText} alt="밥벌이" />

            <div className="login-card__copy">
              <p className="login-card__eyebrow">
                {isCalendarMode ? '밥벌이 알림을' : '맛있는 한 끼,'}
              </p>
              <h1>
                <strong>{isCalendarMode ? '캘린더에 등록해요' : '밥벌이와 함께!'}</strong>
              </h1>
              <p className="login-card__description">
                {isCalendarMode ? (
                  <>
                    소비 임박 재료, 저녁 추천 메뉴, 저장 레시피 만료일을
                    <br />
                    Google Calendar 일정으로 자동 등록해요.
                  </>
                ) : (
                  <>
                    냉장고 재료로 오늘의 한 끼를 쉽게 만들고
                    <br />
                    식재료 낭비는 줄이고, 맛있는 일상은 더해요.
                  </>
                )}
              </p>
            </div>

            <div className="login-card__art-wrap">
              <img className="login-card__art" src={visualImage} alt="" />
            </div>


          </div>

          <div className="login-card__form-wrap">
            <div className={`login-card__form ${isCalendarMode ? 'is-calendar' : ''}`} aria-label={isCalendarMode ? '캘린더 연동' : '소셜 로그인'}>
              <h2 id="login-title">{isCalendarMode ? '캘린더를 연결할게요' : '환영해요!'}</h2>
              <p className="login-card__helper">
                {isCalendarMode
                  ? '연결하면 밥벌이가 필요한 일정만 골라 Google Calendar에 등록해요.'
                  : '간편 로그인으로 밥벌이의 모든 서비스를 이용해보세요.'}
              </p>

              {isCalendarMode ? (
                <div className="login-calendar-preview" aria-label="등록될 캘린더 일정 미리보기">
                  <div className="login-calendar-preview__top">
                    <span>오늘 등록될 일정</span>
                    <strong>3개</strong>
                  </div>
                  <div className="login-calendar-preview__list">
                    {calendarPreviewEvents.map((event) => (
                      <div className="login-calendar-preview__item" key={event.title}>
                        <time className={`is-${event.tone}`}>{event.time}</time>
                        <div>
                          <strong>{event.title}</strong>
                          <span>{event.description}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}

              <div className="login-card__buttons">
                {isCalendarMode ? (
                  <button className="login-card__button calendar" type="button" onClick={handleCalendarLogin}>
                    <span className="login-card__provider google">G</span>
                    일정 등록 권한 연결
                  </button>
                ) : (
                  loginMethods.map((method) => (
                    <button
                      className={`login-card__button ${method.className}`}
                      type="button"
                      key={method.label}
                      onClick={() => handleSocialLogin(method)}
                    >
                      <span className="login-card__provider">{method.icon}</span>
                      <span className="login-card__button-text">{method.label}</span>
                      <span className="login-card__button-ghost"></span>
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
                    <a href="/privacy">개인정보 처리방침</a>에 동의하게 됩니다.
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
