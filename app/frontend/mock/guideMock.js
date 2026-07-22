import iconEgg from '../assets/extracted/icons/icon_egg.png'
import iconGreenOnion from '../assets/extracted/icons/icon_green_onion.svg'
import iconKimchi from '../assets/extracted/icons/icon_kimchi.svg'
import iconMushroom from '../assets/extracted/icons/icon_mushroom.png'
import iconOnion from '../assets/extracted/icons/icon_onion.png'
import iconTofu from '../assets/extracted/icons/icon_tofu.svg'

export const guideIngredients = [
  { name: '대파', image: iconGreenOnion },
  { name: '두부', image: iconTofu },
  { name: '계란', image: iconEgg },
  { name: '양파', image: iconOnion },
  { name: '버섯', image: iconMushroom },
  { name: '김치', image: iconKimchi },
]

export const guideTips = [
  {
    title: '보관방법',
    points: [
      '냉장 보관이 좋아요.',
      '키친타월로 감싼 뒤 지퍼백이나 밀폐용기에 넣어 보관하세요.',
      '신문지로 감싸면 수분 손실을 줄일 수 있어요.',
    ],
    chip: '보관 온도 : 0~5°C',
    source: '식품의약품안전처 식품안전나라, 농촌진흥청 농식품올바로 참고',
  },
  {
    title: '손질방법',
    points: [
      '뿌리의 지저분한 부분을 잘라내요.',
      '시든 겉잎은 제거하고 활용할 부분만 준비해요.',
      '흰 부분과 초록 부분은 용도에 맞게 나눠 사용해요.',
    ],
    chip: '흰 부분은 국물 요리에 좋아요',
    source: '농촌진흥청 농식품올바로 식재료 손질 정보 참고',
  },
  {
    title: '세척방법',
    points: [
      '흐르는 물에 흙과 이물질을 꼼꼼히 씻어요.',
      '뿌리 부분은 칼집을 살짝 내어 속까지 헹궈요.',
      '물기가 많으면 보관성이 떨어져요.',
    ],
    chip: '흐르는 물 사용 추천',
    source: '식품의약품안전처 식재료 세척 가이드 참고',
  },
  {
    title: '신선도 확인법',
    points: [
      '잎이 선명한 초록색이고 시들지 않았는지 확인해요.',
      '줄기가 단단하고 윤기가 있는지 살펴봐요.',
      '갈변이 넓게 보이면 신선도가 낮아요.',
    ],
    chip: '진액이 나오면 신선해요',
    source: '농촌진흥청 농식품올바로 품질 확인 정보 참고',
  },
]

export const guideRecipes = [
  { id: 'green-onion-tofu-egg-stew', title: '대파 두부 계란찌개', meta: '20분 · 쉬움 · 보유 재료 7/10' },
  { id: 'tomato-pasta', title: '대파 파스타', meta: '25분 · 보통 · 보유 재료 6/9' },
  { id: 'pork-soy-stir-fry', title: '대파 삼겹살 구이', meta: '30분 · 쉬움 · 보유 재료 5/8' },
]
