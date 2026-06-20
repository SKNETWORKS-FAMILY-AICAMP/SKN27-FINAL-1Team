import imageEatRefrigerator from '../assets/extracted/images/image_eat_refrigerator.png'

export const countOptions = [3, 5, 7]
export const moodOptions = ['든든하게', '가볍게', '따뜻하게', '빠르게']
export const mealOptions = ['아침', '점심', '저녁', '야식']
export const priorityOptions = ['조리시간 짧게', '실패 확률 낮게', '반찬 위주', '절약 메뉴']

export const menuRecommendProcess = [
  {
    title: '조건 확인',
    description: '선택한 분위기, 식사 시간, 우선순위에 맞춰 추천을 준비합니다.',
  },
  {
    title: '메뉴 후보 생성',
    description: '지금 먹기 좋은 메뉴를 조건별로 골라냅니다.',
  },
  {
    title: '결과 정렬',
    description: '조리 난이도와 우선순위를 기준으로 추천 순서를 정리합니다.',
  },
]

export const menuRecommendRecipes = [
  {
    id: 'green-onion-tofu-egg-stew',
    title: '대파 두부 계란찜',
    category: '든든한 한 끼',
    time: '20분',
    level: '쉬움',
    reason: '계란과 두부로 포만감이 좋고 실패 확률이 낮아 편하게 만들 수 있어요.',
    moods: ['든든하게', '따뜻하게'],
    meals: ['아침', '점심', '저녁'],
    priorities: ['실패 확률 낮게', '절약 메뉴'],
    image: imageEatRefrigerator,
  },
  {
    id: 'tomato-pasta',
    title: '토마토 파스타',
    category: '가벼운 면요리',
    time: '15분',
    level: '쉬움',
    reason: '짧은 시간에 완성하기 좋고 점심이나 저녁 메뉴로 부담이 적어요.',
    moods: ['가볍게', '빠르게'],
    meals: ['점심', '저녁'],
    priorities: ['조리시간 짧게', '실패 확률 낮게'],
    image: imageEatRefrigerator,
  },
  {
    id: 'mushroom-perilla-soup',
    title: '버섯 들깨국',
    category: '따뜻한 국물',
    time: '25분',
    level: '보통',
    reason: '고소하고 따뜻해서 저녁에 잘 어울리고 남은 버섯을 쓰기 좋아요.',
    moods: ['따뜻하게', '가볍게'],
    meals: ['아침', '저녁'],
    priorities: ['절약 메뉴', '반찬 위주'],
    image: imageEatRefrigerator,
  },
  {
    id: 'kimchi-fried-rice',
    title: '김치볶음밥',
    category: '빠른 한 그릇',
    time: '15분',
    level: '쉬움',
    reason: '재료가 단순하고 조리가 빨라 바쁜 점심이나 야식에 좋아요.',
    moods: ['든든하게', '빠르게'],
    meals: ['점심', '야식'],
    priorities: ['조리시간 짧게', '절약 메뉴'],
    image: imageEatRefrigerator,
  },
  {
    id: 'rolled-egg',
    title: '계란말이',
    category: '간단 반찬',
    time: '10분',
    level: '쉬움',
    reason: '반찬으로 곁들이기 좋고 적은 재료로 빠르게 만들 수 있어요.',
    moods: ['가볍게', '빠르게'],
    meals: ['아침', '저녁'],
    priorities: ['조리시간 짧게', '반찬 위주', '실패 확률 낮게'],
    image: imageEatRefrigerator,
  },
  {
    id: 'tofu-soy-braise',
    title: '두부 간장조림',
    category: '절약 반찬',
    time: '20분',
    level: '쉬움',
    reason: '재료비 부담이 낮고 밥반찬으로 오래 활용하기 좋아요.',
    moods: ['든든하게', '따뜻하게'],
    meals: ['점심', '저녁'],
    priorities: ['절약 메뉴', '반찬 위주'],
    image: imageEatRefrigerator,
  },
  {
    id: 'pork-soy-stir-fry',
    title: '돼지고기 간장볶음',
    category: '든든한 고기 메뉴',
    time: '18분',
    level: '쉬움',
    reason: '메인 요리감이 확실해서 든든한 저녁 메뉴로 잘 맞아요.',
    moods: ['든든하게', '빠르게'],
    meals: ['저녁', '야식'],
    priorities: ['조리시간 짧게', '실패 확률 낮게'],
    image: imageEatRefrigerator,
  },
]
