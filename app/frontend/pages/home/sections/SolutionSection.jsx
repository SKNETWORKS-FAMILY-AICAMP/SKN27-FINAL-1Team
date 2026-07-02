import { useEffect, useRef, useState } from 'react'
import iconAlarm from '../../../assets/extracted/icons/icon_alarm.png'
import iconBasket from '../../../assets/extracted/icons/icon_basket.png'
import iconCart from '../../../assets/extracted/icons/icon_cart.png'
import iconReceipt from '../../../assets/extracted/icons/icon_receipt.png'
import iconRefrigerator from '../../../assets/extracted/icons/icon_refrigerator.png'
import iconTime from '../../../assets/extracted/icons/icon_time.png'
import imageAlarm from '../../../assets/extracted/images/image_alarm.png'
import imageEatRefrigerator from '../../../assets/extracted/images/image_eat_refrigerator.png'
import imageGuide from '../../../assets/extracted/images/image_guide.png'
import imageMenuRecommendation from '../../../assets/extracted/images/image_menu_recommendation.png'
import imageMypage from '../../../assets/extracted/images/image_mypage.png'
import imagePutting from '../../../assets/extracted/images/image_putting.png'
import imageReceiptRegistration from '../../../assets/extracted/images/image_receipt registration.png'
import imageSearch from '../../../assets/extracted/images/image_search.png'
import imageShop from '../../../assets/extracted/images/image_shop.png'

const flowSteps = [
  {
    label: '영수증 등록',
    caption: 'OCR 자동 인식',
    icon: iconReceipt,
  },
  {
    label: '냉장고 입고',
    caption: '수량·보관 위치',
    icon: iconRefrigerator,
  },
  {
    label: '소비 임박 확인',
    caption: '유통기한 알림',
    icon: iconTime,
  },
  {
    label: 'AI 메뉴 추천',
    caption: '매칭률과 이유',
    icon: iconBasket,
  },
  {
    label: '부족 재료 장보기',
    caption: '판매처 가격 비교',
    icon: iconCart,
  },
  {
    label: '유통기한 알림',
    caption: '먹기 좋은 타이밍',
    icon: iconAlarm,
  },
]

const features = [
  {
    label: '영수증 OCR',
    icon: imageReceiptRegistration,
    summary: '찍은 영수증에서 구매한 식재료 후보를 자동으로 뽑아냅니다.',
    description: [
      '품목명, 수량, 가격을 분석해 식재료 후보를 정리합니다.',
      '사용자가 확인한 재료만 냉장고에 입고해 잘못 등록되는 항목을 줄입니다.',
      '장 본 직후 재료 등록 과정을 짧게 만들어 냉장고 관리의 시작점을 가볍게 만듭니다.',
    ],
  },
  {
    label: '냉장고',
    icon: imagePutting,
    summary: '보관 중인 재료를 위치, 수량, 유통기한 기준으로 관리합니다.',
    description: [
      '냉장, 냉동, 실온 보관 위치를 나눠 재료 상태를 빠르게 확인합니다.',
      '소비 임박 재료를 우선 표시해 버리기 전에 쓸 수 있게 도와줍니다.',
      '사용한 재료는 소비 처리해 실제 재고와 앱 안의 재고가 어긋나지 않게 유지합니다.',
    ],
  },
  {
    label: '레시피',
    icon: imageSearch,
    summary: '재료명이나 메뉴명으로 필요한 레시피를 바로 찾습니다.',
    description: [
      '필요한 재료, 조리 시간, 인분 정보를 한 화면에서 확인합니다.',
      '냉장고에 있는 재료와 부족한 재료를 비교해 만들 수 있는 정도를 판단합니다.',
      '검색만으로 끝나지 않고 장보기나 냉장고파먹기 추천으로 이어질 수 있게 연결합니다.',
    ],
  },
  {
    label: '냉장고파먹기',
    icon: imageEatRefrigerator,
    summary: '지금 가진 재료로 오늘 만들기 좋은 메뉴를 추천합니다.',
    description: [
      '보유 재료와 소비 임박 재료를 기준으로 추천 우선순위를 잡습니다.',
      '부족한 재료가 적은 레시피를 먼저 보여줘 바로 요리할 가능성을 높입니다.',
      '재료를 남기지 않고 쓰는 방향으로 식비 낭비를 줄이는 데 초점을 둡니다.',
    ],
  },
  {
    label: '메뉴 추천',
    icon: imageMenuRecommendation,
    summary: '무엇을 먹을지 고민될 때 상황에 맞는 후보를 좁혀줍니다.',
    description: [
      '보유 재료, 소비 임박 재료, 부족한 재료를 함께 고려합니다.',
      '간단한 식사, 든든한 한 끼, 처리해야 할 재료처럼 선택 기준을 반영합니다.',
      '추천 이유를 함께 보여줘 사용자가 납득하고 고를 수 있게 만듭니다.',
    ],
  },
  {
    label: '장보기',
    icon: imageShop,
    summary: '부족한 재료를 자동으로 모아 장보기 리스트로 정리합니다.',
    description: [
      '추천 레시피나 메뉴 추천에서 모자란 재료만 따로 모읍니다.',
      '구매처별 가격 비교를 통해 어떤 재료를 어디서 살지 판단할 수 있게 합니다.',
      '직접 요리할 때 배달 대비 얼마나 절약되는지도 함께 확인합니다.',
    ],
  },
  {
    label: '알림',
    icon: imageAlarm,
    summary: '먹어야 할 재료와 확인이 필요한 재료를 놓치지 않게 알려줍니다.',
    description: [
      '유통기한과 소비 시점을 기준으로 오늘 확인할 재료를 구분합니다.',
      '임박 재료, 소비 추천 재료, 확인 필요 재료를 다른 상태로 보여줍니다.',
      'Calendar, Discord, Gmail 등 원하는 채널로 알림을 받을 수 있게 확장합니다.',
    ],
  },
  {
    label: '식재료 가이드',
    icon: imageGuide,
    summary: '식재료를 오래 보관하고 상한 상태를 구분하는 기준을 제공합니다.',
    description: [
      '재료별 보관방법, 손질방법, 세척방법을 함께 안내합니다.',
      '냉장, 냉동, 실온 중 어떤 방식이 맞는지 빠르게 확인할 수 있습니다.',
      '신선도 확인법과 상한 상태 기준을 제공해 잘못된 보관으로 인한 낭비를 줄입니다.',
    ],
  },
  {
    label: '마이페이지',
    icon: imageMypage,
    summary: '추천 기준과 알림 설정을 저장해 개인화된 식단 흐름을 만듭니다.',
    description: [
      '소셜 로그인 계정, 알림 채널, 마케팅 수신 여부를 관리합니다.',
      '냉장고 기반 추천 사용 여부와 절약 표시 여부를 설정합니다.',
      '취향과 생활 패턴을 반영해 더 잘 맞는 추천을 받을 수 있게 합니다.',
    ],
  },
]

const recommendationScores = [
  { label: '보유 재료 매칭', value: 93 },
  { label: '소비 임박 우선', value: 88 },
  { label: '취향 적합도', value: 81 },
  { label: '부족 재료 최소화', value: 90 },
]

const recommendationReasons = [
  '보유 재료를 최대한 활용',
  '유통기한이 가까운 재료 우선',
  '사용자 취향과 조리 시간 반영',
  '추가 구매 품목과 비용 최소화',
]

function SolutionSection() {
  const dragStartXRef = useRef(null)
  const [activeFeatureIndex, setActiveFeatureIndex] = useState(0)
  const [isFeatureResetting, setIsFeatureResetting] = useState(false)
  const featureSlides = [...features, features[0]]

  const moveFeature = (direction) => {
    setActiveFeatureIndex((current) => {
      if (direction > 0) return current >= features.length ? 1 : current + 1
      return current === 0 ? features.length - 1 : current - 1
    })
  }

  const resetFeatureLoop = () => {
    setIsFeatureResetting(true)
    setActiveFeatureIndex(0)
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => setIsFeatureResetting(false))
    })
  }

  const handleFeaturePointerDown = (event) => {
    dragStartXRef.current = event.clientX
    event.currentTarget.setPointerCapture?.(event.pointerId)
  }

  const handleFeaturePointerUp = (event) => {
    if (dragStartXRef.current === null) return

    const dragDistance = event.clientX - dragStartXRef.current
    dragStartXRef.current = null

    if (Math.abs(dragDistance) < 48) return
    moveFeature(dragDistance < 0 ? 1 : -1)
  }

  const handleFeaturePointerCancel = () => {
    dragStartXRef.current = null
  }

  const handleFeatureTransitionEnd = () => {
    if (activeFeatureIndex < features.length) return
    resetFeatureLoop()
  }

  useEffect(() => {
    const timer = window.setInterval(() => {
      setActiveFeatureIndex((current) => (current >= features.length ? 1 : current + 1))
    }, 5200)

    return () => window.clearInterval(timer)
  }, [])

  useEffect(() => {
    if (activeFeatureIndex < features.length) return undefined

    const fallbackTimer = window.setTimeout(resetFeatureLoop, 700)
    return () => window.clearTimeout(fallbackTimer)
  }, [activeFeatureIndex])

  return (
    <section className="home-section home-solution home-reveal" aria-label="밥벌이 해결 방식">
      <div className="home-flow">
        <div className="home-flow__heading">
          <div>
            <p>한 번에 이어지는 식사 준비</p>
            <h2>밥벌이는 이렇게 해결해요</h2>
          </div>
          <span>등록부터 조리, 장보기, 알림까지 서로 연결된 흐름으로 식재료 낭비를 줄입니다.</span>
        </div>
        <div className="home-flow__steps">
          {flowSteps.map((step, index) => (
            <div className="home-flow__item" key={step.label}>
              <span className="image-slot image-slot--flow image-slot--filled" aria-hidden="true">
                <img src={step.icon} alt="" />
              </span>
              <strong>{step.label}</strong>
              <small>{step.caption}</small>
              {index < flowSteps.length - 1 && <i aria-hidden="true" />}
            </div>
          ))}
        </div>
      </div>

      <div className="home-solution__bottom">
        <div className="home-feature-block">
          <div className="home-feature-header">
            <div>
              <p>서비스 흐름</p>
              <h2>밥벌이가 도와주는 일</h2>
            </div>
            <div className="home-feature-header__side">
              <span>재료 등록부터 추천, 장보기, 식재료 가이드까지 식재료를 쓰는 전 과정을 한 흐름으로 연결합니다.</span>
              <div className="home-feature-controls" aria-label="밥벌이가 도와주는 일 슬라이드 이동">
                <button type="button" aria-label="이전 도움 항목" onClick={() => moveFeature(-1)}>
                  &lt;
                </button>
                <button type="button" aria-label="다음 도움 항목" onClick={() => moveFeature(1)}>
                  &gt;
                </button>
              </div>
            </div>
          </div>

          <div
            className={`home-feature-slider ${isFeatureResetting ? 'is-resetting' : ''}`}
            tabIndex={0}
            onPointerDown={handleFeaturePointerDown}
            onPointerUp={handleFeaturePointerUp}
            onPointerCancel={handleFeaturePointerCancel}
            onPointerLeave={handleFeaturePointerCancel}
          >
            <div
              className="home-feature-track"
              style={{ transform: `translateX(-${activeFeatureIndex * 100}%)` }}
              onTransitionEnd={handleFeatureTransitionEnd}
            >
              {featureSlides.map((feature, index) => {
                const displayIndex = index % features.length

                return (
                  <section
                    className={`home-feature-section ${activeFeatureIndex % features.length === displayIndex ? 'is-active' : ''}`}
                    key={`${feature.label}-${index}`}
                    aria-hidden={activeFeatureIndex % features.length === displayIndex ? undefined : 'true'}
                  >
                    <div className="home-feature-section__image image-slot image-slot--feature image-slot--filled" aria-hidden="true">
                      <img src={feature.icon} alt="" />
                    </div>
                    <div className="home-feature-section__text">
                      <span>{String(displayIndex + 1).padStart(2, '0')}</span>
                    <h3>{feature.label}</h3>
                    <p className="home-feature-summary">{feature.summary}</p>
                    <ul>
                      {feature.description.map((line) => (
                        <li key={line}>{line}</li>
                      ))}
                    </ul>
                    </div>
                  </section>
                )
              })}
            </div>
          </div>
        </div>

        <div className="home-ai-block">
          <div className="home-ai-heading">
            <div>
              <p>설명 가능한 추천</p>
              <h2>
                AI가 왜 이 메뉴를 골랐는지
                <br />
                추천 이유까지 보여줘요
              </h2>
            </div>
            <span>단순 인기순이 아니라 재료, 유통기한, 구매량, 취향을 함께 계산합니다.</span>
          </div>

          <div className="home-ai-grid">
            <article className="home-ai-quote">
              <span aria-hidden="true">“</span>
              <h3>
                대파가 D-1이라 오늘 먼저 쓰고,
                <br />
                냉장고 재료 7개로 만들 수 있는
                <strong>대파 두부 계란찌개</strong>를 추천했어요.
              </h3>
              <div>
                <em>대파 D-1</em>
                <em>보유 재료 7/10</em>
                <em>20분 완성</em>
                <em>매운맛 낮음</em>
              </div>
            </article>

            <article className="home-ai-score">
              <h3>추천 점수 구성</h3>
              <div className="home-ai-score__list">
                {recommendationScores.map((score) => (
                  <div className="home-ai-score__row" key={score.label}>
                    <span>{score.label}</span>
                    <i aria-hidden="true">
                      <b style={{ width: `${score.value}%` }} />
                    </i>
                    <strong>{score.value}</strong>
                  </div>
                ))}
              </div>
              <ul>
                {recommendationReasons.map((reason) => (
                  <li key={reason}>{reason}</li>
                ))}
              </ul>
            </article>
          </div>
        </div>
      </div>
    </section>
  )
}

export default SolutionSection
