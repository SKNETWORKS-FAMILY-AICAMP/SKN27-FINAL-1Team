import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import './Mypage.css'

import iconAlarm from '../../assets/extracted/icons/icon_alarm.png'
import iconBasket from '../../assets/extracted/icons/icon_basket.png'
import iconCart from '../../assets/extracted/icons/icon_cart.png'
import iconRefrigerator from '../../assets/extracted/icons/icon_refrigerator.png'
import imageMypage from '../../assets/extracted/images/image_mypage.png'
import imageRecommendation from '../../assets/extracted/images/image_recommendation.png'

const stats = [
  { label: '보유 재료', value: '28개', note: '냉장 18 · 냉동 7 · 임박 3', image: iconRefrigerator },
  { label: '추천 횟수', value: '24회', note: '이번 달 기준', image: iconAlarm },
  { label: '절약 금액', value: '48,700원', note: '직접 요리 기준', image: iconBasket },
  { label: '사용 금액', value: '31,200원', note: '이번 달 장보기', image: iconCart },
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

function ImageSlot({ src, alt = '', className = '' }) {
  return (
    <span className={`mypage-image-slot ${src ? 'is-filled' : ''} ${className}`}>
      {src ? <img src={src} alt={alt} /> : null}
    </span>
  )
}

function Toggle({ checked }) {
  return <span className={`mypage-toggle ${checked ? 'is-on' : ''}`} aria-hidden="true" />
}

function Mypage() {
  const navigate = useNavigate()
  const authMode =
    typeof window === 'undefined' ? null : window.localStorage.getItem('bobbeori-auth-mode')
  const isGuest = authMode === 'guest'
  const [userData, setUserData] = useState(null)

  useEffect(() => {
    if (isGuest) return

    const fetchUser = async () => {
      const token = window.localStorage.getItem('bobbeori-token')
      if (!token) {
        navigate('/login')
        return
      }

      try {
        const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000'
        const response = await fetch(`${apiUrl}/api/v1/auth/me`, {
          headers: {
            Authorization: `Bearer ${token}`
          }
        })
        if (!response.ok) throw new Error('인증 실패')
        
        const data = await response.json()
        setUserData(data)
      } catch (err) {
        console.error(err)
        window.localStorage.removeItem('bobbeori-token')
        window.localStorage.removeItem('bobbeori-auth-mode')
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

  return (
    <section className="mypage" aria-labelledby="mypage-title">
      <div className="mypage-hero">
        <div>
          <h1 id="mypage-title">마이페이지</h1>
          <p>내 정보와 이용 기록을 한눈에 확인하고, 개인 설정을 관리해요!</p>
        </div>
        <ImageSlot className="mypage-hero__image" src={imageMypage} />
      </div>

      <section className="mypage-panel mypage-profile" aria-label="회원 정보">
        <ImageSlot className="mypage-profile__avatar" src={imageMypage} />
        <div className="mypage-profile__info">
          <div className="mypage-profile__name">
            <h2>{isGuest ? '게스트님' : (userData ? `${userData.nickname}님` : '불러오는 중...')}</h2>
            <span>{isGuest ? '게스트' : '일반 회원'}</span>
          </div>
          <p>{isGuest ? 'guest@bobbeori.com' : (userData?.email || '이메일 정보 없음')}</p>
          <small>{isGuest ? '게스트 모드 이용 중' : (userData ? `가입일 ${new Date(userData.created_at).toLocaleDateString()}` : '')}</small>
          <div className="mypage-profile__actions">
            <button className="mypage-primary-button" type="button">
              프로필 수정
            </button>
            <button className="mypage-soft-button" type="button" onClick={handleLogout}>
              로그아웃
            </button>
          </div>
        </div>
        <div className="mypage-social">
          <strong>소셜 로그인 정보</strong>
          <div>
            <span className={`mypage-social__pill mypage-social__pill--kakao ${userData?.provider === 'kakao' ? 'is-active' : ''}`}>카카오</span>
            <span className={`mypage-social__pill mypage-social__pill--naver ${userData?.provider === 'naver' ? 'is-active' : ''}`}>네이버</span>
            <span className={`mypage-social__pill mypage-social__pill--google ${userData?.provider === 'google' ? 'is-active' : ''}`}>구글</span>
          </div>
        </div>
      </section>

      <div className="mypage-stats" aria-label="마이페이지 통계">
        {stats.map((stat) => (
          <article className="mypage-panel mypage-stat" key={stat.label}>
            <div>
              <span>{stat.label}</span>
              <strong>{stat.value}</strong>
              <p>{stat.note}</p>
            </div>
            <ImageSlot className="mypage-stat__image" src={stat.image} />
          </article>
        ))}
      </div>

      <div className="mypage-grid">
        <section className="mypage-panel mypage-recipe" aria-labelledby="selected-recipe-title">
          <div className="mypage-panel__title">
            <h2 id="selected-recipe-title">선택된 레시피 정보</h2>
          </div>
          <article className="mypage-selected-recipe">
            <ImageSlot className="mypage-selected-recipe__image" src={imageRecommendation} />
            <div>
              <div className="mypage-recipe-title-row">
                <h3>대파 두부 계란찌개</h3>
                <span>추천 레시피</span>
              </div>
              <p>20분 · 난이도 쉬움 · 매칭률 92%</p>
              <p>보유 재료 7/10</p>
              <div className="mypage-recipe-actions">
                <button className="mypage-primary-button" type="button">
                  레시피 보기
                </button>
                <button className="mypage-soft-button" type="button">
                  장보기 이동
                </button>
              </div>
            </div>
          </article>

          <div className="mypage-recent">
            <div className="mypage-subtitle-row">
              <strong>최근 선택 레시피</strong>
              <button type="button">전체 보기</button>
            </div>
            <div className="mypage-recent-list">
              {recentRecipes.map((recipe) => (
                <article key={recipe.title}>
                  <ImageSlot className="mypage-recent__image" />
                  <div>
                    <h3>{recipe.title}</h3>
                    <p>{recipe.meta}</p>
                  </div>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="mypage-panel mypage-settings" aria-labelledby="settings-title">
          <h2 id="settings-title">개인화 설정</h2>
          <ul>
            {settings.map((setting) => (
              <li key={setting.label}>
                <span>{setting.label}</span>
                <Toggle checked={setting.checked} />
              </li>
            ))}
          </ul>
        </section>

        <section className="mypage-panel mypage-settings" aria-labelledby="alerts-title">
          <h2 id="alerts-title">알림 설정</h2>
          <ul>
            {alerts.map((alert) => (
              <li key={alert.label}>
                <span>{alert.label}</span>
                <Toggle checked={alert.checked} />
              </li>
            ))}
          </ul>
        </section>

        <section className="mypage-panel mypage-usage" aria-labelledby="usage-title">
          <div className="mypage-subtitle-row">
            <h2 id="usage-title">이용 기록 & 소비 요약</h2>
            <button type="button">전체 보기</button>
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
          <p>나만을 위한 맞춤 추천을 더 확인해보세요.</p>
        </div>
        <button className="mypage-primary-button" type="button">
          나에게 맞는 추천 더 보기
        </button>
        <ImageSlot className="mypage-cta__mascot" src={imageMypage} />
      </section>
    </section>
  )
}

export default Mypage
