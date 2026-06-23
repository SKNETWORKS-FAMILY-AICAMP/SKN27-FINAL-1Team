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

const setupSteps = [
  '프로필 확인',
  '알림 설정',
  '오늘 추천 이어가기',
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

function Mypage() {
  const navigate = useNavigate()
  const [alertSettings, setAlertSettings] = useState(alerts)
  const [profileName, setProfileName] = useState(userProfile.name)
  const [profileEmail, setProfileEmail] = useState('babbeori@example.com')
  const [isEditingProfile, setIsEditingProfile] = useState(false)
  const [connectedSocials, setConnectedSocials] = useState(['카카오', '네이버', '구글'])
  const [completedSteps, setCompletedSteps] = useState(['프로필 확인'])
  const [saveMessage, setSaveMessage] = useState('마이페이지 설정을 확인해보세요.')
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
  const activeStepIndex = Math.min(completedSteps.length, setupSteps.length - 1)
  const progressPercent = Math.round((completedSteps.length / setupSteps.length) * 100)
  const activeStep = setupSteps[activeStepIndex]
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

  const completeStep = (step) => {
    setCompletedSteps((prev) => (prev.includes(step) ? prev : [...prev, step]))
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
        const [userDataResponse, summaryResponse] = await Promise.all([
          fetch(`${apiUrl}/api/v1/auth/me`, {
            headers: { Authorization: `Bearer ${token}` },
          }),
          fetch(`${apiUrl}/api/v1/inventory/summary`, {
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
    completeStep('알림 설정')
    setSaveMessage(`${targetLabel} 설정을 변경했어요.`)
  }

  const saveProfile = () => {
    setIsEditingProfile(false)
    completeStep('프로필 확인')
    setSaveMessage('프로필 정보를 저장했어요.')
    window.localStorage.setItem(
      'bobbeori-profile',
      JSON.stringify({ name: profileName, email: profileEmail }),
    )
  }

  const connectSocial = () => {
    const nextSocial = connectedSocials.includes('구글') ? '애플' : '구글'
    setConnectedSocials((prev) => (prev.includes(nextSocial) ? prev : [...prev, nextSocial]))
    setSaveMessage(`${nextSocial} 계정을 연결했어요.`)
  }

  const saveAllSettings = () => {
    completeStep('알림 설정')
    setSaveMessage('알림 설정을 저장했어요.')
    window.localStorage.setItem(
      'bobbeori-mypage-settings',
      JSON.stringify({ alertSettings }),
    )
  }

  const continueRecommendation = () => {
    completeStep('오늘 추천 이어가기')
    navigate('/recipe-fridge')
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

      <section className="mypage-runner" aria-label="마이페이지 설정 진행 상태">
        <div>
          <span>{progressPercent === 100 ? '설정 완료' : `${activeStepIndex + 1}단계 진행 중`}</span>
          <h2>{activeStep}</h2>
          <p>{saveMessage}</p>
        </div>
        <div className="mypage-runner__meter" aria-hidden="true">
          <i style={{ width: `${progressPercent}%` }} />
        </div>
        <strong>{progressPercent}%</strong>
        <button type="button" onClick={saveAllSettings}>설정 저장</button>
      </section>

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

      <div className="mypage-grid">
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
                  onClick={() => {
                    completeStep('오늘 추천 이어가기')
                    navigate(`/recipes/${selectedRecipe.id}`)
                  }}
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

        <section className="mypage-panel mypage-usage" aria-labelledby="usage-title">
          <div className="mypage-subtitle-row">
            <h2 id="usage-title">이용 기록 & 소비 요약</h2>
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

      <section className="mypage-panel mypage-cta">
        <ImageSlot className="mypage-cta__image" src={iconRefrigerator} />
        <div>
          <h2>저장한 추천을 이어서 확인해보세요</h2>
          <p>마음에 든 메뉴와 장보기 목록을 다시 불러올 수 있어요.</p>
        </div>
        <button className="mypage-primary-button" type="button" onClick={continueRecommendation}>
          나에게 맞는 추천 더 보기
        </button>
        <ImageSlot className="mypage-cta__mascot" src={imageMypage} />
      </section>
    </section>
  )
}

export default Mypage
