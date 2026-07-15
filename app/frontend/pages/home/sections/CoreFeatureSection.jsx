import iconCart from '../../../assets/extracted/icons/icon_cart.png'
import iconReceipt from '../../../assets/extracted/icons/icon_receipt.png'
import iconRefrigerator from '../../../assets/extracted/icons/icon_refrigerator.png'
import mascotChef from '../../../assets/mascot_chef.webp'

const coreFeatures = [
  {
    tag: 'Receipt OCR',
    title: '영수증을 찍으면 재료와 가격이 자동 등록',
    description: '품목명, 수량, 구매일, 가격을 인식해 냉장고 목록을 빠르게 채웁니다.',
    icon: iconReceipt,
  },
  {
    tag: 'Inventory',
    title: '보관 위치와 소비 임박을 한눈에 관리',
    description: '냉장·냉동·상온 분류와 소비기한 우선순위로 재료를 놓치지 않습니다.',
    icon: iconRefrigerator,
  },
  {
    tag: 'Recipe AI',
    title: '보유 재료를 많이 쓰는 맞춤 레시피 추천',
    description: '조리 시간, 난이도, 알레르기, 매운맛 선호까지 반영해 추천합니다.',
    icon: mascotChef,
  },
  {
    tag: 'Price Compare',
    title: '부족한 재료만 모아 장보기 가격 비교',
    description: '구매처별 가격과 배송비를 비교하고 최저가 장바구니로 연결합니다.',
    icon: iconCart,
  },
]

function CoreFeatureSection() {
  return (
    <section className="home-section home-core home-reveal" aria-labelledby="home-core-title">
      <div className="home-core-heading">
        <div>
          <p>핵심 기능</p>
          <h2 id="home-core-title">
            냉장고 관리에 필요한 기능을
            <br />
            딱 필요한 만큼만
          </h2>
        </div>
        <span>
          입력은 빠르게, 추천은 구체적으로, 구매는 알뜰하게 설계했습니다.
        </span>
      </div>

      <div className="home-core-grid">
        {coreFeatures.map((feature) => (
          <article className="home-core-card" key={feature.title}>
            <div>
              <em>{feature.tag}</em>
              <h3>{feature.title}</h3>
              <p>{feature.description}</p>
            </div>
            <span className="image-slot image-slot--core image-slot--filled" aria-hidden="true">
              <img src={feature.icon} alt="" />
            </span>
          </article>
        ))}
      </div>
    </section>
  )
}

export default CoreFeatureSection
