import iconRefrigerator from '../../../assets/extracted/icons/icon_refrigerator.png'
import iconSearch from '../../../assets/extracted/images/image_search.png'
import iconTime from '../../../assets/extracted/icons/icon_time.png'

const problems = [
  {
    number: '01',
    title: '있는 재료를 자꾸 잊어요',
    description: '냉장·냉동·상온 재료를 한 화면에서 보고, 수량과 보관 위치까지 관리합니다.',
    icon: iconRefrigerator,
  },
  {
    number: '02',
    title: '소비기한이 지나 버려요',
    description: '소비 임박 재료를 먼저 알려주고, 해당 재료를 활용한 메뉴를 우선 추천합니다.',
    icon: iconTime,
  },
  {
    number: '03',
    title: '레시피마다 재료가 부족해요',
    description: '보유 재료 매칭률을 계산해 최소 구매로 완성할 수 있는 레시피를 골라드립니다.',
    icon: iconSearch,
  },
]

function ProblemSection() {
  return (
    <section className="home-section home-problems home-reveal" aria-labelledby="home-problem-title">
      <div className="home-problem-heading">
        <div>
          <p>매번 반복되는 고민</p>
          <h2 id="home-problem-title">
            냉장고는 가득한데,
            <br />
            오늘도 메뉴가 막막하죠
          </h2>
        </div>
        <span>
          보유 재료를 기억하고, 소비기한을 챙기고, 부족한 재료를 따로 계산하는
          번거로움을 밥벌이가 줄여드려요.
        </span>
      </div>

      <div className="home-problem-grid">
        {problems.map((problem) => (
          <article className="home-mini-card home-problem-card" key={problem.title}>
            <span className="image-slot image-slot--icon image-slot--filled" aria-hidden="true">
              <img src={problem.icon} alt="" />
            </span>
            <b>{problem.number}</b>
            <strong>{problem.title}</strong>
            <p>{problem.description}</p>
          </article>
        ))}
      </div>
    </section>
  )
}

export default ProblemSection
