/**
 * 레시피 목록 필터 옵션 (recipe_175.csv 기준).
 * 이후 app/frontend/config/ 등으로 파일만 이동해도 import 경로만 바꾸면 됨.
 *
 * @typedef {{ value: string, label: string }} FilterOption
 */

export class RecipeFilterConfig {
  static FILTER_ALL = '전체'

  /** menu_category — 가나다순 */
  static recipeTypes = [
    '간식·야식',
    '국·탕',
    '메인요리',
    '면',
    '반찬',
    '밥·덮밥',
    '볶음밥',
    '샌드위치·토스트',
    '샐러드',
    '죽',
    '찌개',
  ]

  /** difficulty */
  static difficulties = ['매우 쉬움', '쉬움', '보통']

  static labels = {
    recipeType: '요리타입',
    cookingTime: '조리시간',
    difficulty: '난이도',
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
    ingredient: 'ingredient',
    category: 'category',
    difficulty: 'difficulty',
    cookingTime: 'cooking_time',
    browse: 'browse',
  }

  /**
   * @param {string} search - location.search (e.g. '?query=김치')
   * @returns {{ query: string, ingredient: string, category: string, timeFilter: string, levelFilter: string, browseAll: boolean }}
   */
  static parseSearchParams(search) {
    const params = new URLSearchParams(search)
    return {
      query: (params.get(this.urlKeys.query) ?? '').trim(),
      ingredient: (params.get(this.urlKeys.ingredient) ?? '').trim(),
      category: params.get(this.urlKeys.category) ?? this.FILTER_ALL,
      timeFilter: params.get(this.urlKeys.cookingTime) ?? this.FILTER_ALL,
      levelFilter: params.get(this.urlKeys.difficulty) ?? this.FILTER_ALL,
      browseAll: params.get(this.urlKeys.browse) === 'all',
    }
  }

  /**
   * @param {{ query?: string, ingredient?: string, category?: string, timeFilter?: string, levelFilter?: string, browseAll?: boolean }} criteria
   * @returns {URLSearchParams}
   */
  static buildSearchParams(criteria) {
    const params = new URLSearchParams()
    const query = (criteria.query ?? '').trim()
    const ingredient = (criteria.ingredient ?? '').trim()
    if (query) {
      params.set(this.urlKeys.query, query)
    }
    if (ingredient) {
      params.set(this.urlKeys.ingredient, ingredient)
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
   * @param {{ query?: string, ingredient?: string, category?: string, timeFilter?: string, levelFilter?: string, browseAll?: boolean }} criteria
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
    const ingredient = (criteria.ingredient ?? '').trim()
    if (query) {
      params.query = query
    }
    if (ingredient) {
      params.ingredient = ingredient
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
