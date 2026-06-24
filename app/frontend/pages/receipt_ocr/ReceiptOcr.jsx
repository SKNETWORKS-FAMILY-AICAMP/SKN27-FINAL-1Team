import React, { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import './ReceiptOcr.css'

import iconReceipt from '../../assets/extracted/icons/icon_receipt.png'
import iconRefrigerator from '../../assets/extracted/icons/icon_refrigerator.png'
import imageHello from '../../assets/extracted/images/image_hello.png'
import imageReceipt from '../../assets/extracted/images/image_receipt registration.png'
import { useAppDialog } from '../../components/AppDialog.jsx'
import {
  receiptHistory,
  receiptRows as rows,
  receiptRules,
  receiptSteps as steps,
} from '../../mock/receiptOcrMock.js'

function ImageSlot({ src, alt = '', className = '' }) {
  return (
    <span className={`receipt-image-slot ${src ? 'is-filled' : ''} ${className}`}>
      {src ? <img src={src} alt={alt} /> : null}
    </span>
  )
}

function getAuthState() {
  if (typeof window === 'undefined') {
    return false
  }

  return Boolean(
    window.localStorage.getItem('bobbeori-token') ||
      window.localStorage.getItem('bobbeori-auth-mode') === 'guest',
  )
}

function getInitialEditingRows(nextRows) {
  return nextRows.reduce((acc, row) => {
    acc[row.raw] = true
    return acc
  }, {})
}

function toNumber(value, fallback = 0) {
  const number = Number(String(value).replace(/[^\d.]/g, ''))
  return Number.isFinite(number) ? number : fallback
}

function ReceiptOcr() {
  const navigate = useNavigate()
  const { dialogNode, showAlert, showConfirm, showPrompt } = useAppDialog()
  const flowTimersRef = useRef([])
  const [isLoggedIn, setIsLoggedIn] = useState(getAuthState)
  const [hasUploaded, setHasUploaded] = useState(false)
  const [activeStep, setActiveStep] = useState(0)
  const [detectedRows, setDetectedRows] = useState(rows)
  const [editingRows, setEditingRows] = useState(() => getInitialEditingRows(rows))
  const [receiptSource, setReceiptSource] = useState('샘플 영수증')
  const [isProcessing, setIsProcessing] = useState(false)
  const [previewScale, setPreviewScale] = useState('normal')

  const mappedCount = detectedRows.filter((row) => !row.review && !editingRows[row.raw]).length
  const reviewCount = detectedRows.length - mappedCount
  const totalAmount = detectedRows.reduce((sum, row) => {
    const numericPrice = Number(row.price.replace(/[^\d]/g, ''))
    return sum + (Number.isFinite(numericPrice) ? numericPrice : 0)
  }, 0)
  const progressPercent = hasUploaded ? Math.round(((activeStep + 1) / steps.length) * 100) : 0
  const currentStepLabel = steps[activeStep]
  const isReadyToStock = hasUploaded && activeStep >= steps.length - 1

  const progressDescriptions = [
    '영수증을 올리거나 촬영하면 분석을 시작해요.',
    isProcessing
      ? `${receiptSource} 기준으로 품목과 금액을 읽는 중이에요.`
      : `${receiptSource} 기준으로 품목과 금액을 읽었어요.`,
    reviewCount
      ? `${detectedRows.length}개 품목을 찾았어요. 확인한 품목은 확정을 눌러 잠가주세요.`
      : `${detectedRows.length}개 품목이 모두 확정됐어요.`,
    `총 ${detectedRows.length}개 재료를 냉장고에 입고할 준비가 끝났어요.`,
  ]

  const clearFlowTimers = () => {
    flowTimersRef.current.forEach((timerId) => window.clearTimeout(timerId))
    flowTimersRef.current = []
  }

  const moveToStep = (nextStep) => {
    if (!hasUploaded && nextStep > 0) {
      return
    }

    clearFlowTimers()
    setIsProcessing(false)
    setActiveStep(Math.max(0, Math.min(nextStep, steps.length - 1)))
  }

  const requestLogin = async () => {
    const confirmed = await showConfirm('영수증 분석과 냉장고 입고는 로그인 후 사용할 수 있어요.', {
      title: '로그인이 필요해요',
      confirmText: '로그인하기',
      cancelText: '닫기',
    })

    if (confirmed) {
      navigate('/login')
    }
  }

  const startUpload = (source) => {
    if (!isLoggedIn) {
      requestLogin()
      return
    }

    clearFlowTimers()
    setReceiptSource(source)
    setHasUploaded(true)
    setIsProcessing(true)
    setActiveStep(1)

    const autoSteps = [2]
    flowTimersRef.current = autoSteps.map((step, index) =>
      window.setTimeout(() => {
        setActiveStep(step)

        if (step === 2) {
          setIsProcessing(false)
        }
      }, (index + 1) * 650),
    )
  }

  const proceedNextStep = async () => {
    clearFlowTimers()
    setIsProcessing(false)

    if (!hasUploaded) {
      await showAlert('먼저 영수증을 업로드하거나 촬영해주세요.', {
        title: '영수증이 필요해요',
      })
      return
    }

    if (isReadyToStock) {
      stockIngredients()
      return
    }

    if (activeStep === 2 && reviewCount > 0) {
      await showAlert('아직 확정되지 않은 항목이 있어요. 수량과 금액을 확인한 뒤 확정 체크를 눌러주세요.', {
        title: '확인이 필요해요',
      })
      return
    }

    moveToStep(activeStep + 1)
  }

  const addRow = async () => {
    const name = await showPrompt('추가할 품목명을 입력해주세요.', {
      title: '품목 추가',
      placeholder: '예: 대파',
    })

    if (!name?.trim()) {
      return
    }

    setDetectedRows((prev) => [
      ...prev,
      {
        raw: name.trim(),
        name: name.trim(),
        quantity: '1개',
        price: '0원',
        category: '기타',
        review: true,
      },
    ])
    setEditingRows((prev) => ({ ...prev, [name.trim()]: true }))
    setHasUploaded(true)
    setActiveStep(2)
  }

  const updateRowField = (raw, field, value) => {
    setDetectedRows((prev) =>
      prev.map((row) => (row.raw === raw ? { ...row, [field]: value, review: true } : row)),
    )
    setEditingRows((prev) => ({ ...prev, [raw]: true }))
    setActiveStep(2)
  }

  const setRowEditing = (raw, isEditing) => {
    setEditingRows((prev) => ({ ...prev, [raw]: isEditing }))

    if (isEditing) {
      setDetectedRows((prev) => prev.map((row) => (row.raw === raw ? { ...row, review: true } : row)))
      setActiveStep(2)
    } else {
      confirmRow(raw)
    }
  }

  const confirmRow = (raw) => {
    setDetectedRows((prev) => prev.map((row) => (row.raw === raw ? { ...row, review: false } : row)))
    setEditingRows((prev) => ({ ...prev, [raw]: false }))
    setActiveStep(2)
  }

  const resetAnalysis = () => {
    clearFlowTimers()
    setDetectedRows(rows)
    setEditingRows(getInitialEditingRows(rows))
    setReceiptSource('샘플 영수증')
    setHasUploaded(false)
    setIsProcessing(false)
    setActiveStep(0)
  }

  const stockIngredients = async () => {
    if (!hasUploaded) {
      return
    }

    if (reviewCount > 0) {
      const confirmed = await showConfirm('검토 필요 항목이 남아 있어요. 그래도 냉장고에 입고할까요?', {
        title: '냉장고 입고 확인',
        confirmText: '입고하기',
        cancelText: '돌아가기',
      })

      if (!confirmed) {
        return
      }
    }

    const token = window.localStorage.getItem('bobbeori-token')
    if (token) {
      const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000'
      const calendarCostEnabled = window.localStorage.getItem('bobbeori-calendar-cost-enabled') !== 'false'

      try {
        await fetch(`${apiUrl}/api/v1/receipts/confirm`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            calendar_cost_enabled: calendarCostEnabled,
            items: detectedRows.map((row) => ({
              name: row.name,
              quantity: toNumber(row.quantity, 1),
              storage_method: '냉장',
              price: toNumber(row.price, 0),
            })),
          }),
        })
      } catch (err) {
        console.error(err)
      }
    }

    window.localStorage.setItem('bobbeori-last-stocked-count', String(detectedRows.length))
    navigate('/fridge')
  }

  useEffect(() => {
    const syncAuthState = () => setIsLoggedIn(getAuthState())

    window.addEventListener('bobbeori-auth-change', syncAuthState)
    window.addEventListener('storage', syncAuthState)

    return () => {
      clearFlowTimers()
      window.removeEventListener('bobbeori-auth-change', syncAuthState)
      window.removeEventListener('storage', syncAuthState)
    }
  }, [])

  return (
    <section className="receipt-page" aria-labelledby="receipt-title">
      <div className="receipt-hero">
        <div className="receipt-hero__copy">
          <h1 id="receipt-title">영수증 OCR 입고</h1>
          <p>영수증 한 장으로 재료를 똑똑하게 등록해요!</p>
        </div>
        <ImageSlot className="receipt-hero__image" src={imageReceipt} />
      </div>

      <div className="receipt-stepper" aria-label="OCR 진행 단계">
        {steps.map((step, index) => (
          <React.Fragment key={step}>
            <button
              className={[
                index === activeStep ? 'is-active' : '',
                hasUploaded && index < activeStep ? 'is-done' : '',
              ]
                .filter(Boolean)
                .join(' ')}
              type="button"
              onClick={() => moveToStep(index)}
            >
              <span>{step}</span>
            </button>
            {index < steps.length - 1 ? <i aria-hidden="true" /> : null}
          </React.Fragment>
        ))}
      </div>

      {!isLoggedIn ? (
        <div className="receipt-branch receipt-guest-grid">
          <UploadPanel onStartUpload={startUpload} />
          <section className="receipt-panel receipt-login-notice" aria-labelledby="receipt-login-title">
            <ImageSlot className="receipt-login-notice__image" src={imageHello} />
            <h2 id="receipt-login-title">로그인이 필요해요</h2>
            <p>
              업로드한 영수증은 냉장고와 연결되어 저장돼요. 로그인하면 OCR 분석 결과를 바로
              확인하고 내 식재료로 등록할 수 있어요.
            </p>
            <button className="receipt-primary-button" type="button" onClick={() => navigate('/login')}>
              로그인하러 가기
            </button>
          </section>
        </div>
      ) : !hasUploaded ? (
        <div className="receipt-branch receipt-before-grid">
          <UploadPanel onStartUpload={startUpload} />
          <aside className="receipt-before-side" aria-label="영수증 입고 정보">
            <RecentHistory />
            <ReceiptRules />
          </aside>
          <section className="receipt-panel receipt-chart" aria-labelledby="receipt-chart-title">
            <div>
              <h2 id="receipt-chart-title">식재료 구매 흐름</h2>
              <p>최근 구매 금액과 월별 구매 횟수를 기준으로 보여줘요.</p>
            </div>
            <div className="receipt-chart__bars" aria-hidden="true">
              <span style={{ height: '42%' }} />
              <span style={{ height: '66%' }} />
              <span style={{ height: '54%' }} />
              <span style={{ height: '82%' }} />
              <span style={{ height: '58%' }} />
            </div>
          </section>
        </div>
      ) : (
        <>
          <section className="receipt-progress-panel" aria-labelledby="receipt-progress-title">
            <div>
              <span>{progressPercent}% 진행</span>
              <h2 id="receipt-progress-title">{currentStepLabel}</h2>
              <p>{progressDescriptions[activeStep]}</p>
            </div>
            <div className="receipt-progress-panel__bar" aria-label={`진행률 ${progressPercent}%`}>
              <span style={{ width: `${progressPercent}%` }} />
            </div>
            <button
              className="receipt-primary-button"
              type="button"
              disabled={isProcessing}
              onClick={proceedNextStep}
            >
              {isProcessing ? 'OCR 진행 중...' : isReadyToStock ? '냉장고 입고 완료하기' : '다음 단계 진행'}
            </button>
          </section>

          <div className="receipt-branch receipt-after-grid">
            <section className="receipt-panel receipt-preview-panel" aria-labelledby="preview-title">
              <div className="receipt-preview__title">
                <h2 id="preview-title">영수증 미리보기</h2>
                <button type="button" onClick={resetAnalysis}>
                  다시 촬영
                </button>
              </div>
              <article className={`receipt-paper receipt-paper--${previewScale}`}>
                <strong>BABBEORI MART</strong>
                <span>2026.06.18 14:32</span>
                <dl>
                  {detectedRows.map((row) => (
                    <div key={row.raw}>
                      <dt>{row.raw}</dt>
                      <dd>{row.quantity}</dd>
                      <dd>{row.price}</dd>
                    </div>
                  ))}
                </dl>
                <b>합계 {totalAmount.toLocaleString()}원</b>
              </article>
              <div className="receipt-preview-tools">
                <span>영수증 확대</span>
                <button
                  className={previewScale === 'normal' ? 'is-active' : ''}
                  type="button"
                  onClick={() => setPreviewScale('normal')}
                >
                  기본
                </button>
                <button
                  className={previewScale === 'large' ? 'is-active' : ''}
                  type="button"
                  onClick={() => setPreviewScale('large')}
                >
                  확대
                </button>
              </div>
            </section>

            <section className="receipt-panel receipt-mapping" aria-labelledby="mapping-title">
              <div className="receipt-panel__title">
                <h2 id="mapping-title">표준 재료명 매칭</h2>
                <span>전체 금액 {totalAmount.toLocaleString()}원</span>
              </div>
              <p className="receipt-mapping__helper">
                OCR 결과는 먼저 모두 수정 가능하게 열려 있어요. 수량과 금액을 확인한 뒤 확정을 누르면 해당 행이 잠깁니다.
              </p>

              <div className="receipt-mapping-table" role="table" aria-label="표준 재료명 매칭 결과">
                <div className="receipt-mapping-row receipt-mapping-row--head" role="row">
                  <span role="columnheader">재료</span>
                  <span role="columnheader">입고 정보</span>
                  <span role="columnheader">분류</span>
                  <span role="columnheader">확인</span>
                </div>
                {detectedRows.map((row) => {
                  const isEditing = Boolean(editingRows[row.raw])

                  return (
                  <div className={`receipt-mapping-row ${isEditing ? 'is-editing' : ''}`} role="row" key={row.raw}>
                    <span className="receipt-mapping-name-cell" role="cell">
                      <ImageSlot className="receipt-mapping-row__image" src={row.image} />
                      <b>
                        {isEditing ? (
                          <input
                            aria-label={`${row.raw} 표준 재료명`}
                            className="receipt-inline-input"
                            type="text"
                            value={row.name}
                            onChange={(event) => updateRowField(row.raw, 'name', event.target.value)}
                          />
                        ) : (
                          row.name
                        )}
                        <small>원문: {row.raw}</small>
                      </b>
                    </span>
                    <span className="receipt-mapping-details" role="cell">
                      <label>
                        <small>수량</small>
                        <input
                          aria-label={`${row.name} 수량`}
                          className="receipt-inline-input"
                          type="text"
                          value={row.quantity}
                          disabled={!isEditing}
                          onChange={(event) => updateRowField(row.raw, 'quantity', event.target.value)}
                        />
                      </label>
                      <label>
                        <small>금액</small>
                        <input
                          aria-label={`${row.name} 금액`}
                          className="receipt-inline-input receipt-inline-input--price"
                          type="text"
                          value={row.price}
                          disabled={!isEditing}
                          onChange={(event) => updateRowField(row.raw, 'price', event.target.value)}
                        />
                      </label>
                    </span>
                    <span role="cell" className="is-category">
                      {row.category}
                    </span>
                    <span className="receipt-row-status" role="cell">
                      <strong className={row.review || isEditing ? 'is-review' : ''}>
                        {row.review || isEditing ? '확인 중' : '확정 완료'}
                      </strong>
                      <label className={`receipt-confirm-toggle ${!row.review && !isEditing ? 'is-confirmed' : ''}`}>
                        <input
                          type="checkbox"
                          checked={!row.review && !isEditing}
                          onChange={(event) => {
                            if (event.target.checked) {
                              confirmRow(row.raw)
                              return
                            }

                            setRowEditing(row.raw, true)
                          }}
                        />
                        <span aria-hidden="true" />
                        <b>{!row.review && !isEditing ? '확정' : '수정 중'}</b>
                      </label>
                    </span>
                  </div>
                  )
                })}
              </div>

              <button className="receipt-add-row" type="button" onClick={addRow}>
                + 행 추가
              </button>
              <p className="receipt-success">
                총 상품 {detectedRows.length}개, 총 금액 {totalAmount.toLocaleString()}원. 확인 완료
                {' '}
                {mappedCount}개, 수정 필요 {reviewCount}개예요.
              </p>
              <button className="receipt-stock-button" type="button" onClick={stockIngredients}>
                <ImageSlot className="receipt-stock-button__icon" src={iconRefrigerator} />
                냉장고에 입고하기
                <small>총 {detectedRows.length}개 재료가 등록돼요!</small>
              </button>
            </section>
          </div>
        </>
      )}
      {dialogNode}
    </section>
  )
}

function UploadPanel({ onStartUpload }) {
  return (
    <section className="receipt-panel receipt-upload" aria-labelledby="upload-title">
      <h2 id="upload-title">영수증 업로드</h2>
      <div className="receipt-dropzone">
        <ImageSlot className="receipt-dropzone__icon" src={iconReceipt} />
        <p>영수증 사진을 드래그하거나 업로드/촬영 버튼을 눌러주세요.</p>
        <div>
          <button className="receipt-primary-button" type="button" onClick={() => onStartUpload('업로드 이미지')}>
            이미지 업로드
          </button>
          <button className="receipt-soft-button" type="button" onClick={() => onStartUpload('카메라 촬영본')}>
            카메라 촬영
          </button>
        </div>
      </div>
      <p className="receipt-tip">사진은 정면에서 밝게 촬영하면 인식률이 올라가요.</p>
    </section>
  )
}

function RecentHistory() {
  const [selectedHistory, setSelectedHistory] = useState(receiptHistory[0])
  const [showAllHistory, setShowAllHistory] = useState(false)
  const visibleHistory = showAllHistory ? receiptHistory : receiptHistory.slice(0, 3)

  return (
    <section className="receipt-panel receipt-history" aria-labelledby="receipt-history-title">
      <div className="receipt-panel__title">
        <h2 id="receipt-history-title">최근 OCR 내역</h2>
        <button type="button" onClick={() => setShowAllHistory((prev) => !prev)}>
          {showAllHistory ? '접기' : '내역보기'}
        </button>
      </div>
      <div className="receipt-history-list">
        {visibleHistory.map((item) => (
          <button
            className={selectedHistory?.title === item.title ? 'is-active' : ''}
            key={item.title}
            type="button"
            onClick={() => setSelectedHistory(item)}
          >
            <span aria-hidden="true" />
            <div>
              <strong>{item.title}</strong>
              <p>{item.meta}</p>
            </div>
            <b>{item.amount}</b>
            <em>{item.status}</em>
          </button>
        ))}
      </div>
      {selectedHistory ? (
        <article className="receipt-history-detail" aria-label={`${selectedHistory.title} 상세 내역`}>
          <div>
            <span>{selectedHistory.date}</span>
            <strong>{selectedHistory.store}</strong>
            <b>{selectedHistory.amount}</b>
          </div>
          <ul>
            {selectedHistory.items.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
          <p>{selectedHistory.note}</p>
        </article>
      ) : null}
    </section>
  )
}

function ReceiptRules() {
  return (
    <section className="receipt-panel receipt-rules" aria-labelledby="receipt-rules-title">
      <h2 id="receipt-rules-title">입고 규칙</h2>
      <div className="receipt-rule-list">
        {receiptRules.map((rule) => (
          <article key={rule.title}>
            <span aria-hidden="true" />
            <div>
              <strong>{rule.title}</strong>
              <p>{rule.description}</p>
            </div>
            <em>{rule.enabled ? 'ON' : '후보'}</em>
          </article>
        ))}
      </div>
    </section>
  )
}

export default ReceiptOcr
