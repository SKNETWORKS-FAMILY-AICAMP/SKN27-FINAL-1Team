const reviews = [
  {
    quote:
      '퇴근길에 뭘 사야 할지 고민하는 시간이 확 줄었어요. 집에 있는 재료부터 쓰게 돼서 버리는 채소도 거의 없어졌습니다.',
    name: '김하늘 님',
    meta: '1인 가구 · 사용 3개월',
  },
  {
    quote:
      '아이 입맛과 조리 시간 설정을 해두니 평일 메뉴 정하기가 편해요. 부족 재료만 바로 장보기로 넘어가는 점이 좋습니다.',
    name: '박준호 님',
    meta: '맞벌이 가정 · 사용 5개월',
  },
  {
    quote:
      '영수증 촬영으로 냉장고 목록이 채워지는 게 제일 편해요. 소비기한 알림 덕분에 같은 식재료를 중복 구매하지 않아요.',
    name: '이서현 님',
    meta: '요리 초보 · 사용 2개월',
  },
  {
    quote:
      '냉장고에 뭐가 남아 있는지 한 번에 보여서 장보기 전에 꼭 확인하게 됩니다. 식비도 조금씩 줄었어요.',
    name: '정민재 님',
    meta: '자취 4년차 · 사용 4개월',
  },
  {
    quote:
      '추천 이유가 같이 나오니까 왜 이 메뉴를 먹어야 하는지 납득이 돼요. 남은 재료 처리에 특히 좋습니다.',
    name: '오유진 님',
    meta: '신혼부부 · 사용 6개월',
  },
  {
    quote:
      '부족한 재료만 따로 모아줘서 장보기 목록을 다시 만들 필요가 없어요. 냉장고 파먹기가 훨씬 쉬워졌습니다.',
    name: '최도윤 님',
    meta: '직장인 · 사용 1개월',
  },
]

const rollingReviews = [...reviews, ...reviews]

function ReviewSection() {
  return (
    <section className="home-section home-reviews home-reveal" aria-labelledby="home-review-title">
      <div className="home-review-heading">
        <div>
          <p>밥벌이 사용 후기</p>
          <h2 id="home-review-title">
            냉장고를 비우는 일이
            <br />
            조금 더 즐거워졌어요
          </h2>
        </div>
        <span>자취생부터 맞벌이 가정까지, 각자의 식사 루틴에 맞게 활용하고 있어요.</span>
      </div>

      <div className="home-review-grid" aria-label="밥벌이 사용 후기">
        <div className="home-review-track">
          {rollingReviews.map((review, index) => (
            <article
              className="home-review-card"
              key={`${review.name}-${index}`}
              aria-hidden={index >= reviews.length ? 'true' : undefined}
            >
              <span aria-label="별점 5점">★★★★★</span>
              <p>“{review.quote}”</p>
              <div>
                <i aria-hidden="true" />
                <strong>{review.name}</strong>
                <em>{review.meta}</em>
              </div>
            </article>
          ))}
        </div>
      </div>
    </section>
  )
}

export default ReviewSection
