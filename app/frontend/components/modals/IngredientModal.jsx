import React from 'react'

const CATEGORY_OPTIONS = ['채소', '과일', '육류', '수산물', '유제품', '가공식품', '기타']
const STORAGE_OPTIONS = ['냉장', '냉동', '실온']
const UNIT_OPTIONS = ['개', '팩', '봉', 'g', 'kg', 'ml', 'L']

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
  if (!isOpen) return null

  return (
    <div className="fridge-modal-overlay">
      <div className="fridge-modal-content" onClick={(event) => event.stopPropagation()}>
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
              onChange={handleFormChange}
            />
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

          <div className="fridge-form-row">
            <div className="fridge-form-group">
              <label>구매일</label>
              <input type="date" name="purchase_date" value={formData.purchase_date} onChange={handleFormChange} />
            </div>

            <div className="fridge-form-group">
              <label>
                소비기한 <small style={{ color: '#8b673e', fontWeight: 'normal' }}>(비우면 자동 계산)</small>
              </label>
              <input type="date" name="expiration_date" value={formData.expiration_date} onChange={handleFormChange} />
            </div>
          </div>
        </div>

        <div className="fridge-modal-footer">
          <button type="button" className="btn-cancel" onClick={onClose} disabled={isSubmitting}>
            취소
          </button>
          <button type="button" className="btn-submit" onClick={onSubmit} disabled={isSubmitting}>
            {isSubmitting ? '처리 중...' : editingId ? '수정 완료' : '등록 완료'}
          </button>
        </div>
      </div>
    </div>
  )
}
