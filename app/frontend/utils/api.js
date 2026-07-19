export const API_URL = import.meta.env?.VITE_API_URL || 'http://localhost:8000'

export const API_NOTICE_EVENT = 'bobbeori-api-notice'
export const SESSION_EXPIRED_KEY = 'bobbeori-session-expired-alerted'

const API_NOTICES = {
  loginRequired: {
    title: '로그인 필요',
    message: '로그인이 필요한 서비스입니다. 로그인한 뒤 이용해주세요.',
  },
  sessionExpired: {
    title: '로그인 만료',
    message: '로그인 세션이 만료되었습니다.\n다시 로그인한 뒤 이용해주세요.',
  },
  serverError: {
    title: '서비스 오류',
    message: '사용자 정보를 불러오지 못했습니다. 잠시 후 다시 시도해주세요.',
  },
  networkError: {
    title: '연결 오류',
    message: '서버에 연결할 수 없습니다. 서버 실행 상태를 확인해주세요.',
  },
}

// API 오류 유형에 맞는 공용 안내 모달을 표시합니다.
export const showApiNotice = (type) => {
  const notice = API_NOTICES[type]
  if (notice) window.dispatchEvent(new CustomEvent(API_NOTICE_EVENT, { detail: { type, ...notice } }))
}

// 로그인 토큰을 제거하고 화면에 인증 상태 변경을 알립니다.
const clearAuthToken = () => {
  window.localStorage.removeItem('bobbeori-token')
  window.localStorage.removeItem('bobbeori-auth-mode')
  window.dispatchEvent(new Event('bobbeori-auth-change'))
}

// 인증 헤더를 추가하고 401/403 응답만 세션 만료로 공통 처리합니다.
export const authenticatedFetch = async (url, options = {}) => {
  const headers = new Headers(options.headers)
  const token = window.localStorage.getItem('bobbeori-token')
  if (token && !headers.has('Authorization')) headers.set('Authorization', `Bearer ${token}`)

  const response = await fetch(url, { ...options, headers })
  if (response.status !== 401 && response.status !== 403) return response

  clearAuthToken()
  showApiNotice('sessionExpired')
  const error = new Error('로그인 세션이 만료되었습니다.')
  error.code = 'SESSION_EXPIRED'
  throw error
}

// 인증 만료 오류인지 확인하여 호출부의 이동 처리에 사용합니다.
export const isSessionExpiredError = (error) => error?.code === 'SESSION_EXPIRED'
