import { Link } from 'react-router-dom'
import iconAlarm from '../../../assets/extracted/icons/icon_alarm.png'
import iconBasket from '../../../assets/extracted/icons/icon_basket.png'
import iconReceipt from '../../../assets/extracted/icons/icon_receipt.png'
import iconRefrigerator from '../../../assets/extracted/icons/icon_refrigerator.png'
import imageHero from '../../../assets/extracted/images/image_hero.png'
import mascotChef from '../../../assets/mascot_chef.png'
import { serviceContext, userProfile } from '../../../data/userService.js'

const quickActions = ['영수증 등록', '냉장고 확인', 'AI 추천', '장보기', '알림 설정']
const serviceFlow = ['냉장고 확인', '맞춤 메뉴', '예산 장보기']

const quickActionIconMap = {
  '영수증 등록': iconReceipt,
  '냉장고 확인': iconRefrigerator,
  'AI 추천': mascotChef,
  장보기: iconBasket,
  '알림 설정': iconAlarm,
}

const quickActionPathMap = {
  '영수증 등록': '/receipt-ocr',
  '냉장고 확인': '/fridge',
  'AI 추천': '/recipe-fridge',
  장보기: '/shopping-list',
  '알림 설정': '/mypage',
}

function HeroSection() {
  return (
    <section className="home-hero home-reveal" aria-labelledby="home-title">
      <div className="home-hero__copy">
        <p className="home-eyebrow">{userProfile.household} 맞춤 식비 관리</p>
        <h1 id="home-title">
          {userProfile.mealTarget} 메뉴부터
          <br />
          장보기 예산까지
          <br />
          <strong>한 번에 맞춰드려요</strong>
        </h1>
        <p className="home-description">
          {serviceContext.fridgeMatch} 매칭 레시피를 기준으로 부족 재료만 골라
          {userProfile.budgetLabel} 안에서 장보기까지 이어줍니다.
        </p>
        <div className="home-service-flow" aria-label="밥벌이 서비스 흐름">
          {serviceFlow.map((step) => (
            <span key={step}>{step}</span>
          ))}
        </div>
        <div className="home-mobile-hero-art image-slot image-slot--mobile-hero image-slot--filled" aria-hidden="true">
          <img src={imageHero} alt="" />
        </div>
        <div className="home-hero__actions">
          <Link className="home-button home-button--primary" to="/fridge">
            시작하기
          </Link>
          <Link className="home-button home-button--secondary" to="/recipes">
            레시피 보기
          </Link>
        </div>
        <div className="home-quick-actions" aria-label="빠른 메뉴">
          {quickActions.map((action) => (
            <Link className="home-quick-action" to={quickActionPathMap[action]} key={action}>
              <span className="image-slot image-slot--quick image-slot--filled" aria-hidden="true">
                <img src={quickActionIconMap[action]} alt="" />
              </span>
              {action}
            </Link>
          ))}
        </div>
      </div>

      <div className="home-hero__visual" aria-label="밥벌이 서비스 대표 이미지">
        <div className="home-hero__image image-slot image-slot--hero-main image-slot--filled" aria-hidden="true">
          <img src={imageHero} alt="" />
        </div>
      </div>
    </section>
  )
}

export default HeroSection
