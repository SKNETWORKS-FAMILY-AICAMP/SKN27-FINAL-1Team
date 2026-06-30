import iconEgg from '../assets/extracted/icons/icon_egg.png'
import iconGreenOnion from '../assets/extracted/icons/icon_green_onion.svg'
import iconKimchi from '../assets/extracted/icons/icon_kimchi.svg'
import iconMushroom from '../assets/extracted/icons/icon_mushroom.png'
import iconOnion from '../assets/extracted/icons/icon_onion.png'
import iconTofu from '../assets/extracted/icons/icon_tofu.svg'

export const receiptSteps = [
  '업로드/촬영',
  'AI 분석',
  '재료 확인',
  '냉장고 입고',
]

export const receiptRows = [
  {
    raw: '국산 대파',
    name: '대파',
    quantity: '1단',
    price: '2,000원',
    category: '채소',
    image: iconGreenOnion,
  },
  {
    raw: '한판 달걀',
    name: '계란',
    quantity: '10개',
    price: '1,980원',
    category: '단백질',
    image: iconEgg,
  },
  {
    raw: '부침두부',
    name: '두부',
    quantity: '1개',
    price: '2,300원',
    category: '단백질',
    image: iconTofu,
  },
  {
    raw: '양파',
    name: '양파',
    quantity: '2개',
    price: '1,280원',
    category: '채소',
    image: iconOnion,
    review: true,
  },
  {
    raw: '방울토마토',
    name: '방울토마토',
    quantity: '1팩',
    price: '1,600원',
    category: '채소',
    image: iconMushroom,
  },
  {
    raw: '맛김치',
    name: '김치',
    quantity: '1통',
    price: '3,400원',
    category: '반찬',
    image: iconKimchi,
  },
]

export const receiptHistory = [
  {
    title: '마켓 영수증',
    meta: '4개 품목, 6개 재료 등록',
    amount: '12,560원',
    status: '완료',
    date: '2026.06.18 14:32',
    store: 'BABBEORI MART',
    items: ['대파 1단', '계란 10개', '두부 1개', '양파 2개', '방울토마토 1팩', '김치 1통'],
    note: '모든 품목이 냉장고에 입고됐어요.',
  },
  {
    title: '편의점 영수증',
    meta: '2개 품목 검토 필요',
    amount: '5,800원',
    status: '검토',
    date: '2026.06.16 19:04',
    store: '편의점 영수증',
    items: ['우유 1개', '샐러드 1개', '바나나 1송이'],
    note: '상품명 확인이 필요한 품목이 남아 있어요.',
  },
  {
    title: '온라인 주문 캡처',
    meta: '이번 주 식재료 후보',
    amount: '24,300원',
    status: '확인',
    date: '2026.06.12 10:21',
    store: '온라인 장보기',
    items: ['닭가슴살 1kg', '버섯 1팩', '양배추 1개', '현미밥 3개'],
    note: '금액 확인이 필요한 품목을 먼저 확인해주세요.',
  },
  {
    title: '동네마트 영수증',
    meta: '5개 품목, 5개 재료 등록',
    amount: '18,900원',
    status: '완료',
    date: '2026.06.08 17:46',
    store: '동네마트',
    items: ['돼지고기 600g', '상추 1개', '마늘 1개', '두부 1개', '콩나물 1봉'],
    note: '품목명과 금액까지 모두 확인됐어요.',
  },
  {
    title: '주말 장보기',
    meta: '7개 품목 분석 완료',
    amount: '31,200원',
    status: '완료',
    date: '2026.06.02 11:12',
    store: '대형마트',
    items: ['양파 3개', '감자 1kg', '당근 2개', '계란 10개', '치즈 1개', '토마토 1팩', '우유 1개'],
    note: '소비 임박 알림이 자동으로 설정됐어요.',
  },
]

export const receiptRules = [
  { title: '표준 재료명 매칭', description: '상품명을 냉장고 재료명으로 정리', enabled: true },
]
