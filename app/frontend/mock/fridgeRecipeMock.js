import imageEatRefrigerator from '../assets/extracted/images/image_eat_refrigerator.png'
import { userProfile } from './userService.js'

export const fridgeRecipeTabs = ['전체 추천 (3)', '소비 임박 우선 (2)', '재료 많이 활용 (2)', '간단 요리 (2)']

export const fridgeRecipeRecommendations = [
  {
    id: 'green-onion-tofu-egg-stew',
    title: '대파 두부 계란찌개',
    category: '임박 재료 사용',
    time: '20분',
    minutes: 20,
    level: '쉬움',
    people: '1인분',
    match: 93,
    owned: 7,
    total: 8,
    expiresSoon: true,
    saveEstimate: '8,400원 절약',
    reason: '대파가 D-1이라 먼저 사용할 수 있어요. 보유 재료 7/8개로 간단하게 만들 수 있어요.',
    missing: ['된장 1큰술'],
    image: imageEatRefrigerator,
  },
  {
    id: 'pork-soy-stir-fry',
    title: '돼지고기 간장볶음',
    category: '보유 재료 활용',
    time: '15분',
    minutes: 15,
    level: '쉬움',
    people: '1인분',
    match: 89,
    owned: 6,
    total: 8,
    expiresSoon: false,
    saveEstimate: '6,200원 절약',
    reason: '돼지고기, 양파 등 보유 재료를 많이 활용할 수 있어서 알뜰해요.',
    missing: ['간장 1큰술', '식용유 1큰술'],
  },
  {
    id: 'tomato-pasta',
    title: '토마토 파스타',
    category: '간단 요리',
    time: '15분',
    minutes: 15,
    level: '쉬움',
    people: '1인분',
    match: 82,
    owned: 5,
    total: 7,
    expiresSoon: true,
    saveEstimate: '5,800원 절약',
    reason: '토마토가 D-2라 맛있을 때 사용할 수 있어요. 한 번에 뚝딱 만들 수 있어요.',
    missing: ['파스타면 100g', '올리브오일 1큰술'],
  },
]

export const fridgeRecipeProcess = [
  {
    title: '보유 재료 스캔',
    description: '냉장고에 있는 재료와 수량을 확인해요.',
  },
  {
    title: '소비 임박 우선 계산',
    description: 'D-3 이하 재료가 들어가는 메뉴에 가중치를 줘요.',
  },
  {
    title: '취향과 예산 반영',
    description: `${userProfile.cookTime}, ${userProfile.budgetLabel}, ${userProfile.taste} 조건을 반영해요.`,
  },
  {
    title: '부족 재료 장보기 연결',
    description: '없는 재료만 골라 장보기 목록으로 넘겨요.',
  },
]
