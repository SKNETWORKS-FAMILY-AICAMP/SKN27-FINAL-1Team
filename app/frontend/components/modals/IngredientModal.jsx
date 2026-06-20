import React from 'react'

export default function IngredientModal({
  isOpen,
  editingId,
  formData,
  handleFormChange,
  onClose,
  onSubmit
}) {
  if (!isOpen) return null

  return (
    <div className="fridge-modal-overlay">
      <div className="fridge-modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="fridge-modal-header">
          <h2>{editingId ? '식재료 수정' : '식재료 추가'}</h2>
          <button type="button" onClick={onClose} aria-label="닫기">
            ✕
          </button>
        </div>
        <div className="fridge-modal-body">
          <div className="fridge-form-group">
            <label>재료명 <span style={{color:'red'}}>*</span></label>
            <input type="text" name="name" placeholder="예) 양파, 대파, 우유" value={formData.name} onChange={handleFormChange} />
          </div>
          <div className="fridge-form-row">
            <div className="fridge-form-group">
              <label>카테고리</label>
              <select name="category" value={formData.category} onChange={handleFormChange}>
                <option value="채소">채소</option>
                <option value="과일">과일</option>
                <option value="육류">육류</option>
                <option value="수산물">수산물</option>
                <option value="유제품">유제품</option>
                <option value="가공식품">가공식품</option>
                <option value="기타">기타</option>
              </select>
            </div>
            <div className="fridge-form-group">
              <label>보관 위치</label>
              <select name="storage_method" value={formData.storage_method} onChange={handleFormChange}>
                <option value="냉장">냉장</option>
                <option value="냉동">냉동</option>
                <option value="실온">실온</option>
              </select>
            </div>
          </div>
          <div className="fridge-form-row">
            <div className="fridge-form-group">
              <label>수량 <small style={{color:'#8b673e', fontWeight: 'normal'}}>(반 개는 0.5)</small></label>
              <input type="number" name="quantity" min="0.5" step="0.5" value={formData.quantity} onChange={handleFormChange} />
            </div>
            <div className="fridge-form-group">
              <label>단위</label>
              <select name="unit" value={formData.unit} onChange={handleFormChange}>
                <option value="개">개</option>
                <option value="Kg">Kg</option>
              </select>
            </div>
          </div>
          <div className="fridge-form-group">
            <label>유통기한(소비기한) <small style={{color:'#8b673e', fontWeight: 'normal'}}>(미입력시 자동 계산)</small></label>
            <input type="date" name="expiration_date" value={formData.expiration_date} onChange={handleFormChange} />
          </div>
        </div>
        <div className="fridge-modal-footer">
          <button type="button" className="btn-cancel" onClick={onClose}>취소</button>
          <button type="button" className="btn-submit" onClick={onSubmit}>
            {editingId ? '수정 완료' : '등록 완료'}
          </button>
        </div>
      </div>
    </div>
  )
}
