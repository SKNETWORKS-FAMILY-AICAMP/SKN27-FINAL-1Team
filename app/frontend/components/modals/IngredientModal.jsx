import React, { useState, useEffect, useRef } from 'react'
import { API_URL } from '../../utils/api.js'
import {
  searchIngredientImages,
  useIngredientImageCatalog,
} from '../../utils/ingredientImages.js'

const CATEGORY_OPTIONS = ['기타', '채소', '과일', '육류', '수산물', '유제품', '가공식품']
const STORAGE_OPTIONS = ['냉장', '냉동', '실온']
const UNIT_OPTIONS = ['개', 'kg']

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
  const ingredientImageCatalog = useIngredientImageCatalog()
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
      const response = await fetch(`${API_URL}/api/v1/inventory/predict?name=${encodeURIComponent(ingredientName)}`, {
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
          setPredictError('올바른 식재료 이름을 입력해주세요.')
        }
      }
    } catch (error) {
      console.error('AI 예측 실패:', error)
    }
  }
  // 재료명 입력값으로 매니페스트의 대표 식재료를 자동완성합니다.
  useEffect(() => {
    const keyword = formData.name.trim()
    if (!isOpen || (editingId && !hasEditedName) || !keyword) {
      setSuggestions([])
      setFocusedSuggestionIndex(-1)
      return
    }

    setFocusedSuggestionIndex(-1)
    setSuggestions(searchIngredientImages(ingredientImageCatalog, keyword))
  }, [editingId, formData.name, hasEditedName, ingredientImageCatalog, isOpen])

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
                    key={suggestion.id}
                    className={index === focusedSuggestionIndex ? 'is-focused' : ''}
                    onMouseDown={(event) => {
                      event.preventDefault()
                      handleSelectSuggestion(suggestion)
                    }}
                  >
                    <img src={suggestion.imageUrl} alt="" />
                    <span>{suggestion.name}</span>
                  </button>
                ))}
              </div>
            ) : null}
            {predictError && <p style={{ color: 'red', fontSize: '12px', marginTop: '4px', marginLeft: '5px' }}>{predictError}</p>}
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
              소비기한{' '}
              <small style={{ color: '#8b673e', fontWeight: 'normal' }}>
                (미 입력시 <span className="fridge-ai-badge" style={{ padding: '2px 6px', fontSize: '11px', margin: '0 2px', verticalAlign: 'baseline', borderRadius: '6px' }}>AI</span>가 자동 계산)
              </small>
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
