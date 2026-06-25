import React, { useState, useEffect } from 'react'
import iconEgg from '../../assets/extracted/icons/icon_egg.png'
import iconKimchi from '../../assets/extracted/icons/icon_kimchi.svg'
import iconMushroom from '../../assets/extracted/icons/icon_mushroom.png'
import iconOnion from '../../assets/extracted/icons/icon_onion.png'
import iconTofu from '../../assets/extracted/icons/icon_tofu.svg'
import iconGreenOnion from '../../assets/extracted/icons/icon_green_onion.svg'

const CATEGORY_OPTIONS = ['기타', '채소', '과일', '육류', '수산물', '유제품', '가공식품']
const STORAGE_OPTIONS = ['냉장', '냉동', '실온']
const UNIT_OPTIONS = ['개', 'kg']

// 자동완성 재료명에 맞는 대표 식재료 아이콘을 선택합니다.
function getSuggestionIcon(name = '') {
  if (name.includes('달걀') || name.includes('계란')) return iconEgg
  if (name.includes('김치') || name.includes('깍두기')) return iconKimchi
  if (name.includes('버섯')) return iconMushroom
  if (name.includes('양파')) return iconOnion
  if (name.includes('두부')) return iconTofu
  if (name.includes('대파') || name.includes('쪽파') || name.includes('파')) return iconGreenOnion
  return null
}

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
  // 재료명 입력값으로 식재료 마스터 자동완성 목록을 조회합니다.
  useEffect(() => {
    const keyword = formData.name.trim()
    if (!isOpen || !keyword) {
      setSuggestions([])
      return undefined
    }

    const token = window.localStorage.getItem('bobbeori-token')
    if (!token) {
      setSuggestions([])
      return undefined
    }

    const timeoutId = window.setTimeout(async () => {
      try {
        const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000'
        const response = await fetch(apiUrl + '/api/v1/inventory/suggestions?q=' + encodeURIComponent(keyword), {
          headers: { Authorization: 'Bearer ' + token },
        })
        if (response.ok) {
          const data = await response.json()
          setSuggestions(data.filter((name) => name !== keyword).slice(0, 6))
        }
      } catch (error) {
        setSuggestions([])
      }
    }, 180)

    return () => window.clearTimeout(timeoutId)
  }, [formData.name, isOpen])

  // 자동완성 항목을 선택하면 재료명 입력값에 바로 반영합니다.
  const handleSelectSuggestion = (name) => {
    handleFormChange({ target: { name: 'name', value: name } })
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
              placeholder="예: 양파, 두부, 우유"
              value={formData.name}
              onChange={(event) => {
                setIsSuggestionOpen(true)
                handleFormChange(event)
              }}
              onFocus={() => setIsSuggestionOpen(true)}
              onBlur={() => {
                setIsSuggestionOpen(false)
                handlePredictIngredient()
              }}
            />
            {isSuggestionOpen && suggestions.length > 0 ? (
              <div className="fridge-suggestion-list">
                {suggestions.map((name) => (
                  <button
                    type="button"
                    key={name}
                    onMouseDown={(event) => {
                      event.preventDefault()
                      handleSelectSuggestion(name)
                    }}
                  >
                    {getSuggestionIcon(name) ? <img src={getSuggestionIcon(name)} alt="" /> : null}
                    <span>{name}</span>
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
                min="0.1"
                step="0.1"
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
