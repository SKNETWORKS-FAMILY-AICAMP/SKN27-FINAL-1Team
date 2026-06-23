import React, { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import './Mypage.css'

import iconAlarm from '../../assets/extracted/icons/icon_alarm.png'
import iconRefrigerator from '../../assets/extracted/icons/icon_refrigerator.png'
import imageMypage from '../../assets/extracted/images/image_mypage.png'
import imageRecommendation from '../../assets/extracted/images/image_recommendation.png'
import { serviceContext, userProfile } from '../../mock/userService.js'

const alerts = [
  { label: '소비 임박 알림', checked: true },
  { label: '장보기 가격 변동 알림', checked: true },
  { label: '추천 레시피 알림', checked: false },
  { label: 'OCR 입고 완료 알림', checked: true },
]

const recentRecipes = [
  { title: '버섯 들깨탕', meta: '최근 본 레시피' },
  { title: '김치 참치 볶음밥', meta: '저장한 레시피' },
]

const cartHistory = [
  { date: '2024.05.20', price: '11,140원' },
  { date: '2024.05.16', price: '8,400원' },
  { date: '2024.05.12', price: '7,380원' },
]

const toLocalDateKey = (date) => {
  const localDate = new Date(date.getTime() - date.getTimezoneOffset() * 60000)
  return localDate.toISOString().slice(0, 10)
}

const todayForCalendar = new Date()
const recipeDeleteDate = new Date(todayForCalendar)
recipeDeleteDate.setDate(todayForCalendar.getDate() + 7)

const calendarEvents = [
  { dateKey: toLocalDateKey(todayForCalendar), title: '대파 오늘까지 사용 추천', tone: 'danger' },
  { dateKey: toLocalDateKey(todayForCalendar), title: '저녁 추천: 대파 두부 계란찌개', tone: 'green' },
  { dateKey: toLocalDateKey(recipeDeleteDate), title: '저장 레시피 삭제 예정', tone: 'yellow' },
]

const tabs = [
  { id: 'profile', label: '내 정보' },
  { id: 'alerts', label: '알림 및 캘린더' },
]

function ImageSlot({ src, alt = '', className = '' }) {
  return (
    <span className={`mypage-image-slot ${src ? 'is-filled' : ''} ${className}`}>
      {src ? <img src={src} alt={alt} /> : null}
    </span>
  )
}

function Toggle({ checked, label, onClick }) {
  return (
    <button
      className={`mypage-toggle ${checked ? 'is-on' : ''}`}
      type="button"
      aria-label={`${label} ${checked ? '끄기' : '켜기'}`}
      aria-pressed={checked}
      onClick={onClick}
    />
  )
}

function CalendarPreview({ connected }) {
  const today = new Date()
  const year = today.getFullYear()
  const month = today.getMonth()
  const firstDay = new Date(year, month, 1).getDay()
  const lastDate = new Date(year, month + 1, 0).getDate()
  const days = [
    ...Array.from({ length: firstDay }, (_, index) => ({ id: `empty-${index}` })),
    ...Array.from({ length: lastDate }, (_, index) => {
      const day = index + 1
      return { id: day, day, dateKey: toLocalDateKey(new Date(year, month, day)) }
    }),
  ]

  return (
    <section className="mypage-panel mypage-calendar-preview" aria-labelledby="calendar-preview-title">
      <div className="mypage-calendar-preview__head">
        <div>
          <h2 id="calendar-preview-title">밥벌이 캘린더</h2>
          <p>{connected ? 'Google Calendar와 연결되어 있어요.' : '연동하면 일정 등록이 가능해요.'}</p>
        </div>
        <strong>{year}.{String(month + 1).padStart(2, '0')}</strong>
      </div>
      <div className="mypage-calendar-preview__week" aria-hidden="true">
        {['일', '월', '화', '수', '목', '금', '토'].map((day) => (
          <span key={day}>{day}</span>
        ))}
      </div>
      <div className="mypage-calendar-preview__grid">
        {days.map((item) => {
          const events = calendarEvents.filter((calendarEvent) => calendarEvent.dateKey === item.dateKey)
          return (
            <div
              className={`mypage-calendar-preview__day ${item.day === today.getDate() ? 'is-today' : ''}`}
              key={item.id}
            >
              {item.day ? <span>{item.day}</span> : null}
              {events.map((event) => (
                <b className={`is-${event.tone}`} key={event.title}>{event.title}</b>
              ))}
            </div>
          )
        })}
      </div>
    </section>
  )
}

function Mypage() {
  const navigate = useNavigate()
  const [alertSettings, setAlertSettings] = useState(alerts)
  const [activeTab, setActiveTab] = useState('profile')
  const [calendarEnabled, setCalendarEnabled] = useState(false)
  const [calendarAutoAdd, setCalendarAutoAdd] = useState(true)
  const [calendarTestEvent, setCalendarTestEvent] = useState(null)
  const [profileName, setProfileName] = useState(userProfile.name)
  const [profileEmail, setProfileEmail] = useState('babbeori@example.com')
  const [isEditingProfile, setIsEditingProfile] = useState(false)
  const [connectedSocials, setConnectedSocials] = useState(['카카오', '네이버', '구글'])
  const [userData, setUserData] = useState(null)
  const [inventorySummary, setInventorySummary] = useState({
    total: 0,
    expiring_soon: 0,
    storage: { 냉장: 0, 냉동: 0, 실온: 0, 기타: 0 },
  })
  const [savedFridgeRecipe] = useState(() => {
    if (typeof window === 'undefined') return null

    const saved = window.localStorage.getItem('bobbeori-fridge-recipe')
    return saved ? JSON.parse(saved) : null
  })
  const authMode =
    typeof window === 'undefined' ? null : window.localStorage.getItem('bobbeori-auth-mode')
  const isGuest = authMode === 'guest'
  const activeAlertsCount = useMemo(
    () => alertSettings.filter((alert) => alert.checked).length,
    [alertSettings],
  )

  const dynamicStats = [
    { 
      label: '보유 재료', 
      value: `${inventorySummary.total}개`, 
      note: `냉장 ${inventorySummary.storage['냉장']} · 냉동 ${inventorySummary.storage['냉동']} · 임박 ${inventorySummary.expiring_soon}`, 
      image: iconRefrigerator 
    },
    { label: '추천 횟수', value: '24회', note: '이번 달 기준', image: iconAlarm },
  ]

  useEffect(() => {
    if (isGuest) {
      return
    }

    const token = window.localStorage.getItem('bobbeori-token')
    if (!token) {
      return
    }

    const fetchUser = async () => {
      try {
        const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000'
        const [userDataResponse, summaryResponse, calendarResponse] = await Promise.all([
          fetch(`${apiUrl}/api/v1/auth/me`, {
            headers: { Authorization: `Bearer ${token}` },
          }),
          fetch(`${apiUrl}/api/v1/inventory/summary`, {
            headers: { Authorization: `Bearer ${token}` },
          }),
          fetch(`${apiUrl}/api/v1/calendar/google/status`, {
            headers: { Authorization: `Bearer ${token}` },
          }),
        ])

        if (!userDataResponse.ok) {
          throw new Error('인증 실패')
        }

        const data = await userDataResponse.json()
        setUserData(data)
        
        if (summaryResponse.ok) {
          const summaryData = await summaryResponse.json()
          setInventorySummary(summaryData)
        }

        if (calendarResponse.ok) {
          const calendarData = await calendarResponse.json()
          setCalendarEnabled(calendarData.connected)
        }

        setProfileName(data.nickname ? `${data.nickname}님` : userProfile.name)
        setProfileEmail(data.email || 'babbeori@example.com')
        setConnectedSocials((prev) => {
          if (!data.provider) {
            return prev
          }

          const providerLabel = {
            kakao: '카카오',
            naver: '네이버',
            google: '구글',
          }[data.provider] ?? data.provider

          return prev.includes(providerLabel) ? prev : [providerLabel, ...prev]
        })
      } catch (err) {
        console.error(err)
        window.localStorage.removeItem('bobbeori-token')
        window.localStorage.removeItem('bobbeori-auth-mode')
        window.dispatchEvent(new Event('bobbeori-auth-change'))
        navigate('/login')
      }
    }

    fetchUser()
  }, [isGuest, navigate])

  const handleLogout = () => {
    window.localStorage.removeItem('bobbeori-token')
    window.localStorage.removeItem('bobbeori-auth-mode')
    window.dispatchEvent(new Event('bobbeori-auth-change'))
    navigate('/login')
  }

  const toggleAlert = (targetLabel) => {
    setAlertSettings((prev) =>
      prev.map((alert) =>
        alert.label === targetLabel ? { ...alert, checked: !alert.checked } : alert,
      ),
    )
  }

  const saveProfile = () => {
    setIsEditingProfile(false)
    window.localStorage.setItem(
      'bobbeori-profile',
      JSON.stringify({ name: profileName, email: profileEmail }),
    )
  }

  const connectSocial = () => {
    const nextSocial = connectedSocials.includes('구글') ? '애플' : '구글'
    setConnectedSocials((prev) => (prev.includes(nextSocial) ? prev : [...prev, nextSocial]))
  }

  const connectGoogleCalendar = async () => {
    navigate('/login?calendar=1')
  }

  const createCalendarTestEvent = async () => {
    const token = window.localStorage.getItem('bobbeori-token')
    if (!token) {
      navigate('/login')
      return
    }

    const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000'
    const response = await fetch(`${apiUrl}/api/v1/calendar/google/test-event`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
    })

    if (!response.ok) {
      window.alert('Google Calendar 일정 생성에 실패했어요. 다시 연동해보세요.')
      return
    }

    const data = await response.json()
    setCalendarTestEvent(data.events?.find((event) => event.html_link) ?? null)
  }

  const profileDisplayName = isGuest ? '게스트님' : profileName
  const profileDisplayEmail = isGuest ? 'guest@bobbeori.com' : profileEmail
  const profileCreatedAt = userData?.created_at
    ? `가입일 ${new Date(userData.created_at).toLocaleDateString()}`
    : '가입일 2024. 05. 22'
  const selectedRecipe = savedFridgeRecipe ?? {
    id: 'green-onion-tofu-egg-stew',
    title: serviceContext.selectedRecipe,
    category: '기본 추천',
    reason: `${userProfile.priority} 기준으로 이어볼 수 있는 추천 메뉴예요.`,
  }

  return (
    <section className="mypage" aria-labelledby="mypage-title">
      <div className="mypage-hero">
        <div>
          <h1 id="mypage-title">마이페이지</h1>
          <p>
            내 프로필, 저장한 레시피, 알림 설정과 이용 기록을 한곳에서 확인해요.
          </p>
        </div>
        <ImageSlot className="mypage-hero__image" src={imageMypage} />
      </div>

      <div className="mypage-layout">
        <nav className="mypage-tabs" aria-label="마이페이지 메뉴">
          {tabs.map((tab) => (
            <button
              className={activeTab === tab.id ? 'is-active' : ''}
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </nav>

        <div className="mypage-content">
          {activeTab === 'profile' && (
            <>
              <section className="mypage-panel mypage-profile" aria-label="회원 정보">
                <ImageSlot className="mypage-profile__avatar" src={imageMypage} />
                <div className="mypage-profile__info">
                  <div className="mypage-profile__name">
                    {isEditingProfile ? (
                      <input
                        aria-label="이름"
                        value={profileName}
                        onChange={(event) => setProfileName(event.target.value)}
                      />
                    ) : (
                      <h2>{profileDisplayName}</h2>
                    )}
                    <span>{isGuest ? '게스트' : '일반 회원'}</span>
                  </div>
                  {isEditingProfile ? (
                    <input
                      aria-label="이메일"
                      value={profileEmail}
                      onChange={(event) => setProfileEmail(event.target.value)}
                    />
                  ) : (
                    <p>{profileDisplayEmail}</p>
                  )}
                  <small>{isGuest ? '게스트 모드 이용 중' : profileCreatedAt}</small>
                  <div className="mypage-profile__actions">
                    <button
                      className="mypage-primary-button"
                      type="button"
                      onClick={isEditingProfile ? saveProfile : () => setIsEditingProfile(true)}
                    >
                      {isEditingProfile ? '저장하기' : '프로필 수정'}
                    </button>
                    <button className="mypage-soft-button" type="button" onClick={handleLogout}>
                      로그아웃
                    </button>
                  </div>
                </div>
                <div className="mypage-social">
                  <strong>소셜 로그인 정보</strong>
                  <div>
                    {connectedSocials.map((social) => {
                      const className =
                        social === '카카오'
                          ? 'mypage-social__pill--kakao'
                          : social === '구글'
                            ? 'mypage-social__pill--google'
                            : 'mypage-social__pill--naver'

                      const isActive =
                        (social === '카카오' && userData?.provider === 'kakao') ||
                        (social === '네이버' && userData?.provider === 'naver') ||
                        (social === '구글' && userData?.provider === 'google')

                      return (
                        <span
                          className={`mypage-social__pill ${className} ${isActive ? 'is-active' : ''}`}
                          key={social}
                        >
                          {social}
                        </span>
                      )
                    })}
                    <button className="mypage-connect-button" type="button" onClick={connectSocial}>
                      + 연결하기
                    </button>
                  </div>
                </div>
              </section>

              <div className="mypage-stats" aria-label="마이페이지 통계">
                {dynamicStats.map((stat, index) => (
                  <button
                    className="mypage-panel mypage-stat"
                    key={stat.label}
                    type="button"
                    onClick={() => navigate(index === 0 ? '/fridge' : '/recipe-fridge')}
                  >
                    <div>
                      <span>{stat.label}</span>
                      <strong>{stat.value}</strong>
                      <p>{stat.note}</p>
                    </div>
                    <ImageSlot className="mypage-stat__image" src={stat.image} />
                  </button>
                ))}
              </div>

              <div className="mypage-history-grid">
                <section className="mypage-panel mypage-recipe" aria-labelledby="selected-recipe-title">
                  <div className="mypage-panel__title">
                    <h2 id="selected-recipe-title">오늘 이어갈 추천</h2>
                  </div>
                  <article className="mypage-selected-recipe">
                    <ImageSlot className="mypage-selected-recipe__image" src={imageRecommendation} />
                    <div>
                      <div className="mypage-recipe-title-row">
                        <h3>{selectedRecipe.title}</h3>
                        <span>{savedFridgeRecipe ? '저장됨' : selectedRecipe.category}</span>
                      </div>
                      <p>{selectedRecipe.reason}</p>
                      <p>{savedFridgeRecipe ? `보유 재료 ${selectedRecipe.owned}/${selectedRecipe.total}개 · 부족 재료 ${selectedRecipe.missing.length}개` : '저장한 메뉴와 최근 본 레시피를 이어서 확인할 수 있어요.'}</p>
                      <div className="mypage-recipe-actions">
                        <button
                          className="mypage-primary-button"
                          type="button"
                          onClick={() => navigate(`/recipes/${selectedRecipe.id}`)}
                        >
                          레시피 보기
                        </button>
                        <button className="mypage-soft-button" type="button" onClick={() => navigate('/shopping-list')}>
                          장보기 이동
                        </button>
                      </div>
                    </div>
                  </article>

                  <div className="mypage-recent">
                    <div className="mypage-subtitle-row">
                      <strong>최근 선택 레시피</strong>
                      <button type="button" onClick={() => navigate('/recipes')}>전체 보기</button>
                    </div>
                    <div className="mypage-recent-list">
                      {recentRecipes.map((recipe) => (
                        <button type="button" key={recipe.title} onClick={() => navigate('/recipes')}>
                          <ImageSlot className="mypage-recent__image" />
                          <div>
                            <h3>{recipe.title}</h3>
                            <p>{recipe.meta}</p>
                          </div>
                        </button>
                      ))}
                    </div>
                  </div>
                </section>

                <section className="mypage-panel mypage-usage" aria-labelledby="usage-title">
                  <div className="mypage-subtitle-row">
                    <h2 id="usage-title">이용 기록</h2>
                    <button type="button" onClick={() => navigate('/shopping-list')}>전체 보기</button>
                  </div>
                  <div className="mypage-chart" aria-label="월별 사용 요약">
                    {[52, 36, 64, 44, 70, 50, 40, 0].map((height, index) => (
                      <span key={`${height}-${index}`} style={{ '--bar-height': `${height}%` }} />
                    ))}
                  </div>
                  <div className="mypage-history">
                    <strong>최근 장보기 기록</strong>
                    {cartHistory.map((item) => (
                      <div key={item.date}>
                        <span>{item.date}</span>
                        <b>{item.price}</b>
                      </div>
                    ))}
                  </div>
                </section>
              </div>

              <section className="mypage-panel mypage-settings" aria-labelledby="account-title">
                <h2 id="account-title">계정 관리</h2>
                <p className="mypage-setting-note">서비스 이용 정보와 계정 상태를 관리해요.</p>
                <ul>
                  <li><span>개인정보 처리방침</span><button type="button">보기</button></li>
                  <li><span>이용약관</span><button type="button">보기</button></li>
                  <li><span>회원 탈퇴</span><button type="button">요청하기</button></li>
                </ul>
              </section>
            </>
          )}

          {activeTab === 'alerts' && (
            <>
              <div className="mypage-alert-calendar">
                <section className="mypage-panel mypage-settings" aria-labelledby="alerts-title">
                  <h2 id="alerts-title">서비스 알림</h2>
                  <p className="mypage-setting-note">현재 {activeAlertsCount}개 알림이 켜져 있어요.</p>
                  <ul>
                    {alertSettings.map((alert) => (
                      <li key={alert.label}>
                        <span>{alert.label}</span>
                        <Toggle
                          checked={alert.checked}
                          label={alert.label}
                          onClick={() => toggleAlert(alert.label)}
                        />
                      </li>
                    ))}
                  </ul>
                </section>

                <section className="mypage-panel mypage-settings" aria-labelledby="calendar-title">
                  <h2 id="calendar-title">캘린더 설정</h2>
                  <p className="mypage-setting-note">
                    소비기한과 오늘 먹을 재료를 일정으로 받아봐요.
                  </p>
                  <ul>
                    <li>
                      <span>소비기한 일정 자동 등록</span>
                      <Toggle
                        checked={calendarAutoAdd}
                        label="소비기한 일정 자동 등록"
                        onClick={() => setCalendarAutoAdd((prev) => !prev)}
                      />
                    </li>
                    <li>
                      <span>등록 캘린더</span>
                      <b>{calendarEnabled ? '밥벌이 냉장고' : '연동 후 선택 가능'}</b>
                    </li>
                  </ul>
                </section>
              </div>

              <section className="mypage-panel mypage-calendar-connect" aria-labelledby="google-calendar-title">
                <div>
                  <h2 id="google-calendar-title">Google Calendar 연결</h2>
                  <p>소비기한 임박 재료와 추천 식단 알림을 캘린더에 자동으로 등록해요.</p>
                  {calendarTestEvent ? (
                    <a href={calendarTestEvent.html_link} target="_blank" rel="noreferrer">
                      생성한 캘린더 일정 확인하기
                    </a>
                  ) : null}
                </div>
                <div className="mypage-calendar-connect__actions">
                  {calendarEnabled ? (
                    <button className="mypage-soft-button" type="button" onClick={createCalendarTestEvent}>
                      캘린더 알림 3개 추가
                    </button>
                  ) : null}
                  <button
                    className="mypage-primary-button"
                    type="button"
                    onClick={connectGoogleCalendar}
                  >
                    {calendarEnabled ? '연동 해제' : 'Google Calendar 연결'}
                  </button>
                </div>
              </section>

              <CalendarPreview connected={calendarEnabled} />
            </>
          )}

        </div>
      </div>
    </section>
  )
}

export default Mypage
