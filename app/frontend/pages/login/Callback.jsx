import React, { useEffect, useState, useRef } from 'react'
import { useParams, useSearchParams, useNavigate } from 'react-router-dom'
import './Login.css'

function Callback() {
  const { provider } = useParams()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const [error, setError] = useState(null)
  const isFetching = useRef(false)

  useEffect(() => {
    const code = searchParams.get('code')
    const returnedState = searchParams.get('state')
    const savedStateKey = `bobbeori-oauth-state-${provider}`
    const savedState = window.sessionStorage.getItem(savedStateKey)

    if (!code) {
      setError('인증 코드가 없습니다.')
      setTimeout(() => navigate('/login'), 2000)
      return
    }

    // OAuth 요청과 콜백이 같은 브라우저 흐름에서 온 것인지 확인합니다.
    if (!returnedState || !savedState || returnedState !== savedState) {
      window.sessionStorage.removeItem(savedStateKey)
      setError('로그인 요청 검증에 실패했습니다. 다시 시도해주세요.')
      setTimeout(() => navigate('/login'), 2000)
      return
    }
    window.sessionStorage.removeItem(savedStateKey)

    if (isFetching.current) return
    isFetching.current = true

    const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000'

    const fetchToken = async () => {
      try {
        const response = await fetch(`${apiUrl}/api/v1/auth/social-login`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            provider: provider,
            code: code,
            state: returnedState,
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
        setError(err.message)
        setTimeout(() => navigate('/login'), 3000)
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
