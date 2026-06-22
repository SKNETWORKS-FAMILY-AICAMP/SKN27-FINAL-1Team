/**
 * 레시피 목록 필터 옵션 (recipe_fix.csv CKG_* 컬럼 unique 기준 하드코딩).
 * 이후 app/frontend/config/ 등으로 파일만 이동해도 import 경로만 바꾸면 됨.
 *
 * @typedef {{ value: string, label: string }} FilterOption
 */

export class RecipeFilterConfig {
  static FILTER_ALL = '전체'

  /** CKG_KND_ACTO_NM — 가나다순 */
  static recipeTypes = [
    '김치/젓갈/장류',
    '과자',
    '국/탕',
    '기타',
    '디저트',
    '메인반찬',
    '면/만두',
    '밑반찬',
    '밥/죽/떡',
    '빵',
    '샐러드',
    '스프',
    '양념/소스/잼',
    '양식',
    '찌개',
    '차/음료/술',
    '퓨전',
  ]

  /** CKG_TIME_NM — 조리 시간 순 */
  static cookingTimes = [
    '5분이내',
    '10분이내',
    '15분이내',
    '30분이내',
    '60분이내',
    '90분이내',
    '2시간이내',
    '2시간이상',
    '확인필요',
  ]

  /** CKG_DODF_NM */
  static difficulties = ['초급', '중급', '고급', '아무나']

  /** 정렬 — UI 유지, FEATURE_FLAGS.sortFilter 연동 전까지 비활성 */
  static sortOptions = [
    { value: '인기순', label: '인기순' },
    { value: '조리시간순', label: '조리시간순' },
    { value: '난이도순', label: '난이도순' },
  ]

  static labels = {
    recipeType: '요리타입',
    cookingTime: '조리시간',
    difficulty: '난이도',
    sort: '정렬',
  }

  /**
   * @param {readonly string[]} values
   * @param {string} allLabel
   * @returns {FilterOption[]}
   */
  static toSelectOptions(values, allLabel) {
    return [
      { value: RecipeFilterConfig.FILTER_ALL, label: allLabel },
      ...values.map((value) => ({ value, label: value })),
    ]
  }
}
