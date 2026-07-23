import iconEgg from '../assets/extracted/icons/icon_egg.png'
import iconOnion from '../assets/extracted/icons/icon_onion.png'

export const shoppingItems = [
  {
    name: '대파',
    detail: '국내산',
    quantity: '1대',
    recipe: '대파 두부 계란찌개',
    reason: '소비 임박 대파를 보완할 최소 수량',
    priority: '오늘 필요',
  },
  {
    name: '두부',
    detail: '부침/찌개용',
    quantity: '1모',
    recipe: '대파 두부 계란찌개',
    reason: '단백질 보강, 냉장고에 없음',
    priority: '오늘 필요',
  },
  {
    name: '계란',
    detail: '특란',
    quantity: '10개',
    recipe: '대파 두부 계란찌개',
    image: iconEgg,
    reason: '찌개와 다음 아침 식사까지 활용',
    priority: '묶음 추천',
  },
  {
    name: '양파',
    detail: '국내산',
    quantity: '2개',
    recipe: '김치볶음밥',
    image: iconOnion,
    reason: '볶음밥 단맛 보강, 남은 재료와 호환',
    priority: '대체 가능',
  },
  {
    name: '김치',
    detail: '배추김치',
    quantity: '1통 (300g)',
    recipe: '김치볶음밥',
    reason: '냉장고 김치 부족으로 자동 추가',
    priority: '오늘 필요',
  },
  {
    name: '참기름',
    detail: '오뚜기',
    quantity: '1병',
    recipe: '김치볶음밥',
    reason: '기본 양념 재고 없음',
    priority: '상시 재고',
  },
  {
    name: '김가루',
    detail: '조미김',
    quantity: '1봉',
    recipe: '김치볶음밥',
    reason: '맛 보강용, 예산 초과 시 제외 가능',
    priority: '선택',
  },
]

export const priceRows = [
  { name: '대파 (1대)', marketA: '1,900원', marketB: '1,490원', best: '1,490원', diff: '-410원' },
  { name: '두부 (1모)', marketA: '2,300원', marketB: '1,980원', best: '1,980원', diff: '-320원' },
  { name: '계란 (10개)', marketA: '2,980원', marketB: '2,780원', best: '2,780원', diff: '-200원' },
  { name: '양파 (2개)', marketA: '1,980원', marketB: '1,780원', best: '1,780원', diff: '-200원' },
  { name: '김치 (300g)', marketA: '2,980원', marketB: '2,500원', best: '2,500원', diff: '-480원' },
  { name: '참기름 (1병)', marketA: '3,200원', marketB: '2,980원', best: '2,980원', diff: '-220원' },
  { name: '김가루 (1봉)', marketA: '1,400원', marketB: '1,200원', best: '1,200원', diff: '-200원' },
]
