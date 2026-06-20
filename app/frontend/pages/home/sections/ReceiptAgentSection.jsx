const receiptRows = [
  { name: '대파', amount: '1단', price: '1,980원', category: '채소' },
  { name: '두부', amount: '1모', price: '2,300원', category: '가공식품' },
  { name: '계란', amount: '10구', price: '2,980원', category: '달걀' },
  { name: '양파', amount: '2개', price: '1,280원', category: '채소' },
  { name: '버섯', amount: '180g', price: '3,460원', category: '버섯' },
]

const receiptStats = [
  { value: '5개', label: '인식 품목' },
  { value: '98%', label: '평균 정확도' },
  { value: '5초', label: '처리 시간' },
]

function ReceiptAgentSection() {
  return (
    <section className="home-section home-receipt-agent home-reveal" aria-labelledby="home-receipt-agent-title">
      <div className="home-receipt-agent__heading">
        <div>
          <p>Receipt OCR Agent</p>
          <h2 id="home-receipt-agent-title">
            영수증 한 장으로
            <br />
            냉장고 등록을 끝내세요
          </h2>
        </div>
        <span>사진에서 품목과 가격을 읽고 식재료만 분류해 냉장고에 입고합니다.</span>
      </div>

      <div className="home-receipt-agent__grid">
        <article className="home-receipt-scan" aria-label="영수증 스캔 예시">
          <div className="home-receipt-paper">
            <strong>BABBEORI MART</strong>
            <dl>
              {receiptRows.map((row) => (
                <div key={row.name}>
                  <dt>{row.name}</dt>
                  <dd>{row.price}</dd>
                </div>
              ))}
            </dl>
            <b>TOTAL 12,000</b>
          </div>
          <span aria-hidden="true" />
        </article>

        <article className="home-receipt-result">
          <h3>인식 결과를 확인해 주세요</h3>
          <p>재료 카테고리와 보관 위치를 자동으로 제안했어요.</p>

          <div className="home-receipt-result__table" role="table" aria-label="영수증 OCR 인식 결과">
            <div className="home-receipt-result__row is-head" role="row">
              <span role="columnheader">인식 품목</span>
              <span role="columnheader">수량</span>
              <span role="columnheader">가격</span>
              <span role="columnheader">분류</span>
            </div>
            {receiptRows.map((row) => (
              <div className="home-receipt-result__row" role="row" key={row.name}>
                <span role="cell">{row.name}</span>
                <span role="cell">{row.amount}</span>
                <span role="cell">{row.price}</span>
                <span role="cell">{row.category}</span>
              </div>
            ))}
          </div>

          <div className="home-receipt-stats">
            {receiptStats.map((stat) => (
              <div key={stat.label}>
                <strong>{stat.value}</strong>
                <span>{stat.label}</span>
              </div>
            ))}
          </div>

          <button type="button">모두 냉장고에 입고</button>
        </article>
      </div>
    </section>
  )
}

export default ReceiptAgentSection
