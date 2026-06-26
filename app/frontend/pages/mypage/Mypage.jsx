import React, { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import './Mypage.css'

import imageMypage from '../../assets/extracted/images/image_mypage.png'
import imageRecommendation from '../../assets/extracted/images/image_recommendation.png'
import OnboardingModal from '../../components/OnboardingModal.jsx'
import ConfirmModal from '../../components/modals/ConfirmModal'
import { userProfile } from '../../mock/userService.js'
import { readStoredRecipes, removeStoredRecipe, saveStoredRecipe } from '../../utils/savedRecipes.js'

const alerts = [
  { label: '소비 임박 알림', checked: true },
  { label: '오늘의 추천 메뉴', checked: true },
  { label: '레시피 삭제 예정 알림', checked: true },
]

const toLocalDateKey = (date) => {
  const localDate = new Date(date.getTime() - date.getTimezoneOffset() * 60000)
  return localDate.toISOString().slice(0, 10)
}

const readOnboardingSettings = () => {
  if (typeof window === 'undefined') {
    return { allergy: [], disliked_ingredients: [], preferred_ingredients: [] }
  }

  try {
    return JSON.parse(window.localStorage.getItem('bobbeori-onboarding-settings')) || {
      allergy: [],
      disliked_ingredients: [],
      preferred_ingredients: [],
    }
  } catch {
    return { allergy: [], disliked_ingredients: [], preferred_ingredients: [] }
  }
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
  const { search } = useLocation()
  const initialTab = new URLSearchParams(search).get('tab')
  const [alertSettings, setAlertSettings] = useState(alerts)
  const [activeTab, setActiveTab] = useState(tabs.some((tab) => tab.id === initialTab) ? initialTab : 'profile')
  const [calendarEnabled, setCalendarEnabled] = useState(false)
  const [googleCalendarEvents, setGoogleCalendarEvents] = useState([])
  const [calendarMonth, setCalendarMonth] = useState(() => new Date())
  const [deleteTarget, setDeleteTarget] = useState(null)
  const [showOnboarding, setShowOnboarding] = useState(false)
  const [onboardingSettings, setOnboardingSettings] = useState(readOnboardingSettings)
  const [calendarCostEnabled, setCalendarCostEnabled] = useState(() =>
    typeof window === 'undefined'
      ? true
      : window.localStorage.getItem('bobbeori-calendar-cost-enabled') !== 'false',
  )
  const [profileName, setProfileName] = useState(userProfile.name)
  const [profileEmail, setProfileEmail] = useState('babbeori@example.com')
  const [isEditingProfile, setIsEditingProfile] = useState(false)
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
  const recommendedSavedRecipes = useMemo(
    () => savedRecipes.filter((recipe) => recipe.savedType !== 'saved'),
    [savedRecipes],
  )
  const manuallySavedRecipes = useMemo(
    () => savedRecipes.filter((recipe) => recipe.savedType === 'saved'),
    [savedRecipes],
  )

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
    const tab = new URLSearchParams(search).get('tab')
    setActiveTab(tabs.some((item) => item.id === tab) ? tab : 'profile')
  }, [search])

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
    setDeleteTarget(null)

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
  const provider = isGuest ? 'guest' : userData?.provider
  const providerLabel = {
    kakao: '카카오',
    naver: '네이버',
    google: '구글',
    guest: '게스트',
  }[provider] || '소셜 로그인'
  const providerClass =
    provider === 'kakao'
      ? 'mypage-social__pill--kakao'
      : provider === 'naver'
        ? 'mypage-social__pill--naver'
        : 'mypage-social__pill--google'

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
              onClick={() => navigate(tab.id === 'profile' ? '/mypage' : `/mypage?tab=${tab.id}`)}
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
                  <strong>로그인 방식</strong>
                  <div>
                    <span className={`mypage-social__pill ${providerClass} is-active`}>
                      {providerLabel}
                    </span>
                  </div>
                </div>
              </section>

              <div className="mypage-info-grid">
                <section className="mypage-panel mypage-account-info" aria-labelledby="account-info-title">
                  <div className="mypage-panel__title">
                    <h2 id="account-info-title">계정 정보</h2>
                  </div>
                  <dl>
                    <div><dt>이메일</dt><dd>{profileDisplayEmail}</dd></div>
                    <div><dt>로그인 방식</dt><dd>{providerLabel}</dd></div>
                    <div><dt>회원 유형</dt><dd>{isGuest ? '게스트' : '일반 회원'}</dd></div>
                    <div><dt>가입일</dt><dd>{profileCreatedAt.replace('가입일 ', '')}</dd></div>
                    <div><dt>캘린더 연동</dt><dd>{calendarEnabled ? '연결됨' : '미연결'}</dd></div>
                    <div><dt>보유 재료</dt><dd>{inventorySummary.total}개</dd></div>
                  </dl>
                </section>

                <section className="mypage-panel mypage-preferences" aria-labelledby="preferences-title">
                  <div className="mypage-panel__title">
                    <h2 id="preferences-title">나의 식재료 설정</h2>
                  </div>
                  {[
                    ['알레르기', onboardingSettings.allergy],
                    ['비선호 재료', onboardingSettings.disliked_ingredients],
                    ['선호 재료', onboardingSettings.preferred_ingredients],
                  ].map(([title, items]) => (
                    <div className="mypage-preference-group" key={title}>
                      <strong>{title}</strong>
                      <div className="mypage-preference-chips">
                        {items?.length ? (
                          items.map((item) => <span key={`${title}-${item}`}>{item}</span>)
                        ) : (
                          <em>설정된 재료가 없어요</em>
                        )}
                      </div>
                    </div>
                  ))}
                  <button
                    className="mypage-soft-button mypage-preferences__reset"
                    type="button"
                    onClick={() => setShowOnboarding(true)}
                  >
                    다시 설정하기
                  </button>
                </section>
              </div>

              <section className="mypage-panel mypage-settings" aria-labelledby="onboarding-title">
                <h2 id="onboarding-title">맞춤 설정</h2>
                <p className="mypage-setting-note">알레르기, 비선호 재료, 선호 재료를 다시 설정해요.</p>
                <button className="mypage-primary-button mypage-onboarding-button" type="button" onClick={() => setShowOnboarding(true)}>
                  온보딩 다시 하기
                </button>
              </section>
            </>
          )}

          {activeTab === 'saved' && (
            <section className="mypage-panel mypage-saved" aria-labelledby="saved-recipes-title">
              <div className="mypage-panel__title">
                <div>
                  <h2 id="saved-recipes-title">저장된 레시피 <span>7일 보관</span></h2>
                </div>
              </div>

              <div className="mypage-saved-grid">
                {[
                  ['추천 레시피', recommendedSavedRecipes, '/recipe-fridge', '추천 받으러 가기'],
                  ['저장한 레시피', manuallySavedRecipes, '/recipes', '레시피 찾으러 가기'],
                ].map(([title, recipes, actionPath, actionLabel]) => (
                  <section className="mypage-saved-section" key={title} aria-label={title}>
                    <div className="mypage-saved-section__head">
                      <h3>{title}</h3>
                    </div>
                    {recipes.length > 0 ? (
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
                                <small>{getDaysLeft(recipe.expiresAt)}일 남음</small>
                              </div>
                              <div className="mypage-recipe-actions">
                                <button className="mypage-primary-button" type="button" onClick={() => navigate(`/recipes/${recipe.recipeId || recipe.id}`)}>
                                  레시피 보기
                                </button>
                                <button className="mypage-soft-button" type="button" onClick={() => setDeleteTarget(recipe)}>
                                  삭제
                                </button>
                              </div>
                            </div>
                          </article>
                        ))}
                      </div>
                    ) : (
                      <div className="mypage-saved-column-empty">
                        <ImageSlot className="mypage-saved-empty__image" src={imageRecommendation} />
                        <h3>{title}가 없어요</h3>
                        <p>{title === '추천 레시피' ? '추천 화면에서 마음에 드는 메뉴를 저장해보세요.' : '레시피 상세에서 저장하면 여기에 모여요.'}</p>
                        <button className="mypage-primary-button" type="button" onClick={() => navigate(actionPath)}>
                          {actionLabel}
                        </button>
                      </div>
                    )}
                  </section>
                ))}
              </div>
            </section>
          )}

          {activeTab === 'alerts' && (
            <>
              <div className="mypage-alert-calendar">
                <section className="mypage-panel mypage-settings" aria-labelledby="alerts-title">
                  <h2 id="alerts-title">서비스 알림</h2>
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
                    <li>
                      <span>사용비용 자동 등록</span>
                      <Toggle
                        checked={calendarCostEnabled}
                        label="사용비용 자동 등록"
                        onClick={toggleCalendarCost}
                      />
                    </li>
                  </ul>
                </section>

                <section className="mypage-panel mypage-calendar-connect" aria-labelledby="google-calendar-title">
                  <div>
                    <h2 id="google-calendar-title">Google Calendar 연결</h2>
                    <p>연동하면 필요한 알림과 사용비용 기록을 캘린더에 자동 등록해요.</p>
                    <ul className="mypage-calendar-connect__list">
                      <li>소비 임박 재료는 아침에 확인할 수 있어요.</li>
                      <li>저녁 추천 메뉴와 레시피 삭제 예정일을 놓치지 않아요.</li>
                      <li>OCR 입고 비용은 사용비용 기록으로 남길 수 있어요.</li>
                    </ul>
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
              </div>

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
      <ConfirmModal
        isOpen={Boolean(deleteTarget)}
        title="레시피 삭제"
        message={deleteTarget ? (
          <>
            <span style={{ color: 'var(--figma-coral)', fontWeight: 900, fontSize: '18px' }}>
              {deleteTarget.title}
            </span>을(를)<br />
            저장된 레시피에서 삭제하시겠습니까?
          </>
        ) : null}
        onConfirm={() => deleteTarget && deleteSavedRecipe(deleteTarget)}
        onClose={() => setDeleteTarget(null)}
      />
      {showOnboarding && (
        <OnboardingModal
          onClose={() => {
            setShowOnboarding(false)
            setOnboardingSettings(readOnboardingSettings())
          }}
        />
      )}
    </section>
  )
}

export default Mypage
