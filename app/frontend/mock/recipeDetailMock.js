import iconEgg from '../assets/extracted/icons/icon_egg.png'
import iconMushroom from '../assets/extracted/icons/icon_mushroom.png'
import iconOnion from '../assets/extracted/icons/icon_onion.png'

export const ownedIngredients = [
  { name: '대파', amount: '1대' },
  { name: '두부', amount: '1모' },
  { name: '계란', amount: '2개', image: iconEgg },
  { name: '양파', amount: '1/2개', image: iconOnion },
  { name: '버섯', amount: '한 줌', image: iconMushroom },
  { name: '김치', amount: '선택' },
]

export const missingIngredients = [
  { name: '다진 마늘', amount: '100g' },
  { name: '고춧가루', amount: '200g' },
]

export const recipeSteps = [
  { title: '재료 손질', text: '대파, 양파, 버섯을 먹기 좋게 썰고 두부는 한 입 크기로 썰어주세요.' },
  { title: '대파 볶기', text: '냄비에 대파를 넣고 중불에서 향이 날 때까지 볶아주세요.' },
  { title: '양파, 버섯 볶기', text: '양파와 버섯을 넣고 함께 2분 정도 볶아주세요.' },
  { title: '물 붓고 끓이기', text: '물과 육수 또는 물을 붓고 끓여주세요.' },
  { title: '두부 넣기', text: '두부를 넣고 5분 정도 더 끓여 간이 배도록 해주세요.' },
  { title: '계란 풀기', text: '마지막에 계란을 풀고 1분만 더 끓인 뒤 불을 꺼주세요.' },
]
