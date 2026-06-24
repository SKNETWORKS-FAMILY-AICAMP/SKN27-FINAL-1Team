import React, { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import './Mypage.css'

import iconAlarm from '../../assets/extracted/icons/icon_alarm.png'
import iconRefrigerator from '../../assets/extracted/icons/icon_refrigerator.png'
import imageMypage from '../../assets/extracted/images/image_mypage.png'
import imageRecommendation from '../../assets/extracted/images/image_recommendation.png'
import { serviceContext, userProfile } from '../../mock/userService.js'
import { readStoredRecipes, removeStoredRecipe, saveStoredRecipe } from '../../utils/savedRecipes.js'

const alerts = [
  { label: '소비 임박 알림', checked: true },
  { label: '오늘의 추천 메뉴', checked: true },
  { label: '레시피 삭제 예정 알림', checked: true },
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

const tabs = [
  { id: 'profile', label: '내 정보' },
  { id: 'saved', label: '저장된 레시피' },
  { id: 'alerts', label: '알림 및 캘린더' },
]

const getDaysLeft = (expiresAt) =>
  Math.max(0, Math.ceil((new Date(expiresAt).getTime() - Date.now()) / (24 * 60 * 60 * 1000)))

const getCalendarTone = (event) =>
  ({
    11: 'danger',
    2: 'green',
    5: 'yellow',
    6: 'info',
  }[String(event.colorId)] || 'green')

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

function CalendarPreview({ connected, events, monthDate, onChangeMonth }) {
  const today = new Date()
  const year = monthDate.getFullYear()
  const month = monthDate.getMonth()
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
          <p>{connected ? 'Google Calendar 일정을 불러왔어요.' : '연동하면 일정 등록이 가능해요.'}</p>
        </div>
        <div className="mypage-calendar-preview__month">
          <button type="button" onClick={() => onChangeMonth(-1)} aria-label="이전 달">‹</button>
          <strong>{year}.{String(month + 1).padStart(2, '0')}</strong>
          <button type="button" onClick={() => onChangeMonth(1)} aria-label="다음 달">›</button>
        </div>
      </div>
      <div className="mypage-calendar-preview__week" aria-hidden="true">
        {['일', '월', '화', '수', '목', '금', '토'].map((day) => (
          <span key={day}>{day}</span>
        ))}
      </div>
      <div className="mypage-calendar-preview__grid">
        {days.map((item) => {
          const dayEvents = events.filter((calendarEvent) => calendarEvent.dateKey === item.dateKey)
          return (
            <div
              className={`mypage-calendar-preview__day ${item.day === today.getDate() ? 'is-today' : ''}`}
              key={item.id}
            >
              {item.day ? <span>{item.day}</span> : null}
              {dayEvents.map((event) => (
                event.htmlLink ? (
                  <a
                    className={`is-${getCalendarTone(event)}`}
                    href={event.htmlLink}
                    key={event.id || event.title}
                    rel="noreferrer"
                    target="_blank"
                  >
                    {event.title}
                  </a>
                ) : (
                  <b className={`is-${getCalendarTone(event)}`} key={event.id || event.title}>{event.title}</b>
                )
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
  const [googleCalendarEvents, setGoogleCalendarEvents] = useState([])
  const [calendarMonth, setCalendarMonth] = useState(() => new Date())
  const [calendarCostEnabled, setCalendarCostEnabled] = useState(() =>
    typeof window === 'undefined'
      ? true
      : window.localStorage.getItem('bobbeori-calendar-cost-enabled') !== 'false',
  )
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
  const [savedRecipes, setSavedRecipes] = useState(() => {
    if (typeof window === 'undefined') return []

    const stored = readStoredRecipes()
    const legacy = window.localStorage.getItem('bobbeori-fridge-recipe')
    if (!legacy) return stored

    try {
      const recipe = JSON.parse(legacy)
      if (!recipe?.id || stored.some((item) => item.id === recipe.id)) return stored
      return [saveStoredRecipe({ ...recipe, source: recipe.source || '냉장고파먹기' }), ...stored]
    } catch {
      return stored
    }
  })
  const authMode =
    typeof window === 'undefined' ? null : window.localStorage.getItem('bobbeori-auth-mode')
  const isGuest = authMode === 'guest'
  const activeAlertsCount = useMemo(
    () => alertSettings.filter((alert) => alert.checked).length,
    [alertSettings],
  )
  const savedFridgeRecipe = savedRecipes[0] ?? null
  const recommendedSavedRecipes = useMemo(
    () => savedRecipes.filter((recipe) => recipe.savedType !== 'saved'),
    [savedRecipes],
  )
  const manuallySavedRecipes = useMemo(
    () => savedRecipes.filter((recipe) => recipe.savedType === 'saved'),
    [savedRecipes],
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

  const loadSavedRecipes = async () => {
    const localRecipes = readStoredRecipes()
    const token = window.localStorage.getItem('bobbeori-token')
    if (!token || isGuest) {
      setSavedRecipes(localRecipes)
      return
    }

    try {
      const apiBaseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000'
      const response = await fetch(`${apiBaseUrl}/api/v1/recommendations`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!response.ok) {
        setSavedRecipes(localRecipes)
        return
      }

      const remoteRecipes = await response.json()
      remoteRecipes.forEach((recipe) => {
        const isManualSave = recipe.recommendation_type === 'manual_save'
        saveStoredRecipe({
          recipe_id: recipe.recipe_id,
          recommendation_id: recipe.recommendation_id,
          title: recipe.title,
          description: recipe.description,
          category: recipe.category,
          image: recipe.image_url,
          source: isManualSave ? '저장한 레시피' : '추천 레시피',
          savedType: isManualSave ? 'saved' : 'recommended',
          savedAt: recipe.created_at,
          recommendation_type: recipe.recommendation_type,
        })
      })
      setSavedRecipes(readStoredRecipes())
    } catch {
      setSavedRecipes(localRecipes)
    }
  }

  const loadGoogleCalendarEvents = async () => {
    const token = window.localStorage.getItem('bobbeori-token')
    if (!token || !calendarEnabled) {
      setGoogleCalendarEvents([])
      return
    }

    const startDate = toLocalDateKey(new Date(calendarMonth.getFullYear(), calendarMonth.getMonth(), 1))
    const endDate = toLocalDateKey(new Date(calendarMonth.getFullYear(), calendarMonth.getMonth() + 1, 1))

    try {
      const apiBaseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000'
      const response = await fetch(
        `${apiBaseUrl}/api/v1/calendar/google/events?start_date=${startDate}&end_date=${endDate}`,
        { headers: { Authorization: `Bearer ${token}` } },
      )
      if (!response.ok) {
        setGoogleCalendarEvents([])
        return
      }

      const data = await response.json()
      setGoogleCalendarEvents(data.events || [])
    } catch {
      setGoogleCalendarEvents([])
    }
  }

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

  useEffect(() => {
    if (activeTab === 'saved') {
      loadSavedRecipes()
    }
  }, [activeTab])

  useEffect(() => {
    if (activeTab === 'alerts') {
      loadGoogleCalendarEvents()
    }
  }, [activeTab, calendarEnabled, calendarMonth])

  const changeCalendarMonth = (offset) => {
    setCalendarMonth((prev) => new Date(prev.getFullYear(), prev.getMonth() + offset, 1))
  }

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
    if (calendarEnabled) {
      const token = window.localStorage.getItem('bobbeori-token')
      if (!token) {
        navigate('/login')
        return
      }

      const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000'
      await fetch(`${apiUrl}/api/v1/calendar/google/disconnect`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      })
      setCalendarEnabled(false)
      setGoogleCalendarEvents([])
      return
    }

    navigate('/login?calendar=1')
  }

  const toggleCalendarCost = () => {
    setCalendarCostEnabled((prev) => {
      const next = !prev
      window.localStorage.setItem('bobbeori-calendar-cost-enabled', String(next))
      return next
    })
  }

  const deleteSavedRecipe = (recipe) => {
    if (!window.confirm(`${recipe.title} 레시피를 정말 삭제할까요?`)) {
      return
    }

    const token = window.localStorage.getItem('bobbeori-token')
    if (token && recipe.recommendationId) {
      const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000'
      fetch(`${apiUrl}/api/v1/recommendations/${recipe.recommendationId}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      }).catch(() => {})
    }

    const next = removeStoredRecipe(recipe.storageId)
    setSavedRecipes(next)

    const legacy = window.localStorage.getItem('bobbeori-fridge-recipe')
    if (!legacy) return

    try {
      const legacyRecipe = JSON.parse(legacy)
      if (legacyRecipe?.id === recipe.id || legacyRecipe?.id === recipe.recipeId) {
        window.localStorage.removeItem('bobbeori-fridge-recipe')
      }
    } catch {
      window.localStorage.removeItem('bobbeori-fridge-recipe')
    }
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
                      <p>{savedFridgeRecipe ? `저장 후 ${getDaysLeft(selectedRecipe.expiresAt)}일 동안 확인할 수 있어요.` : '저장한 메뉴와 최근 본 레시피를 이어서 확인할 수 있어요.'}</p>
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

          {activeTab === 'saved' && (
            <section className="mypage-panel mypage-saved" aria-labelledby="saved-recipes-title">
              <div className="mypage-panel__title">
                <div>
                  <h2 id="saved-recipes-title">저장된 레시피</h2>
                  <p className="mypage-setting-note">저장한 시점부터 7일 동안 보관돼요.</p>
                </div>
                <button className="mypage-soft-button" type="button" onClick={loadSavedRecipes}>
                  새로고침
                </button>
              </div>

              {savedRecipes.length === 0 ? (
                <div className="mypage-saved-empty">
                  <ImageSlot className="mypage-saved-empty__image" src={imageRecommendation} />
                  <div>
                    <h3>아직 저장된 레시피가 없어요</h3>
                    <p>냉장고파먹기나 메뉴추천에서 마음에 드는 레시피를 저장해보세요.</p>
                    <div className="mypage-saved-empty__actions">
                      <button className="mypage-primary-button" type="button" onClick={() => navigate('/recipe-fridge')}>
                        추천 받으러 가기
                      </button>
                      <button className="mypage-soft-button" type="button" onClick={() => navigate('/recipes')}>
                        레시피 찾으러 가기
                      </button>
                    </div>
                  </div>
                </div>
              ) : (
                [
                  ['추천 레시피', '냉장고파먹기와 메뉴추천에서 저장한 레시피예요.', recommendedSavedRecipes],
                  ['저장한 레시피', '상세 페이지에서 저장해 DB에 기록된 레시피예요.', manuallySavedRecipes],
                ].map(([title, description, recipes]) => (
                  recipes.length > 0 ? (
                    <section className="mypage-saved-section" key={title} aria-label={title}>
                      <div className="mypage-saved-section__head">
                        <h3>{title}</h3>
                        <p>{description}</p>
                      </div>
                      <div className="mypage-saved-list">
                        {recipes.map((recipe) => (
                          <article className="mypage-saved-card" key={recipe.storageId}>
                            <ImageSlot
                              className="mypage-saved-card__image"
                              src={recipe.image || imageRecommendation}
                              alt={recipe.title}
                            />
                            <div className="mypage-saved-card__body">
                              <div className="mypage-recipe-title-row">
                                <h3>{recipe.title}</h3>
                                <span>{recipe.source || recipe.category || '저장 레시피'}</span>
                              </div>
                              <p>{recipe.reason || recipe.description || '저장한 레시피를 이어서 확인할 수 있어요.'}</p>
                              <small>{getDaysLeft(recipe.expiresAt)}일 남음</small>
                              <div className="mypage-recipe-actions">
                                <button className="mypage-primary-button" type="button" onClick={() => navigate(`/recipes/${recipe.recipeId || recipe.id}`)}>
                                  레시피 보기
                                </button>
                                <button className="mypage-soft-button" type="button" onClick={() => deleteSavedRecipe(recipe)}>
                                  삭제
                                </button>
                              </div>
                            </div>
                          </article>
                        ))}
                      </div>
                    </section>
                  ) : null
                ))
              )}
            </section>
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
                    Google Calendar 연동 후 필요한 알림만 자동으로 등록돼요.
                  </p>
                  <ul>
                    <li>
                      <span>소비기한 임박 재료</span>
                      <b>자동 등록</b>
                    </li>
                    <li>
                      <span>오늘의 추천 메뉴</span>
                      <b>자동 등록</b>
                    </li>
                    <li>
                      <span>레시피 삭제 예정 알림</span>
                      <b>자동 등록</b>
                    </li>
                    <li>
                      <span>사용비용 자동 등록</span>
                      <Toggle
                        checked={calendarCostEnabled}
                        label="사용비용 자동 등록"
                        onClick={toggleCalendarCost}
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
                  <p>
                    연동하면 오늘의 재료 알림, 저녁 추천, 레시피 삭제 예정 알림이 자동 등록돼요.
                    사용비용은 OCR 입고 시 설정값에 따라 기록돼요.
                  </p>
                </div>
                <div className="mypage-calendar-connect__actions">
                  <button
                    className="mypage-primary-button"
                    type="button"
                    onClick={connectGoogleCalendar}
                  >
                    {calendarEnabled ? '연동 해제' : 'Google Calendar 연결'}
                  </button>
                </div>
              </section>

              <CalendarPreview
                connected={calendarEnabled}
                events={googleCalendarEvents}
                monthDate={calendarMonth}
                onChangeMonth={changeCalendarMonth}
              />
            </>
          )}

        </div>
      </div>
    </section>
  )
}

export default Mypage
