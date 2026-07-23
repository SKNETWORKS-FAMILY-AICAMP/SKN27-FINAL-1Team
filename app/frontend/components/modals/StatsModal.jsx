import React from 'react'
import './StatsModal.css'

export default function StatsModal({ isOpen, onClose, summary }) {
  if (!isOpen || !summary) return null

  // 계산 로직 (간단한 프로그레스 바 너비용)
  const total = summary.total || 0
  const urgent = summary.expiring_soon || 0
  const expired = summary.expired || 0
  const cold = summary.storage['냉장'] || 0
  const freeze = summary.storage['냉동'] || 0
  const room = summary.storage['실온'] || 0

  const urgentRatio = total > 0 ? Math.round((urgent / total) * 100) : 0
  const expiredRatio = total > 0 ? Math.round((expired / total) * 100) : 0
  const coldRatio = total > 0 ? Math.round((cold / total) * 100) : 0
  const freezeRatio = total > 0 ? Math.round((freeze / total) * 100) : 0
  const roomRatio = total > 0 ? Math.round((room / total) * 100) : 0

  return (
    <div className="fridge-modal-overlay">
      <div className="fridge-modal-content stats-modal" onClick={(e) => e.stopPropagation()}>
        <div className="fridge-modal-header">
          <h2>내 냉장고 통계</h2>
          <button type="button" onClick={onClose} aria-label="닫기">✕</button>
        </div>
        <div className="fridge-modal-body stats-modal-body">
          <div className="stats-card" style={{ textAlign: 'center', backgroundColor: '#fffbf0', borderColor: '#f4d19b' }}>
            <h3 style={{ fontSize: '18px', marginBottom: '8px', color: '#8b673e' }}>내 냉장고 총 재료</h3>
            <div style={{ fontSize: '32px', fontWeight: 'bold', color: 'var(--figma-coral)' }}>
              {total}<span style={{ fontSize: '20px', color: '#666' }}> 개</span>
            </div>
          </div>

          <div className="stats-card">
            <h3>소비 임박 비율</h3>
            <div className="stats-progress-bg">
              <div className="stats-progress-fill urgent-fill" style={{ width: `${urgentRatio}%` }}></div>
            </div>
            <p className="stats-text">
              전체 {total}개 중 <strong>{urgent}개 ({urgentRatio}%)</strong>가 위험해요!
            </p>
          </div>

          <div className="stats-card">
            <h3>보관 방식 현황</h3>
            <div className="stats-bar-group">
              <div className="stats-bar-label">냉장 ({cold}개)</div>
              <div className="stats-progress-bg">
                <div className="stats-progress-fill cold-fill" style={{ width: `${coldRatio}%` }}></div>
              </div>
            </div>
            <div className="stats-bar-group">
              <div className="stats-bar-label">냉동 ({freeze}개)</div>
              <div className="stats-progress-bg">
                <div className="stats-progress-fill freeze-fill" style={{ width: `${freezeRatio}%` }}></div>
              </div>
            </div>
            <div className="stats-bar-group">
              <div className="stats-bar-label">실온 ({room}개)</div>
              <div className="stats-progress-bg">
                <div className="stats-progress-fill room-fill" style={{ width: `${roomRatio}%` }}></div>
              </div>
            </div>
          </div>
        </div>
        <div className="fridge-modal-footer">
          <button type="button" className="btn-submit" onClick={onClose} style={{width: '100%'}}>닫기</button>
        </div>
      </div>
    </div>
  )
}
