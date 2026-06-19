import { Link } from 'react-router-dom'
import iconAlarm from '../../../assets/extracted/icons/icon_alarm.png'
import iconBasket from '../../../assets/extracted/icons/icon_basket.png'
import iconReceipt from '../../../assets/extracted/icons/icon_receipt.png'
import iconRefrigerator from '../../../assets/extracted/icons/icon_refrigerator.png'
import imageHero from '../../../assets/extracted/images/image_hero.png'
import mascotChef from '../../../assets/mascot_chef.png'

const quickActions = ['영수증 등록', '냉장고 확인', 'AI 추천', '장보기', '알림 설정']
const serviceFlow = ['재료 등록', '메뉴 추천', '장보기']

const quickActionIconMap = {
  '영수증 등록': iconReceipt,
  '냉장고 확인': iconRefrigerator,
  'AI 추천': mascotChef,
  장보기: iconBasket,
  '알림 설정': iconAlarm,
}

function HeroSection() {
  return (
    <section className="home-hero home-reveal" aria-labelledby="home-title">
      <div className="home-hero__copy">
        <p className="home-eyebrow">냉장고 기반 메뉴 추천</p>
        <h1 id="home-title">
          냉장고 재료로
          <br />
          오늘 먹을 메뉴를
          <br />
          <strong>바로 추천받아요</strong>
        </h1>
        <p className="home-description">
          영수증으로 재료를 넣으면 임박 재료부터 레시피와 장보기를 이어줍니다.
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
            <button className="home-quick-action" type="button" key={action}>
              <span className="image-slot image-slot--quick image-slot--filled" aria-hidden="true">
                <img src={quickActionIconMap[action]} alt="" />
              </span>
              {action}
            </button>
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
