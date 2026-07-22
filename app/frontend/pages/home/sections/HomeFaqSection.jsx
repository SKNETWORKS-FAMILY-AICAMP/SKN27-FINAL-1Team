import { Link } from 'react-router-dom'
import { faqGroups } from '../../info/FaqPage.jsx'

function HomeFaqSection() {
  return (
    <section className="home-section home-faq home-reveal" aria-labelledby="home-faq-title">
      <div className="home-faq-heading">
        <p>자주 묻는 질문</p>
        <h2 id="home-faq-title">
          처음 써도
          <br />
          헷갈리지 않게
        </h2>
        <span>영수증, 냉장고, 레시피, 캘린더, MCP 연결까지 많이 묻는 내용을 모았습니다.</span>
        <Link className="home-faq-link" to="/faq">전체 FAQ 보기</Link>
      </div>

      <div className="home-faq-list">
        {faqGroups.map((group) => (
          <details className="home-faq-group" key={group.title}>
            <summary>{group.title}</summary>
            <div className="home-faq-question-list">
              {group.questions.map((item) => (
                <details className="home-faq-question" key={item.question}>
                  <summary>{item.question}</summary>
                  <p>{item.answer}</p>
                </details>
              ))}
            </div>
          </details>
        ))}
      </div>
    </section>
  )
}

export default HomeFaqSection
