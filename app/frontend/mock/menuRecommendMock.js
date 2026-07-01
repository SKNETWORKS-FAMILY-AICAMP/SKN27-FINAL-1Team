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
    { value: '15분이내', label: '15분 이하' },
    { value: '30분이내', label: '30분 이하' },
    { value: '60분이내', label: '60분 이하' },
    { value: '2시간이상', label: '2시간 이상' },
  ],
  difficulty: [
    { value: 'ANY', label: '상관없음' },
    { value: '초급', label: '쉬움' },
    { value: '중급', label: '보통' },
    { value: '고급', label: '어려움' },
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
    { value: '밥/죽/떡', label: '밥/죽/떡' },
    { value: '국/탕', label: '국/탕' },
    { value: '찌개', label: '찌개' },
    { value: '메인반찬', label: '메인반찬' },
    { value: '밑반찬', label: '밑반찬' },
    { value: '면/만두', label: '면/만두' },
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
    preset: { cookTime: '15분이내', difficulty: '초급', ingredientUsage: 'NORMAL' },
  },
  {
    id: 'low_fail',
    label: '실패 확률 낮게',
    icon: '🛡️',
    desc: '초보자도 성공하기 쉬운 레시피',
    preset: { difficulty: '초급', ingredientUsage: 'NORMAL' },
  },
  {
    id: 'hearty',
    label: '든든한 한 끼',
    icon: '🍲',
    desc: '포만감 있는 레시피',
    preset: { difficulty: '중급', cookTime: 'ANY' },
  },
  {
    id: 'side_dish',
    label: '반찬 위주',
    icon: '🥗',
    desc: '밑반찬·곁들임 레시피',
    preset: { category: '밑반찬', ingredientUsage: 'NORMAL' },
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

export function buildRecommendRequestBody(filters, { excludeIds = [], refreshPool = false } = {}) {
  const body = {
    mode: 'menu_custom',
    limit: filters.limit,
    exclude_recipe_ids: excludeIds,
    refresh_pool: refreshPool,
  }

  if (filters.cookTime !== 'ANY') {
    body.cooking_time_label = filters.cookTime
  }
  if (filters.difficulty !== 'ANY') {
    body.difficulty = filters.difficulty
  }
  if (filters.category !== 'ALL') {
    body.category = filters.category
  }

  return body
}

export function formatCookingTime(minutes) {
  if (minutes == null) {
    return '-'
  }
  return `${minutes}분`
}
