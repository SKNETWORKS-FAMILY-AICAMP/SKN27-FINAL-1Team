/**
 * 레시피 목록 필터 옵션.
 * 각 항목: name(내부 식별) / label(UI 표시) / code(짧은 식별, 클래스약자+번호) / apiValue(백엔드 값, 기본=label)
 *
 * 검색·필터 criteria 전부 location.state + sessionStorage 로 보존. URL 쿼리 없음.
 *
 * @typedef {{ name: string, label: string, code: string, apiValue?: string }} FilterDef
 * @typedef {{ value: string, label: string }} FilterOption
 * @typedef {{ query: string, ingredient: string, category: string, timeFilter: string, levelFilter: string, browseAll: boolean }} RecipeCriteria
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

  static CRITERIA_STORAGE_KEY = 'bobbeori-recipe-criteria'

  /** 구버전 URL 키 (마이그레이션용) */
  static legacyUrlKeys = {
    query: ['q', 'query'],
    ingredient: ['i', 'ingredient'],
    category: ['c', 'category'],
    difficulty: ['d', 'difficulty'],
    cookingTime: ['t', 'cooking_time'],
    browse: ['b', 'browse'],
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

  /** @returns {RecipeCriteria} */
  static emptyCriteria() {
    return {
      query: '',
      ingredient: '',
      category: this.FILTER_ALL,
      timeFilter: this.FILTER_ALL,
      levelFilter: this.FILTER_ALL,
      browseAll: false,
    }
  }

  /**
   * @param {Partial<RecipeCriteria>} criteria
   * @returns {RecipeCriteria}
   */
  static normalizeCriteria(criteria) {
    const base = this.emptyCriteria()
    return {
      query: String(criteria?.query ?? '').trim(),
      ingredient: String(criteria?.ingredient ?? '').trim(),
      category: this.findByName(this.recipeTypes, criteria?.category)?.name ?? this.FILTER_ALL,
      timeFilter: this.findByName(this.cookingTimes, criteria?.timeFilter)?.name ?? this.FILTER_ALL,
      levelFilter: this.findByName(this.difficulties, criteria?.levelFilter)?.name ?? this.FILTER_ALL,
      browseAll: Boolean(criteria?.browseAll),
    }
  }

  /**
   * @param {Partial<RecipeCriteria>} criteria
   * @returns {RecipeCriteria}
   */
  static buildLocationState(criteria) {
    return this.normalizeCriteria(criteria)
  }

  /** @returns {RecipeCriteria | null} */
  static readStoredCriteria() {
    if (typeof sessionStorage === 'undefined') return null
    try {
      const raw = sessionStorage.getItem(this.CRITERIA_STORAGE_KEY)
      if (!raw) return null
      return this.normalizeCriteria(JSON.parse(raw))
    } catch {
      return null
    }
  }

  /** @param {Partial<RecipeCriteria>} criteria */
  static writeStoredCriteria(criteria) {
    if (typeof sessionStorage === 'undefined') return
    try {
      sessionStorage.setItem(
        this.CRITERIA_STORAGE_KEY,
        JSON.stringify(this.normalizeCriteria(criteria)),
      )
    } catch {
      // ponytail: private mode / quota — 보존만 포기
    }
  }

  /**
   * @param {URLSearchParams} params
   * @param {keyof typeof RecipeFilterConfig.legacyUrlKeys} key
   */
  static readLegacyParam(params, key) {
    for (const name of this.legacyUrlKeys[key]) {
      const value = params.get(name)
      if (value != null && value !== '') return value
    }
    return null
  }

  /**
   * @param {readonly FilterDef[]} defs
   * @param {string | null | undefined} token
   * @returns {string}
   */
  static resolveName(defs, token) {
    const raw = String(token ?? '').trim()
    if (!raw || raw === this.FILTER_ALL || raw === this.ALL_OPTION.label) {
      return this.FILTER_ALL
    }
    const byName = defs.find((def) => def.name === raw)
    if (byName) return byName.name
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
   * @param {readonly FilterDef[]} defs
   * @param {readonly string[]} apiValues
   * @returns {FilterDef[]}
   */
  static filterByApiValues(defs, apiValues) {
    const allowed = new Set(apiValues.map((value) => String(value ?? '').trim()).filter(Boolean))
    return defs.filter((def) => allowed.has(apiValueOf(def)))
  }

  /** @param {string} search */
  static hasLegacyCriteriaInUrl(search) {
    const params = new URLSearchParams(search)
    if ([...params.keys()].length === 0) return false
    return Object.keys(this.legacyUrlKeys).some((key) =>
      this.readLegacyParam(params, /** @type {keyof typeof RecipeFilterConfig.legacyUrlKeys} */ (key)) != null
      || (key === 'browse' && (params.has('b') || params.has('browse'))),
    )
  }

  /**
   * @param {string} search
   * @returns {RecipeCriteria}
   */
  static parseLegacyUrlCriteria(search) {
    const params = new URLSearchParams(search)
    const browse = this.readLegacyParam(params, 'browse')
    return this.normalizeCriteria({
      query: this.readLegacyParam(params, 'query') ?? '',
      ingredient: this.readLegacyParam(params, 'ingredient') ?? '',
      category: this.resolveName(this.recipeTypes, this.readLegacyParam(params, 'category')),
      timeFilter: this.resolveName(this.cookingTimes, this.readLegacyParam(params, 'cookingTime')),
      levelFilter: this.resolveName(this.difficulties, this.readLegacyParam(params, 'difficulty')),
      browseAll: browse === '1' || browse === 'all',
    })
  }

  /**
   * location.state → sessionStorage → 구버전 URL 순.
   * @param {string} search
   * @param {unknown} [locationState]
   * @returns {RecipeCriteria}
   */
  static parseCriteria(search, locationState) {
    if (
      locationState
      && typeof locationState === 'object'
      && (
        'query' in locationState
        || 'ingredient' in locationState
        || 'category' in locationState
        || 'timeFilter' in locationState
        || 'levelFilter' in locationState
        || 'browseAll' in locationState
      )
    ) {
      return this.normalizeCriteria(/** @type {Partial<RecipeCriteria>} */ (locationState))
    }

    const stored = this.readStoredCriteria()
    if (stored && (
      stored.query
      || stored.ingredient
      || stored.category !== this.FILTER_ALL
      || stored.timeFilter !== this.FILTER_ALL
      || stored.levelFilter !== this.FILTER_ALL
      || stored.browseAll
    )) {
      return stored
    }

    if (this.hasLegacyCriteriaInUrl(search)) {
      return this.parseLegacyUrlCriteria(search)
    }

    return this.emptyCriteria()
  }

  /** @deprecated parseCriteria 사용 */
  static parseSearchParams(search, locationState) {
    return this.parseCriteria(search, locationState)
  }

  /**
   * URL에는 쿼리를 쓰지 않음 (호환용 빈 파라미터).
   * @returns {URLSearchParams}
   */
  static buildSearchParams() {
    return new URLSearchParams()
  }

  /**
   * @param {Partial<RecipeCriteria>} criteria
   * @param {number} page
   * @param {number} pageSize
   * @returns {Record<string, string>}
   */
  static toApiParams(criteria, page, pageSize) {
    const normalized = this.normalizeCriteria(criteria)
    const params = {
      page: String(page),
      page_size: String(pageSize),
    }
    if (normalized.query) {
      params.query = normalized.query
    }
    if (normalized.ingredient) {
      params.ingredient = normalized.ingredient
    }
    const category = this.findByName(this.recipeTypes, normalized.category)
    if (category) {
      params.category = apiValueOf(category)
    }
    const level = this.findByName(this.difficulties, normalized.levelFilter)
    if (level) {
      params.difficulty = apiValueOf(level)
    }
    const time = this.findByName(this.cookingTimes, normalized.timeFilter)
    if (time) {
      params.cooking_time_label = apiValueOf(time)
    }
    return params
  }
}
