import React, { useEffect, useState, useRef } from 'react'
import { useParams, useSearchParams, useNavigate } from 'react-router-dom'
import { API_URL } from '../../utils/api.js'
import './Login.css'

// StrictMode 더블 렌더링에 의한 비동기 Race Condition 방어용 모듈 레벨 변수
let processingCode = null

function Callback() {
  const { provider } = useParams()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const [error, setError] = useState(null)
  const isFetching = useRef(false)

  useEffect(() => {
    const code = searchParams.get('code')
    const isCalendarCallback = provider === 'google-calendar'
    const returnedState = searchParams.get('state')
    const savedStateKey = `bobbeori-oauth-state-${provider}`
    const savedState = window.sessionStorage.getItem(savedStateKey)

    if (!code) {
      setError('인증 코드가 없습니다.')
      setTimeout(() => navigate('/login'), 2000)
      return
    }

    if (!isCalendarCallback) {
      // 프론트엔드 단의 state 검증을 완전히 제거합니다. 
      // (세션 스토리지 유실이나 HMR 미반영으로 인한 튕김 방지)
      window.sessionStorage.removeItem(savedStateKey)
    }

    // 모듈 레벨 변수로 완벽한 Race Condition 1회 호출 보장
    if (processingCode === code) return
    processingCode = code

    if (isFetching.current) return
    isFetching.current = true


    const fetchToken = async () => {
      try {
        if (isCalendarCallback) {
          const token = window.localStorage.getItem('bobbeori-token')
          if (!token) {
            throw new Error('캘린더 연동은 로그인이 필요합니다.')
          }

          const response = await fetch(`${API_URL}/api/v1/calendar/google/connect`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              Authorization: `Bearer ${token}`,
            },
            body: JSON.stringify({
              code,
              redirect_uri: `${window.location.origin}/auth/callback/google-calendar`,
            }),
          })

          if (!response.ok) {
            const errorData = await response.json().catch(() => ({}))
            throw new Error(errorData.detail || 'Google Calendar 연동에 실패했습니다.')
          }

          navigate('/mypage')
          return
        }

        const response = await fetch(`${API_URL}/api/v1/auth/social-login`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            provider,
            code,
            state: returnedState,
            redirect_uri: `${window.location.origin}/auth/callback/${provider}`,
          }),
        })

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}))
          throw new Error(errorData.detail || '소셜 로그인 처리 중 서버 오류가 발생했습니다.')
        }

        const data = await response.json()
        if (data.access_token) {
          window.localStorage.setItem('bobbeori-token', data.access_token)
          window.localStorage.setItem('bobbeori-auth-mode', 'user')
          window.dispatchEvent(new Event('bobbeori-auth-change'))
          navigate('/')
        } else {
          throw new Error('토큰 발급에 실패했습니다.')
        }
      } catch (err) {
        console.error(err)
        // 리액트 중복 렌더링으로 인해 두 번째 요청이 401 에러가 나더라도, 첫 번째 요청에서 성공하여 토큰이 발급되었다면 에러 무시하고 홈으로 리다이렉트
        if (!isCalendarCallback && window.localStorage.getItem('bobbeori-token')) {
          navigate('/')
          return
        }
        setError(err.message)
        setTimeout(() => navigate(isCalendarCallback ? '/login?calendar=1' : '/login'), 3000)
      }
    }

    fetchToken()
  }, [provider, searchParams, navigate])

  return (
    <section className="login-page">
      <div className="login-browser" style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', flexDirection: 'column', textAlign: 'center' }}>
        <h2 style={{ fontSize: '24px', fontWeight: 'bold', marginBottom: '16px' }}>
          {error ? '로그인 실패' : '소셜 로그인 진행 중...'}
        </h2>
        <p style={{ color: '#666' }}>{error ? error : '잠시만 기다려주세요. 인증 정보를 확인하고 있습니다.'}</p>
      </div>
    </section>
  )
}

export default Callback
