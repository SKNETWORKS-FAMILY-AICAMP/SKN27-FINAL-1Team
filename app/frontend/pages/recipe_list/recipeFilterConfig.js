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
  ]

  /** CKG_DODF_NM */
  static difficulties = ['초급', '중급', '고급']

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

  static urlKeys = {
    query: 'query',
    category: 'category',
    difficulty: 'difficulty',
    cookingTime: 'cooking_time',
    browse: 'browse',
  }

  /**
   * @param {string} search - location.search (e.g. '?query=김치')
   * @returns {{ query: string, category: string, timeFilter: string, levelFilter: string, browseAll: boolean }}
   */
  static parseSearchParams(search) {
    const params = new URLSearchParams(search)
    return {
      query: (params.get(this.urlKeys.query) ?? '').trim(),
      category: params.get(this.urlKeys.category) ?? this.FILTER_ALL,
      timeFilter: params.get(this.urlKeys.cookingTime) ?? this.FILTER_ALL,
      levelFilter: params.get(this.urlKeys.difficulty) ?? this.FILTER_ALL,
      browseAll: params.get(this.urlKeys.browse) === 'all',
    }
  }

  /**
   * @param {{ query?: string, category?: string, timeFilter?: string, levelFilter?: string, browseAll?: boolean }} criteria
   * @returns {URLSearchParams}
   */
  static buildSearchParams(criteria) {
    const params = new URLSearchParams()
    const query = (criteria.query ?? '').trim()
    if (query) {
      params.set(this.urlKeys.query, query)
    }
    if (criteria.category && criteria.category !== this.FILTER_ALL) {
      params.set(this.urlKeys.category, criteria.category)
    }
    if (criteria.timeFilter && criteria.timeFilter !== this.FILTER_ALL) {
      params.set(this.urlKeys.cookingTime, criteria.timeFilter)
    }
    if (criteria.levelFilter && criteria.levelFilter !== this.FILTER_ALL) {
      params.set(this.urlKeys.difficulty, criteria.levelFilter)
    }
    if (criteria.browseAll) {
      params.set(this.urlKeys.browse, 'all')
    }
    return params
  }

  /**
   * @param {{ query?: string, category?: string, timeFilter?: string, levelFilter?: string, browseAll?: boolean }} criteria
   * @param {number} page
   * @param {number} pageSize
   * @returns {Record<string, string>}
   */
  static toApiParams(criteria, page, pageSize) {
    const params = {
      page: String(page),
      page_size: String(pageSize),
    }
    const query = (criteria.query ?? '').trim()
    if (query) {
      params.query = query
    }
    if (criteria.category && criteria.category !== this.FILTER_ALL) {
      params.category = criteria.category
    }
    if (criteria.levelFilter && criteria.levelFilter !== this.FILTER_ALL) {
      params.difficulty = criteria.levelFilter
    }
    if (criteria.timeFilter && criteria.timeFilter !== this.FILTER_ALL) {
      params.cooking_time_label = criteria.timeFilter
    }
    return params
  }
}
