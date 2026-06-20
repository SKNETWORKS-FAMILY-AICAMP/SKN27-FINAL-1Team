import React, { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import './Mypage.css'

import iconAlarm from '../../assets/extracted/icons/icon_alarm.png'
import iconBasket from '../../assets/extracted/icons/icon_basket.png'
import iconCart from '../../assets/extracted/icons/icon_cart.png'
import iconRefrigerator from '../../assets/extracted/icons/icon_refrigerator.png'
import imageMypage from '../../assets/extracted/images/image_mypage.png'
import imageRecommendation from '../../assets/extracted/images/image_recommendation.png'
import { serviceBadges, serviceContext, userProfile } from '../../data/userService.js'

const stats = [
  { label: '보유 재료', value: '28개', note: '냉장 18 · 냉동 7 · 임박 3', image: iconRefrigerator },
  { label: '추천 횟수', value: '24회', note: '이번 달 기준', image: iconAlarm },
  { label: '절약 금액', value: serviceContext.savedThisMonth, note: '직접 요리 기준', image: iconBasket },
  { label: '이번 장보기', value: '15,690원', note: `${serviceContext.selectedMarket} 최저가`, image: iconCart },
]

const settings = [
  { label: '소비 임박 재료 우선 추천', checked: true },
  { label: '매운맛 선호', checked: false },
  { label: '1인분 위주 추천', checked: true },
  { label: '알레르기 재료 제외', checked: true },
]

const alerts = [
  { label: '소비 임박 알림', checked: true },
  { label: '장보기 가격 변동 알림', checked: true },
  { label: '추천 레시피 알림', checked: false },
  { label: 'OCR 입고 완료 알림', checked: true },
]

const recentRecipes = [
  { title: '버섯 들깨탕', meta: '25분 · 매칭률 86%' },
  { title: '김치 참치 볶음밥', meta: '15분 · 매칭률 78%' },
]

const cartHistory = [
  { date: '2024.05.20', price: '11,140원' },
  { date: '2024.05.16', price: '8,400원' },
  { date: '2024.05.12', price: '7,380원' },
]

const setupSteps = [
  '프로필 확인',
  '추천 기준 설정',
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
  const [personalSettings, setPersonalSettings] = useState(settings)
  const [alertSettings, setAlertSettings] = useState(alerts)
  const [profileName, setProfileName] = useState(userProfile.name)
  const [profileEmail, setProfileEmail] = useState('babbeori@example.com')
  const [isEditingProfile, setIsEditingProfile] = useState(false)
  const [connectedSocials, setConnectedSocials] = useState(['카카오', '네이버'])
  const [completedSteps, setCompletedSteps] = useState(['프로필 확인'])
  const [saveMessage, setSaveMessage] = useState('추천 기준이 서비스에 반영되어 있어요.')
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

  const completeStep = (step) => {
    setCompletedSteps((prev) => (prev.includes(step) ? prev : [...prev, step]))
  }

  const handleLogout = () => {
    window.localStorage.removeItem('bobbeori-auth-mode')
    window.dispatchEvent(new Event('bobbeori-auth-change'))
    navigate('/login')
  }

  const toggleSetting = (targetLabel) => {
    setPersonalSettings((prev) =>
      prev.map((setting) =>
        setting.label === targetLabel ? { ...setting, checked: !setting.checked } : setting,
      ),
    )
    completeStep('추천 기준 설정')
    setSaveMessage(`${targetLabel} 설정을 변경했어요.`)
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
    completeStep('추천 기준 설정')
    completeStep('알림 설정')
    setSaveMessage('마이페이지 설정을 저장했어요.')
    window.localStorage.setItem(
      'bobbeori-mypage-settings',
      JSON.stringify({ personalSettings, alertSettings }),
    )
  }

  const continueRecommendation = () => {
    completeStep('오늘 추천 이어가기')
    navigate('/recipe-fridge')
  }

  return (
    <section className="mypage" aria-labelledby="mypage-title">
      <div className="mypage-hero">
        <div>
          <h1 id="mypage-title">내 맞춤 서비스</h1>
          <p>
            {userProfile.household}, {userProfile.budgetLabel}, {userProfile.cookTime} 기준으로
            추천과 장보기를 조정하고 있어요.
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
              <h2>{isGuest ? '게스트님' : profileName}</h2>
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
            <p>{isGuest ? 'guest@bobbeori.com' : profileEmail}</p>
          )}
          <small>{isGuest ? '게스트 모드 이용 중' : '가입일 2024. 05. 22'}</small>
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
            {connectedSocials.map((social) => (
              <span
                className={`mypage-social__pill ${
                  social === '카카오' ? 'mypage-social__pill--kakao' : 'mypage-social__pill--naver'
                }`}
                key={social}
              >
                {social}
              </span>
            ))}
            <button
              className="mypage-connect-button"
              type="button"
              onClick={connectSocial}
            >
              + 연결하기
            </button>
          </div>
        </div>
      </section>

      <div className="mypage-stats" aria-label="마이페이지 통계">
        {stats.map((stat, index) => (
          <button
            className="mypage-panel mypage-stat"
            key={stat.label}
            type="button"
            onClick={() => navigate(index === 0 ? '/fridge' : index === 3 ? '/shopping-list' : '/recipe-fridge')}
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
                <h3>{serviceContext.selectedRecipe}</h3>
                <span>{serviceContext.fridgeMatch} 매칭</span>
              </div>
              <p>{userProfile.cookTime} · {userProfile.taste} · {userProfile.priority}</p>
              <p>{serviceBadges.join(' · ')}</p>
              <div className="mypage-recipe-actions">
                <button
                  className="mypage-primary-button"
                  type="button"
                  onClick={() => {
                    completeStep('오늘 추천 이어가기')
                    navigate('/recipes/green-onion-tofu-egg-stew')
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

        <section className="mypage-panel mypage-settings" aria-labelledby="settings-title">
          <h2 id="settings-title">추천 기준</h2>
          <ul>
            {personalSettings.map((setting) => (
              <li key={setting.label}>
                <span>{setting.label}</span>
                <Toggle
                  checked={setting.checked}
                  label={setting.label}
                  onClick={() => toggleSetting(setting.label)}
                />
              </li>
            ))}
          </ul>
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
          <h2>더 똑똑한 추천으로 식탁을 더 알차게!</h2>
          <p>{userProfile.mealTarget} 기준으로 부족 재료와 예산을 다시 계산해볼게요.</p>
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
