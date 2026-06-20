export const userProfile = {
  name: '밥벌이님',
  household: '2인 가구',
  mealTarget: '오늘 저녁',
  budgetLabel: '18,000원 이하',
  cookTime: '25분 안쪽',
  taste: '맵지 않게',
  avoid: ['새우', '땅콩'],
  priority: '소비 임박 재료 먼저 쓰기',
}

export const serviceContext = {
  selectedRecipe: '대파 두부 계란찌개',
  pairedRecipe: '김치 볶음밥',
  fridgeMatch: '92%',
  urgentIngredientCount: 3,
  savedThisMonth: '48,700원',
  currentCartTotal: 15690,
  cartBudget: 18000,
  deliveryTotal: 24090,
  selectedMarket: '쿠팡',
  deliveryEta: '오늘 밤 도착',
}

export const serviceSteps = [
  {
    title: '냉장고 확인',
    description: '이미 있는 재료는 장보기에서 제외했어요.',
  },
  {
    title: '부족 재료 추림',
    description: '오늘 저녁 메뉴에 꼭 필요한 재료만 남겼어요.',
  },
  {
    title: '최저가 비교',
    description: '배송비 포함 기준으로 가장 싼 조합을 골랐어요.',
  },
]

export const serviceBadges = [
  '2인분 기준',
  '25분 안쪽',
  '맵지 않게',
  '소비 임박 우선',
]

export function formatWon(value) {
  return `${value.toLocaleString('ko-KR')}원`
}
