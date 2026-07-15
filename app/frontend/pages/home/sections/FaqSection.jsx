import { useState } from 'react'

const faqs = [
  {
    question: '영수증 사진은 어디까지 인식하나요?',
    answer:
      '마트, 편의점, 온라인 주문 내역 등 품목명과 금액이 보이는 영수증을 인식합니다. 인식 결과는 저장 전 직접 수정할 수 있어요.',
  },
  {
    question: '소비기한을 전부 직접 입력해야 하나요?',
    answer:
      '기본 보관일을 먼저 제안하고, 필요한 재료만 직접 수정하면 됩니다. 소비 임박 재료는 냉장고 화면과 추천 기준에 반영돼요.',
  },
  {
    question: '알레르기나 먹지 않는 재료도 제외할 수 있나요?',
    answer:
      '마이페이지에서 선호하지 않는 재료와 알레르기 정보를 설정하면 추천 메뉴에서 제외하거나 우선순위를 낮춰 보여줍니다.',
  },
  {
    question: '추천 레시피는 어떤 기준으로 정해지나요?',
    answer:
      '보유 재료 매칭률, 소비 임박 여부, 부족 재료 수, 조리 시간, 사용자 취향을 함께 계산해 추천합니다.',
  },
  {
    question: '모바일에서도 같은 기능을 사용할 수 있나요?',
    answer:
      '네. 영수증 촬영, 냉장고 확인, 레시피 추천, 장보기 목록 확인까지 모바일 화면에서도 사용할 수 있도록 구성했습니다.',
  },
]

function FaqSection() {
  const [openIndex, setOpenIndex] = useState(0)

  return (
    <section className="home-section home-faq home-reveal" aria-labelledby="home-faq-title">
      <div className="home-faq-heading">
        <p>자주 묻는 질문</p>
        <h2 id="home-faq-title">
          시작하기 전에
          <br />
          궁금한 점을 확인하세요
        </h2>
        <span>밥벌이의 재료 등록, 추천 기준, 개인정보 처리 방식에 대한 답변입니다.</span>
      </div>

      <div className="home-faq-list">
        {faqs.map((faq, index) => {
          const isOpen = openIndex === index

          return (
            <article className={`home-faq-item ${isOpen ? 'is-open' : ''}`} key={faq.question}>
              <button
                type="button"
                aria-expanded={isOpen}
                aria-controls={`home-faq-answer-${index}`}
                onClick={() => setOpenIndex(isOpen ? -1 : index)}
              >
                <span>{faq.question}</span>
                <b aria-hidden="true">{isOpen ? 'x' : '+'}</b>
              </button>
              <p id={`home-faq-answer-${index}`}>{faq.answer}</p>
            </article>
          )
        })}
      </div>
    </section>
  )
}

export default FaqSection
