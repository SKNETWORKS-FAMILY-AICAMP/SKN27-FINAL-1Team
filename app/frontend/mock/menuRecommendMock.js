import imageEatRefrigerator from '../assets/extracted/images/image_eat_refrigerator.png'

export const countOptions = [3, 5, 7, 10]

export const defaultFilters = {
  limit: 5,
  cookTime: 'ANY',
  difficulty: 'ANY',
  ingredientUsage: 'NORMAL',
  allowMissing: 'ALLOW',
  expiryPriority: 'ANY',
  category: 'ALL',
}

export const filterOptions = {
  cookTime: [
    { value: 'ANY', label: '상관없음' },
    { value: 'UNDER_20', label: '20분 이하' },
    { value: 'UNDER_40', label: '40분 이하' },
    { value: 'UNDER_60', label: '60분 이하' },
    { value: 'OVER_120', label: '2시간 이상' },
  ],
  difficulty: [
    { value: 'ANY', label: '상관없음' },
    { value: 'EASY', label: '쉬움' },
    { value: 'NORMAL', label: '보통' },
    { value: 'HARD', label: '어려움' },
  ],
  ingredientUsage: [
    { value: 'ANY', label: '상관없음' },
    { value: 'LOW', label: '낮음', hint: '적당히 활용' },
    { value: 'NORMAL', label: '보통', hint: '적당히 활용' },
    { value: 'HIGH', label: '높음', hint: '최대한 활용' },
  ],
  allowMissing: [
    { value: 'ANY', label: '상관없음' },
    { value: 'DENY', label: '허용 안 함', hint: '보유 재료만' },
    { value: 'ALLOW', label: '허용', hint: '추가 구매 가능' },
  ],
  expiryPriority: [
    { value: 'ANY', label: '상관없음' },
    { value: 'PRIORITIZE', label: '우선 사용' },
  ],
  category: [
    { value: 'ALL', label: '전체' },
    { value: '밥', label: '밥' },
    { value: '국/탕', label: '국/탕' },
    { value: '찌개', label: '찌개' },
    { value: '반찬', label: '반찬' },
    { value: '면', label: '면' },
    { value: '디저트', label: '디저트' },
  ],
}

export const filterGroups = [
  { key: 'cookTime', label: '조리 시간', icon: '🕐', type: 'pills' },
  { key: 'difficulty', label: '난이도', icon: '👨‍🍳', type: 'pills' },
  { key: 'ingredientUsage', label: '활용 재료', icon: '🥬', subtitle: '보유 재료 기준', type: 'pills' },
  { key: 'allowMissing', label: '부족 재료 허용', icon: '🛒', type: 'pills' },
  { key: 'category', label: '카테고리', icon: '📁', type: 'select' },
  { key: 'expiryPriority', label: '유통기한 임박 재료 우선', icon: '📅', type: 'pills' },
]

export const recommendTemplates = [
  {
    id: 'quick',
    label: '빠르게 만들기',
    icon: '⚡',
    desc: '조리 시간이 짧은 레시피',
    preset: { cookTime: 'UNDER_20', difficulty: 'EASY', ingredientUsage: 'NORMAL' },
  },
  {
    id: 'low_fail',
    label: '실패 확률 낮게',
    icon: '🛡️',
    desc: '초보자도 성공하기 쉬운 레시피',
    preset: { difficulty: 'EASY', ingredientUsage: 'NORMAL' },
  },
  {
    id: 'hearty',
    label: '든든한 한 끼',
    icon: '🍲',
    desc: '포만감 있는 레시피',
    preset: { difficulty: 'NORMAL', cookTime: 'ANY' },
  },
  {
    id: 'side_dish',
    label: '반찬 위주',
    icon: '🥗',
    desc: '밑반찬·곁들임 레시피',
  // ponytail: UI select only until ranking weights land in API phase
    preset: { category: '반찬', ingredientUsage: 'NORMAL' },
  },
  {
    id: 'budget',
    label: '절약 메뉴',
    icon: '💰',
    desc: '재료비 부담이 적은 레시피',
    preset: { ingredientUsage: 'NORMAL', allowMissing: 'ALLOW' },
  },
  {
    id: 'consume',
    label: '재료 소진 우선',
    icon: '♻️',
    desc: '냉장고 재료를 활용하는 레시피',
    preset: { ingredientUsage: 'HIGH', expiryPriority: 'PRIORITIZE' },
  },
  {
    id: 'custom',
    label: '추천 설정',
    icon: '⚙️',
    desc: '조건을 직접 설정',
    preset: null,
  },
]

export const menuRecommendProcess = [
  {
    title: '조건 확인',
    description: '선택한 템플릿과 필터에 맞춰 추천을 준비합니다.',
  },
  {
    title: '메뉴 후보 생성',
    description: '조건에 맞는 메뉴 후보를 골라냅니다.',
  },
  {
    title: '결과 정렬',
    description: '추천 점수를 기준으로 순서를 정리합니다.',
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
    image: imageEatRefrigerator,
  },
  {
    id: 'tomato-pasta',
    title: '토마토 파스타',
    category: '가벼운 면요리',
    time: '15분',
    level: '쉬움',
    reason: '짧은 시간에 완성하기 좋고 점심이나 저녁 메뉴로 부담이 적어요.',
    image: imageEatRefrigerator,
  },
  {
    id: 'mushroom-perilla-soup',
    title: '버섯 들깨국',
    category: '따뜻한 국물',
    time: '25분',
    level: '보통',
    reason: '고소하고 따뜻해서 저녁에 잘 어울리고 남은 버섯을 쓰기 좋아요.',
    image: imageEatRefrigerator,
  },
  {
    id: 'kimchi-fried-rice',
    title: '김치볶음밥',
    category: '빠른 한 그릇',
    time: '15분',
    level: '쉬움',
    reason: '재료가 단순하고 조리가 빨라 바쁜 점심이나 야식에 좋아요.',
    image: imageEatRefrigerator,
  },
  {
    id: 'rolled-egg',
    title: '계란말이',
    category: '간단 반찬',
    time: '10분',
    level: '쉬움',
    reason: '반찬으로 곁들이기 좋고 적은 재료로 빠르게 만들 수 있어요.',
    image: imageEatRefrigerator,
  },
  {
    id: 'tofu-soy-braise',
    title: '두부 간장조림',
    category: '절약 반찬',
    time: '20분',
    level: '쉬움',
    reason: '재료비 부담이 낮고 밥반찬으로 오래 활용하기 좋아요.',
    image: imageEatRefrigerator,
  },
  {
    id: 'pork-soy-stir-fry',
    title: '돼지고기 간장볶음',
    category: '든든한 고기 메뉴',
    time: '18분',
    level: '쉬움',
    reason: '메인 요리감이 확실해서 든든한 저녁 메뉴로 잘 맞아요.',
    image: imageEatRefrigerator,
  },
]
