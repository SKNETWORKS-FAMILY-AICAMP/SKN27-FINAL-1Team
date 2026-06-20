import imageEatRefrigerator from '../assets/extracted/images/image_eat_refrigerator.png'

export const recipeQuickMenus = [
  { title: '인기 레시피', description: '요즘 많이 찾는 레시피', mark: 'hot' },
  { title: '간단 레시피', description: '짧은 시간에 완성해요', mark: 'easy' },
  { title: '요리 입문', description: '처음 만들어도 쉬워요', mark: 'beginner' },
  { title: '저장한 레시피', description: '내가 저장한 레시피', mark: 'save' },
]

export const recipes = [
  {
    id: 'green-onion-tofu-egg-stew',
    title: '대파 두부 계란찌개',
    category: '국/찌개',
    time: '20분',
    level: '쉬움',
    tags: ['대파', '두부', '계란', '양파'],
    badge: '인기',
    image: imageEatRefrigerator,
  },
  {
    id: 'mushroom-perilla-soup',
    title: '버섯 들깨탕',
    category: '국/찌개',
    time: '25분',
    level: '보통',
    tags: ['버섯', '두부', '들깨'],
    badge: '간단',
  },
  {
    id: 'kimchi-fried-rice',
    title: '김치 볶음밥',
    category: '볶음',
    time: '15분',
    level: '쉬움',
    tags: ['김치', '밥', '대파', '계란'],
  },
  {
    id: 'tofu-soy-braise',
    title: '두부 간장조림',
    category: '반찬',
    time: '20분',
    level: '쉬움',
    tags: ['두부', '간장', '대파'],
  },
  {
    id: 'rolled-egg',
    title: '계란말이',
    category: '반찬',
    time: '10분',
    level: '쉬움',
    tags: ['계란', '대파', '소금'],
  },
  {
    id: 'tomato-pasta',
    title: '토마토 파스타',
    category: '파스타',
    time: '15분',
    level: '쉬움',
    tags: ['토마토', '양파', '파스타면'],
  },
  {
    id: 'pork-soy-stir-fry',
    title: '돼지고기 간장볶음',
    category: '볶음',
    time: '18분',
    level: '쉬움',
    tags: ['돼지고기', '양파', '간장'],
  },
  {
    id: 'green-onion-pasta',
    title: '대파 파스타',
    category: '파스타',
    time: '25분',
    level: '보통',
    tags: ['대파', '마늘', '파스타면'],
  },
]
