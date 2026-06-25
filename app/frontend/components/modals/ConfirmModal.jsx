import React, { useEffect } from 'react'

export default function ConfirmModal({ isOpen, title, message, onConfirm, onClose }) {
  useEffect(() => {
    if (!isOpen) return

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
            ✕
          </button>
        </div>
        <div 
          className="fridge-modal-body" 
          style={{ textAlign: 'center', padding: '30px 20px', fontSize: '16px', color: 'var(--figma-text)', whiteSpace: 'pre-wrap', lineHeight: '1.6' }}
        >
          {message}
        </div>
        <div className="fridge-modal-footer">
          <button type="button" className="btn-cancel" onClick={onClose}>취소</button>
          <button type="button" className="btn-submit btn-danger" onClick={onConfirm}>확인</button>
        </div>
      </div>
    </div>
  )
}
