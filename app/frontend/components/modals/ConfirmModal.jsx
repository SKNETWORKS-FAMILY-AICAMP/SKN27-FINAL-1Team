import React, { useEffect } from 'react'
import './ConfirmModal.css'

// 확인/취소가 필요한 공용 모달입니다
export default function ConfirmModal({
  isOpen,
  title,
  message,
  onConfirm,
  onClose,
  confirmText = '확인',
  cancelText = '취소',
  showCancel = true,
  danger = true,
}) {
  useEffect(() => {
    if (!isOpen) return

    // 키보드 입력으로도 모달을 빠르게 처리할 수 있게 합니다
    const handleKeyDown = (e) => {
      if (e.key === 'Enter') {
        e.preventDefault()
        onConfirm()
      } else if (e.key === 'Escape') {
        onClose()
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, onConfirm, onClose])

  if (!isOpen) return null

  return (
    <div className="fridge-modal-overlay">
      <div className="fridge-modal-content fridge-confirm-modal" onClick={(e) => e.stopPropagation()}>
        <div className="fridge-modal-header">
          <h2>{title}</h2>
          <button type="button" onClick={onClose} aria-label="닫기">
            ×
          </button>
        </div>
        <div className="fridge-modal-body fridge-confirm-modal__body">
          {message}
        </div>
        <div className={`fridge-modal-footer ${showCancel ? '' : 'is-single'}`}>
          {showCancel && (
            <button type="button" className="btn-cancel" onClick={onClose}>
              {cancelText}
            </button>
          )}
          <button
            type="button"
            className={`btn-submit ${danger ? 'btn-danger' : ''}`}
            onClick={onConfirm}
          >
            {confirmText}
          </button>
        </div>
      </div>
    </div>
  )
}
