import React from 'react'
import { useNavigate } from 'react-router-dom'
import './CalendarConnect.css'

function CalendarConnect() {
  const navigate = useNavigate()
  const token = typeof window === 'undefined' ? null : window.localStorage.getItem('bobbeori-token')

  const startGoogleCalendar = () => {
    if (!token) {
      navigate('/login')
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
    <section className="calendar-connect" aria-labelledby="calendar-connect-title">
      <div className="calendar-connect__panel">
        <span className="calendar-connect__eyebrow">Calendar Sync</span>
        <h1 id="calendar-connect-title">Google Calendar 연결</h1>
        <p>
          소비기한 임박 재료와 추천 메뉴 일정을 Google Calendar에 등록하려면
          캘린더 접근 권한이 필요해요.
        </p>

        <div className="calendar-connect__notice">
          <strong>연결 전 확인</strong>
          <span>구글 로그인 화면은 캘린더 권한 확인용이고, 밥벌이 로그인 화면과 분리되어 있어요.</span>
        </div>

        <div className="calendar-connect__actions">
          <button className="calendar-connect__primary" type="button" onClick={startGoogleCalendar}>
            Google Calendar로 계속
          </button>
          <button className="calendar-connect__secondary" type="button" onClick={() => navigate('/mypage')}>
            마이페이지로 돌아가기
          </button>
        </div>
      </div>
    </section>
  )
}

export default CalendarConnect
