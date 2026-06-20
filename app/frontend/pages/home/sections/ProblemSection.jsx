import iconBasket from '../../../assets/extracted/icons/icon_basket.png'
import iconRefrigerator from '../../../assets/extracted/icons/icon_refrigerator.png'
import iconTime from '../../../assets/extracted/icons/icon_time.png'
import worryImage from '../../../assets/extracted/images/image_worry.png'

const problems = [
  {
    label: '재료를 자주 잊어버림',
    icon: iconRefrigerator,
  },
  {
    label: '유통기한 지나서 버림',
    icon: iconTime,
  },
  {
    label: '레시피를 찾아도 없는 재료가 많음',
    icon: iconBasket,
  },
]

function ProblemSection() {
  return (
    <section className="home-section home-problems home-reveal" aria-labelledby="home-problem-title">
      <div className="home-section__header">
        <h2 id="home-problem-title">이런 고민, 매번 반복되죠</h2>
        <img className="home-problem-visual" src={worryImage} alt="" aria-hidden="true" />
      </div>
      <div className="home-problem-grid">
        {problems.map((problem) => (
          <article className="home-mini-card" key={problem.label}>
            <span className="image-slot image-slot--icon image-slot--filled" aria-hidden="true">
              <img src={problem.icon} alt="" />
            </span>
            <strong>{problem.label}</strong>
          </article>
        ))}
      </div>
    </section>
  )
}

export default ProblemSection
