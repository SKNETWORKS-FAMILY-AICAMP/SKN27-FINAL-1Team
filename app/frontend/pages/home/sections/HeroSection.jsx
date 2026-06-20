import { Link } from 'react-router-dom'
import iconAlarm from '../../../assets/extracted/icons/icon_alarm.png'
import iconBasket from '../../../assets/extracted/icons/icon_basket.png'
import iconReceipt from '../../../assets/extracted/icons/icon_receipt.png'
import iconRefrigerator from '../../../assets/extracted/icons/icon_refrigerator.png'
import imageHero from '../../../assets/extracted/images/image_hero.png'
import mascotChef from '../../../assets/mascot_chef.png'
const quickActions = ['영수증 등록', '냉장고 확인', 'AI 추천', '장보기', '알림 설정']

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
        <p className="home-eyebrow">밥벌이 AI 식단 도우미</p>
        <h1 id="home-title">
          냉장고 재료를
          <br />
          <strong>오늘의 한 끼</strong>로
          <br />
          바꿔요
        </h1>
        <p className="home-description">
          영수증으로 재료를 등록하고, 소비 임박 식재료부터 맛있게 쓰는 레시피를
          추천받으세요. 부족한 재료는 최저가 장보기까지 한 번에 연결됩니다.
        </p>
        <div className="home-mobile-hero-art image-slot image-slot--mobile-hero image-slot--filled" aria-hidden="true">
          <img src={imageHero} alt="" />
        </div>
        <div className="home-hero__actions">
          <Link className="home-button home-button--primary" to="/receipt-ocr">
            무료로 시작하기
          </Link>
          <Link className="home-button home-button--secondary" to="/recipes">
            서비스 둘러보기
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
