/**
 * 레시피 목록 필터 옵션.
 * 각 항목: name(내부 식별) / label(UI 표시) / code(URL, 클래스약자+번호 고정 4자) / apiValue(백엔드 값, 기본=label)
 *
 * URL 키는 urlKeys 로 짧게 노출 (q/i/c/d/t/b), 코드에서는 이름으로 참조.
 *
 * @typedef {{ name: string, label: string, code: string, apiValue?: string }} FilterDef
 * @typedef {{ value: string, label: string }} FilterOption
 */

/** @param {FilterDef} def */
function apiValueOf(def) {
  return def.apiValue ?? def.label
}

export class RecipeFilterConfig {
  /** criteria / option.value 에 쓰는 '전체' 식별자 */
  static FILTER_ALL = 'all'

  static ALL_OPTION = {
    name: 'all',
    label: '전체',
    code: 'all',
  }

  /** URL 파라미터 키: 내부 이름 → 외부 짧은 글자 */
  static urlKeys = {
    query: 'q',
    ingredient: 'i',
    category: 'c',
    difficulty: 'd',
    cookingTime: 't',
    browse: 'b',
  }

  /** 구버전(긴 키) — 북마크 호환용 */
  static legacyUrlKeys = {
    query: 'query',
    ingredient: 'ingredient',
    category: 'category',
    difficulty: 'difficulty',
    cookingTime: 'cooking_time',
    browse: 'browse',
  }

  /** @type {readonly FilterDef[]} CT = category type */
  static recipeTypes = [
    { name: 'snack', label: '간식·야식', code: 'ct01' },
    { name: 'soup', label: '국·탕', code: 'ct02' },
    { name: 'main', label: '메인요리', code: 'ct03' },
    { name: 'noodle', label: '면', code: 'ct04' },
    { name: 'side', label: '반찬', code: 'ct05' },
    { name: 'rice', label: '밥·덮밥', code: 'ct06' },
    { name: 'fried_rice', label: '볶음밥', code: 'ct07' },
    { name: 'sandwich', label: '샌드위치·토스트', code: 'ct08' },
    { name: 'salad', label: '샐러드', code: 'ct09' },
    { name: 'porridge', label: '죽', code: 'ct10' },
    { name: 'stew', label: '찌개', code: 'ct11' },
  ]

  /** @type {readonly FilterDef[]} DF = difficulty */
  static difficulties = [
    { name: 'very_easy', label: '매우 쉬움', code: 'df01' },
    { name: 'easy', label: '쉬움', code: 'df02' },
    { name: 'normal', label: '보통', code: 'df03' },
  ]

  /** @type {readonly FilterDef[]} TM = cooking time */
  static cookingTimes = [
    { name: 'le15', label: '15분', code: 'tm01', apiValue: '15분이내' },
    { name: 'le30', label: '30분', code: 'tm02', apiValue: '30분이내' },
    { name: 'ge30', label: '60분', code: 'tm03', apiValue: '30분이상' },
  ]

  static labels = {
    recipeType: '요리타입',
    cookingTime: '조리시간',
    difficulty: '난이도',
  }

  /**
   * @param {keyof typeof RecipeFilterConfig.urlKeys} key
   * @param {URLSearchParams} params
   */
  static readParam(params, key) {
    return params.get(this.urlKeys[key]) ?? params.get(this.legacyUrlKeys[key])
  }

  /**
   * @param {readonly FilterDef[]} defs
   * @param {string} token - URL code 또는 구버전 한글 apiValue/label
   * @returns {string} name (모르면 FILTER_ALL)
   */
  static resolveName(defs, token) {
    const raw = String(token ?? '').trim()
    if (!raw || raw === this.FILTER_ALL || raw === this.ALL_OPTION.label) {
      return this.FILTER_ALL
    }
    const byCode = defs.find((def) => def.code === raw)
    if (byCode) return byCode.name
    const byApi = defs.find((def) => apiValueOf(def) === raw || def.label === raw)
    if (byApi) return byApi.name
    return this.FILTER_ALL
  }

  /**
   * @param {readonly FilterDef[]} defs
   * @param {string} name
   * @returns {FilterDef | null}
   */
  static findByName(defs, name) {
    if (!name || name === this.FILTER_ALL) return null
    return defs.find((def) => def.name === name) ?? null
  }

  /**
   * @param {readonly FilterDef[]} defs
   * @returns {FilterOption[]}
   */
  static toSelectOptions(defs) {
    return [
      { value: this.FILTER_ALL, label: this.ALL_OPTION.label },
      ...defs.map((def) => ({ value: def.name, label: def.label })),
    ]
  }

  /**
   * facets(한글 api 값)에 해당하는 정의만 남긴다.
   * @param {readonly FilterDef[]} defs
   * @param {readonly string[]} apiValues
   * @returns {FilterDef[]}
   */
  static filterByApiValues(defs, apiValues) {
    const allowed = new Set(apiValues.map((value) => String(value ?? '').trim()).filter(Boolean))
    return defs.filter((def) => allowed.has(apiValueOf(def)))
  }

  /**
   * @param {string} search
   * @returns {{ query: string, ingredient: string, category: string, timeFilter: string, levelFilter: string, browseAll: boolean }}
   */
  static parseSearchParams(search) {
    const params = new URLSearchParams(search)
    const browse = this.readParam(params, 'browse')
    return {
      query: (this.readParam(params, 'query') ?? '').trim(),
      ingredient: (this.readParam(params, 'ingredient') ?? '').trim(),
      category: this.resolveName(this.recipeTypes, this.readParam(params, 'category')),
      timeFilter: this.resolveName(this.cookingTimes, this.readParam(params, 'cookingTime')),
      levelFilter: this.resolveName(this.difficulties, this.readParam(params, 'difficulty')),
      browseAll: browse === '1' || browse === 'all',
    }
  }

  /**
   * 필터는 고정길이 code, 검색어만 원문. 파라미터 키는 urlKeys 약자.
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
    const category = this.findByName(this.recipeTypes, criteria.category)
    if (category) {
      params.set(this.urlKeys.category, category.code)
    }
    const time = this.findByName(this.cookingTimes, criteria.timeFilter)
    if (time) {
      params.set(this.urlKeys.cookingTime, time.code)
    }
    const level = this.findByName(this.difficulties, criteria.levelFilter)
    if (level) {
      params.set(this.urlKeys.difficulty, level.code)
    }
    if (criteria.browseAll) {
      params.set(this.urlKeys.browse, '1')
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
    const category = this.findByName(this.recipeTypes, criteria.category)
    if (category) {
      params.category = apiValueOf(category)
    }
    const level = this.findByName(this.difficulties, criteria.levelFilter)
    if (level) {
      params.difficulty = apiValueOf(level)
    }
    const time = this.findByName(this.cookingTimes, criteria.timeFilter)
    if (time) {
      params.cooking_time_label = apiValueOf(time)
    }
    return params
  }
}
