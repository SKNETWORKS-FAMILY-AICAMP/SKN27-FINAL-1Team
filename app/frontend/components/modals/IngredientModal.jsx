import React, { useState, useEffect, useRef } from 'react'

const CATEGORY_OPTIONS = ['기타', '채소', '과일', '육류', '수산물', '유제품', '가공식품']
const STORAGE_OPTIONS = ['냉장', '냉동', '실온']
const UNIT_OPTIONS = ['개', 'kg']

// 식재료 이미지 파일명을 검색용 키로 정규화합니다.
function normalizeIngredientImageName(name = '') {
  return name.replace(/\.[^.]+$/, '').replace(/\s/g, '').toLowerCase()
}

const INGREDIENT_SEARCH_ALIASES = {
  계란: ['달걀'],
  달걀: ['계란'],
  쇠고기: ['소고기'],
  돈육: ['돼지고기'],
  고추가루: ['고춧가루'],
  케찹: ['케첩'],
  대파: ['파'],
}

// 사용자가 동의어로 검색해도 대표 식재료가 자동완성되도록 검색 키를 확장합니다.
function getIngredientSearchKeys(keyword = '') {
  const key = normalizeIngredientImageName(keyword)
  return [key, ...(INGREDIENT_SEARCH_ALIASES[key] || []).map(normalizeIngredientImageName)]
}

const ingredientImages = Object.entries(
  import.meta.glob('../../assets/extracted/ingredients/*.{png,jpg,jpeg,webp,svg}', {
    eager: true,
    import: 'default',
  }),
)
  .map(([path, src]) => {
    const fileName = path.split('/').pop() || ''
    const name = fileName.replace(/\.[^.]+$/, '')
    return { name, key: normalizeIngredientImageName(name), src }
  })
  .sort((a, b) => a.name.localeCompare(b.name, 'ko'))


// 식재료 추가/수정 폼을 표시하는 모달 컴포넌트입니다.
export default function IngredientModal({
  isOpen,
  editingId,
  formData,
  handleFormChange,
  onClose,
  onSubmit,
  isSubmitting,
}) {
  const [predictError, setPredictError] = useState('')
  const [suggestions, setSuggestions] = useState([])
  const [isSuggestionOpen, setIsSuggestionOpen] = useState(false)
  const [hasEditedName, setHasEditedName] = useState(false)
  const [focusedSuggestionIndex, setFocusedSuggestionIndex] = useState(-1)
  const suggestionListRef = useRef(null)

  useEffect(() => {
    if (focusedSuggestionIndex >= 0 && suggestionListRef.current) {
      const activeElement = suggestionListRef.current.children[focusedSuggestionIndex]
      if (activeElement) {
        activeElement.scrollIntoView({ block: 'nearest' })
      }
    }
  }, [focusedSuggestionIndex])

  // 수정 모달은 처음 열릴 때 자동완성을 숨기고, 사용자가 이름을 바꾼 뒤 다시 보여줍니다.
  useEffect(() => {
    if (isOpen) setHasEditedName(false)
  }, [editingId, isOpen])

  // 식재료명 입력이 끝났을 때 보관 위치를 한 번만 예측합니다.
  const handlePredictIngredient = async () => {
    const ingredientName = formData.name.trim()

    if (!isOpen || !ingredientName) {
      setPredictError('')
      return
    }

    if (formData.storage_method) return

    setPredictError('')

    try {
      const token = window.localStorage.getItem('bobbeori-token')
      const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000'
      const response = await fetch(`${apiUrl}/api/v1/inventory/predict?name=${encodeURIComponent(ingredientName)}`, {
        headers: {
          'Authorization': `Bearer ${token || ''}`,
        }
      })

      if (response.ok) {
        const data = await response.json()
        if (data.is_valid_food) {
          if (!formData.storage_method && data.storage_method) {
            handleFormChange({ target: { name: 'storage_method', value: data.storage_method } })
          }
        } else {
          setPredictError('올바른 식재료 이름을 입력해주세요. (예: 양파, 우유)')
        }
      }
    } catch (error) {
      console.error('AI 예측 실패:', error)
    }
  }
  // 재료명 입력값으로 assets에 있는 표준 식재료만 자동완성합니다.
  useEffect(() => {
    const keyword = formData.name.trim()
    const key = normalizeIngredientImageName(keyword)
    const searchKeys = getIngredientSearchKeys(keyword)
    if (!isOpen || (editingId && !hasEditedName) || !key) {
      setSuggestions([])
      setFocusedSuggestionIndex(-1)
      return
    }

    setFocusedSuggestionIndex(-1)
    setSuggestions(
      ingredientImages
        .filter((item) => searchKeys.some((searchKey) => item.key.includes(searchKey)))
        // 정확히 일치하는 식재료를 먼저 보여줍니다.
        .sort((a, b) =>
          Number(searchKeys.includes(b.key)) - Number(searchKeys.includes(a.key)) ||
          Number(searchKeys.some((searchKey) => b.key.startsWith(searchKey))) - Number(searchKeys.some((searchKey) => a.key.startsWith(searchKey))) ||
          a.name.localeCompare(b.name, 'ko'),
        )
        .slice(0, 6),
    )
  }, [editingId, formData.name, hasEditedName, isOpen])

  // 자동완성 항목을 선택하면 재료명 입력값에 바로 반영합니다.
  const handleSelectSuggestion = (suggestion) => {
    handleFormChange({ target: { name: 'name', value: suggestion.name } })
    setSuggestions([])
    setIsSuggestionOpen(false)
    setPredictError('')
  }

  useEffect(() => {
    if (!isOpen) return

    const handleGlobalKeyDown = (e) => {
      if (e.key === 'Enter') {
        // 폼 입력 시 기본 제출/엔터 동작 방지
        e.preventDefault()
        if (!isSubmitting && !predictError) {
          onSubmit()
        }
      } else if (e.key === 'Escape') {
        onClose()
      }
    }

    window.addEventListener('keydown', handleGlobalKeyDown)
    return () => window.removeEventListener('keydown', handleGlobalKeyDown)
  }, [isOpen, isSubmitting, predictError, onSubmit, onClose])

  if (!isOpen) return null

  return (
    <div className="fridge-modal-overlay">
      <div
        className="fridge-modal-content"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="fridge-modal-header">
          <h2>{editingId ? '식재료 수정' : '식재료 추가'}</h2>
          <button type="button" onClick={onClose} aria-label="닫기">
            ×
          </button>
        </div>

        <div className="fridge-modal-body">
          <div className="fridge-form-group">
            <label>
              재료명<span style={{ color: 'red' }}>*</span>
            </label>
            <input
              type="text"
              name="name"
              disabled={!!editingId}
              autoComplete="off"
              autoFocus
              placeholder="예: 양파, 두부, 우유"
              value={formData.name}
              onChange={(event) => {
                if (editingId) setHasEditedName(true)
                setIsSuggestionOpen(true)
                handleFormChange(event)
              }}
              onKeyDown={(e) => {
                if (isSuggestionOpen && suggestions.length > 0) {
                  if (e.key === 'ArrowDown') {
                    e.preventDefault()
                    setFocusedSuggestionIndex((prev) => Math.min(prev + 1, suggestions.length - 1))
                  } else if (e.key === 'ArrowUp') {
                    e.preventDefault()
                    setFocusedSuggestionIndex((prev) => Math.max(prev - 1, 0))
                  } else if (e.key === 'Enter') {
                    e.preventDefault()
                    e.stopPropagation()
                    if (focusedSuggestionIndex >= 0) {
                      handleSelectSuggestion(suggestions[focusedSuggestionIndex])
                    } else {
                      handleSelectSuggestion(suggestions[0])
                    }
                  }
                }
              }}
              onFocus={() => (!editingId || hasEditedName) && setIsSuggestionOpen(true)}
              onBlur={() => {
                setIsSuggestionOpen(false)
                handlePredictIngredient()
              }}
            />
            {(!editingId || hasEditedName) && isSuggestionOpen && suggestions.length > 0 ? (
              <div className="fridge-suggestion-list" ref={suggestionListRef}>
                {suggestions.map((suggestion, index) => (
                  <button
                    type="button"
                    key={suggestion.key}
                    className={index === focusedSuggestionIndex ? 'is-focused' : ''}
                    onMouseDown={(event) => {
                      event.preventDefault()
                      handleSelectSuggestion(suggestion)
                    }}
                  >
                    <img src={suggestion.src} alt="" />
                    <span>{suggestion.name}</span>
                  </button>
                ))}
              </div>
            ) : null}
            {predictError && <p style={{ color: 'red', fontSize: '12px', marginTop: '4px' }}>🔴 {predictError}</p>}
          </div>

          <div className="fridge-form-row">
            <div className="fridge-form-group">
              <label>카테고리</label>
              <select name="category" value={formData.category} onChange={handleFormChange}>
                {CATEGORY_OPTIONS.map((option) => (
                  <option value={option} key={option}>{option}</option>
                ))}
              </select>
            </div>

            <div className="fridge-form-group">
              <label>보관 위치</label>
              <select name="storage_method" value={formData.storage_method} onChange={handleFormChange}>
                <option value="" disabled>권장 보관 위치</option>
                {STORAGE_OPTIONS.map((option) => (
                  <option value={option} key={option}>{option}</option>
                ))}
              </select>
            </div>
          </div>

          <div className="fridge-form-row">
            <div className="fridge-form-group">
              <label>
                수량 <small style={{ color: '#8b673e', fontWeight: 'normal' }}>(소수점 입력 가능)</small>
              </label>
              <input
                type="number"
                name="quantity"
                min="0.5"
                step="0.5"
                value={formData.quantity}
                onChange={handleFormChange}
              />
            </div>

            <div className="fridge-form-group">
              <label>단위</label>
              <select name="unit" value={formData.unit} onChange={handleFormChange}>
                {UNIT_OPTIONS.map((option) => (
                  <option value={option} key={option}>{option}</option>
                ))}
              </select>
            </div>
          </div>
          <div className="fridge-form-group">
            <label>
              소비기한 <small style={{ color: '#8b673e', fontWeight: 'normal' }}>(비우면 자동 계산)</small>
            </label>
            <input type="date" name="expiration_date" value={formData.expiration_date} onChange={handleFormChange} />
          </div>
        </div>

        <div className="fridge-modal-footer">
          <button type="button" className="btn-cancel" onClick={onClose} disabled={isSubmitting}>
            취소
          </button>
          <button type="button" className="btn-submit" onClick={onSubmit} disabled={isSubmitting || !!predictError}>
            {isSubmitting ? '처리 중...' : editingId ? '수정 완료' : '등록 완료'}
          </button>
        </div>
      </div>
    </div>
  )
}
