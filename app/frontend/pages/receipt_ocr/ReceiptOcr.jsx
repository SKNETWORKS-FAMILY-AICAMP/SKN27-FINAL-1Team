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

const weeklyPurchaseData = [
  { week: '1주차', items: 8, amount: 32600 },
  { week: '2주차', items: 12, amount: 48700 },
  { week: '3주차', items: 9, amount: 35400 },
  { week: '4주차', items: 15, amount: 61200 },
  { week: '5주차', items: 11, amount: 42900 },
]

const quantityUnitOptions = ['kg', '개']
const storageOptions = ['냉동', '냉장', '실온']
const aiAnalysisSteps = [
  '이미지 업로드 중',
  '영수증 내용 분석 중',
  '표준 재료명 매칭 중',
  '확인 화면 준비 중',
]

function ImageSlot({ src, alt = '', className = '' }) {
  return (
    <span className={`receipt-image-slot ${src ? 'is-filled' : ''} ${className}`}>
      {src ? <img src={src} alt={alt} /> : null}
    </span>
  )
}

function PurchaseFlowChart({ isLoggedIn }) {
  const weeklyChartMaxAmount = Math.max(...weeklyPurchaseData.map((data) => data.amount))
  const weeklyChartMaxItems = Math.max(...weeklyPurchaseData.map((data) => data.items))
  const weeklyChartPoints = weeklyPurchaseData.map((data, index) => {
    const x = 18 + index * (164 / (weeklyPurchaseData.length - 1))
    const y = 92 - (data.items / weeklyChartMaxItems) * 62
    const barHeight = (data.amount / weeklyChartMaxAmount) * 58
    const barY = 92 - barHeight

    return { ...data, x, y, barHeight, barY }
  })
  const weeklyChartLine = weeklyChartPoints.map((point) => `${point.x},${point.y}`).join(' ')
  const chartId = isLoggedIn ? 'receipt-chart-title' : 'receipt-guest-chart-title'

  return (
    <section className="receipt-panel receipt-chart" aria-labelledby={chartId}>
      <div>
        <h2 id={chartId}>식재료 구매 흐름</h2>
        <p>
          {isLoggedIn
            ? '최근 구매일 기준으로 주차별 식재료 구매량과 금액을 보여줘요.'
            : '최근 구매 금액과 월별 구매 횟수를 기준으로 보여줘요.'}
        </p>
      </div>
      {isLoggedIn ? (
        <div className="receipt-week-chart" role="img" aria-label="주차별 식재료 구매량과 금액 그래프">
          <div className="receipt-week-chart__legend" aria-hidden="true">
            <span className="is-amount">구매 금액</span>
            <span className="is-items">품목 수</span>
          </div>
          <div className="receipt-week-chart__plot">
            <svg viewBox="0 0 200 116" aria-hidden="true" focusable="false">
              <defs>
                <linearGradient id="receipt-week-bar-gradient" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="0%" stopColor="#ffbe75" />
                  <stop offset="100%" stopColor="#ffe9a8" />
                </linearGradient>
              </defs>
              <path className="receipt-week-chart__grid" d="M18 30 H182 M18 61 H182 M18 92 H182" />
              {weeklyChartPoints.map((point) => (
                <rect
                  className="receipt-week-chart__bar"
                  height={point.barHeight}
                  key={`${point.week}-amount`}
                  rx="4"
                  width="18"
                  x={point.x - 9}
                  y={point.barY}
                />
              ))}
              <polyline className="receipt-week-chart__line" points={weeklyChartLine} />
              {weeklyChartPoints.map((point) => (
                <g key={point.week}>
                  <circle className="receipt-week-chart__dot" cx={point.x} cy={point.y} r="4.5" />
                  <text className="receipt-week-chart__value" x={point.x} y={point.y - 9}>
                    {point.items}개
                  </text>
                  <text className="receipt-week-chart__label" x={point.x} y="108">
                    {point.week}
                  </text>
                </g>
              ))}
            </svg>
          </div>
          <ul className="receipt-week-chart__summary" aria-label="주차별 구매 금액">
            {weeklyPurchaseData.map((data) => (
              <li key={data.week}>
                <span>{data.week}</span>
                <strong>{data.amount.toLocaleString()}원</strong>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <div className="receipt-chart__bars" aria-hidden="true">
          <span style={{ height: '42%' }} />
          <span style={{ height: '66%' }} />
          <span style={{ height: '54%' }} />
          <span style={{ height: '82%' }} />
          <span style={{ height: '58%' }} />
        </div>
      )}
    </section>
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

function parseQuantity(quantity) {
  const quantityText = String(quantity ?? '1개')
  const amount = Number.parseFloat(quantityText.replace(/[^\d.]/g, ''))
  const unit = quantityUnitOptions.find((option) => quantityText.includes(option))

  return {
    quantityAmount: Number.isFinite(amount) && amount > 0 ? amount : 1,
    quantityUnit: unit || '개',
  }
}

function normalizeReceiptRows(nextRows) {
  return nextRows.map((row) => ({
    ...row,
    ...parseQuantity(row.quantity),
    storage: row.storage || '냉장',
  }))
}

function formatQuantity(row) {
  return `${row.quantityAmount ?? 1}${row.quantityUnit || '개'}`
}

function formatPriceInput(value) {
  const numericValue = String(value ?? '').replace(/[^\d]/g, '')

  return numericValue ? Number(numericValue).toLocaleString() : ''
}

function ReceiptOcr() {
  const navigate = useNavigate()
  const { dialogNode, showAlert, showConfirm, showPrompt } = useAppDialog()
  const flowTimersRef = useRef([])
  const [isLoggedIn, setIsLoggedIn] = useState(getAuthState)
  const [hasUploaded, setHasUploaded] = useState(false)
  const [activeStep, setActiveStep] = useState(0)
  const [detectedRows, setDetectedRows] = useState(() =>
    normalizeReceiptRows(rows).map((row) => ({ ...row, price: formatPriceInput(row.price) })),
  )
  const [editingRows, setEditingRows] = useState(() => getInitialEditingRows(rows))
  const [receiptSource, setReceiptSource] = useState('샘플 영수증')
  const [isProcessing, setIsProcessing] = useState(false)
  const [analysisStep, setAnalysisStep] = useState(0)
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
  const isAllConfirmed = reviewCount === 0
  const isShowingAnalysisProgress = isProcessing && activeStep === 1
  const analysisProgressPercent = Math.round(((analysisStep + 1) / aiAnalysisSteps.length) * 100)

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
    setAnalysisStep(0)
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
    setAnalysisStep(0)
    setActiveStep(1)

    flowTimersRef.current = [
      ...aiAnalysisSteps.slice(1).map((_, index) =>
        window.setTimeout(() => {
          setAnalysisStep(index + 1)
        }, (index + 1) * 800),
      ),
      window.setTimeout(() => {
        setActiveStep(2)
        setIsProcessing(false)
      }, aiAnalysisSteps.length * 800),
    ]
  }

  const proceedNextStep = async () => {
    clearFlowTimers()
    setIsProcessing(false)
    setAnalysisStep(0)

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
        quantityAmount: 1,
        quantityUnit: '개',
        price: '0',
        category: '기타',
        storage: '냉장',
        review: true,
      },
    ])
    setEditingRows((prev) => ({ ...prev, [name.trim()]: true }))
    setHasUploaded(true)
    setActiveStep(2)
  }

  const updateQuantityAmount = (raw, nextAmount) => {
    const numericAmount = Number.parseFloat(nextAmount)
    const safeAmount = Number.isFinite(numericAmount) ? Math.max(0, numericAmount) : 0

    setDetectedRows((prev) =>
      prev.map((row) =>
        row.raw === raw
          ? {
              ...row,
              quantityAmount: safeAmount,
              quantity: `${safeAmount}${row.quantityUnit || '개'}`,
              review: true,
            }
          : row,
      ),
    )
    setEditingRows((prev) => ({ ...prev, [raw]: true }))
    setActiveStep(2)
  }

  const stepQuantityAmount = (raw, direction) => {
    const targetRow = detectedRows.find((row) => row.raw === raw)
    const currentAmount = Number.parseFloat(targetRow?.quantityAmount)
    const nextAmount = Math.max(0, (Number.isFinite(currentAmount) ? currentAmount : 0) + direction)

    updateQuantityAmount(raw, nextAmount)
  }

  const updateQuantityUnit = (raw, unit) => {
    if (!quantityUnitOptions.includes(unit)) {
      return
    }

    setDetectedRows((prev) =>
      prev.map((row) =>
        row.raw === raw
          ? {
              ...row,
              quantityUnit: unit,
              quantity: `${row.quantityAmount ?? 1}${unit}`,
              review: true,
            }
          : row,
      ),
    )
    setEditingRows((prev) => ({ ...prev, [raw]: true }))
    setActiveStep(2)
  }

  const updateRowField = (raw, field, value) => {
    setDetectedRows((prev) =>
      prev.map((row) =>
        row.raw === raw ? { ...row, [field]: field === 'price' ? formatPriceInput(value) : value, review: true } : row,
      ),
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

  const toggleAllRowsConfirmation = () => {
    const nextReviewState = isAllConfirmed

    setDetectedRows((prev) => prev.map((row) => ({ ...row, review: nextReviewState })))
    setEditingRows(
      detectedRows.reduce((nextEditingRows, row) => {
        nextEditingRows[row.raw] = nextReviewState
        return nextEditingRows
      }, {}),
    )
    setActiveStep(2)
  }

  const resetAnalysis = () => {
    clearFlowTimers()
    setDetectedRows(normalizeReceiptRows(rows).map((row) => ({ ...row, price: formatPriceInput(row.price) })))
    setEditingRows(getInitialEditingRows(rows))
    setReceiptSource('샘플 영수증')
    setHasUploaded(false)
    setIsProcessing(false)
    setAnalysisStep(0)
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
          <h1 id="receipt-title">영수증 입고</h1>
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
          <PurchaseFlowChart isLoggedIn={false} />
        </div>
      ) : !hasUploaded ? (
        <div className="receipt-branch receipt-before-grid">
          <UploadPanel onStartUpload={startUpload} />
          <aside className="receipt-before-side" aria-label="영수증 입고 정보">
            <RecentHistory />
          </aside>
          <PurchaseFlowChart isLoggedIn />
        </div>
      ) : (
        <>
          <section className="receipt-progress-panel" aria-labelledby="receipt-progress-title">
            <div>
              <span>{progressPercent}% 진행</span>
              <h2 id="receipt-progress-title">{currentStepLabel}</h2>
              <p>{progressDescriptions[activeStep]}</p>
            </div>
            {!isShowingAnalysisProgress ? (
              <div className="receipt-progress-panel__bar" aria-label={`진행률 ${progressPercent}%`}>
                <span style={{ width: `${progressPercent}%` }} />
              </div>
            ) : null}
            {isShowingAnalysisProgress ? (
              <div className="receipt-analysis-progress" aria-label="AI 분석 세부 진행 단계">
                <div className="receipt-analysis-progress__bar">
                  <span style={{ width: `${analysisProgressPercent}%` }} />
                </div>
                <ol>
                  {aiAnalysisSteps.map((step, index) => (
                    <li
                      className={[
                        index < analysisStep ? 'is-done' : '',
                        index === analysisStep ? 'is-active' : '',
                      ]
                        .filter(Boolean)
                        .join(' ')}
                      key={step}
                    >
                      {step}
                    </li>
                  ))}
                </ol>
              </div>
            ) : null}
            <button
              className="receipt-primary-button"
              type="button"
              disabled={isProcessing}
              onClick={proceedNextStep}
            >
              {isProcessing ? '분석 진행 중...' : isReadyToStock ? '냉장고 입고 완료하기' : '다음 단계 진행'}
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
                      <dd>{formatQuantity(row)}</dd>
                      <dd>{row.price}원</dd>
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
              <ReceiptRules variant="inline" />
              <div className="receipt-panel__title">
                <h2 id="mapping-title">표준 재료명 매칭</h2>
                <div className="receipt-panel__actions">
                  <button type="button" onClick={toggleAllRowsConfirmation}>
                    {isAllConfirmed ? '전체 확인 취소' : '전체 확인'}
                  </button>
                  <span>전체 금액 {totalAmount.toLocaleString()}원</span>
                </div>
              </div>
              <p className="receipt-mapping__helper">
                OCR 결과는 먼저 모두 수정 가능하게 열려 있어요. 수량과 금액을 확인한 뒤 확정을 누르면 해당 행이 잠깁니다.
              </p>

              <div className="receipt-mapping-table" role="table" aria-label="표준 재료명 매칭 결과">
                <div className="receipt-mapping-row receipt-mapping-row--head" role="row">
                  <span role="columnheader">재료</span>
                  <span role="columnheader">입고 정보</span>
                  <span role="columnheader">보관</span>
                  <span role="columnheader">확인</span>
                </div>
                {detectedRows.map((row) => {
                  const isEditing = Boolean(editingRows[row.raw])

                  return (
                  <div className={`receipt-mapping-row ${isEditing ? 'is-editing' : ''}`} role="row" key={row.raw}>
                    <span className="receipt-mapping-name-cell" role="cell">
                      <ImageSlot className="receipt-mapping-row__image" src={row.image} />
                      <b>
                        <small>원재료명: {row.raw}</small>
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
                      </b>
                    </span>
                    <span className="receipt-mapping-details" role="cell">
                      <label className="receipt-quantity-field">
                        <small>수량</small>
                        <span className="receipt-quantity-control">
                          <button
                            aria-label={`${row.name} 수량 감소`}
                            disabled={!isEditing}
                            type="button"
                            onClick={() => stepQuantityAmount(row.raw, -1)}
                          >
                            -
                          </button>
                          <input
                            aria-label={`${row.name} 수량`}
                            className="receipt-inline-input"
                            min="0"
                            step={row.quantityUnit === 'kg' ? '0.1' : '1'}
                            type="number"
                            value={row.quantityAmount ?? 1}
                            disabled={!isEditing}
                            onChange={(event) => updateQuantityAmount(row.raw, event.target.value)}
                          />
                          <button
                            aria-label={`${row.name} 수량 증가`}
                            disabled={!isEditing}
                            type="button"
                            onClick={() => stepQuantityAmount(row.raw, 1)}
                          >
                            +
                          </button>
                        </span>
                        <select
                          aria-label={`${row.name} 단위`}
                          className="receipt-inline-select"
                          disabled={!isEditing}
                          value={row.quantityUnit || '개'}
                          onChange={(event) => updateQuantityUnit(row.raw, event.target.value)}
                        >
                          {quantityUnitOptions.map((unit) => (
                            <option key={unit} value={unit}>
                              {unit}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        <small>금액(원)</small>
                        <input
                          aria-label={`${row.name} 금액`}
                          className="receipt-inline-input receipt-inline-input--price"
                          inputMode="numeric"
                          pattern="[0-9,]*"
                          type="text"
                          value={row.price}
                          disabled={!isEditing}
                          onChange={(event) => updateRowField(row.raw, 'price', event.target.value)}
                        />
                      </label>
                    </span>
                    <span role="cell" className="receipt-storage-cell">
                      <select
                        aria-label={`${row.name} 보관 방법`}
                        className="receipt-storage-select"
                        disabled={!isEditing}
                        value={row.storage || '냉장'}
                        onChange={(event) => updateRowField(row.raw, 'storage', event.target.value)}
                      >
                        {storageOptions.map((storage) => (
                          <option key={storage} value={storage}>
                            {storage}
                          </option>
                        ))}
                      </select>
                    </span>
                    <span className="receipt-row-status" role="cell">
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
                        <b>{!row.review && !isEditing ? '확인 완료' : '확인 필요'}</b>
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
        <p>영수증 사진(PNG, JPG, JPEG)을 드래그하거나 업로드/촬영 버튼을 눌러주세요.</p>
        <div>
          <button className="receipt-primary-button" type="button" onClick={() => onStartUpload('업로드 이미지')}>
            이미지 업로드
          </button>
          <button className="receipt-soft-button" type="button" onClick={() => onStartUpload('카메라 촬영본')}>
            카메라 촬영
          </button>
        </div>
      </div>
      <p className="receipt-tip">영수증 전체가 보이도록 밝은 곳에서 정면으로 촬영해주세요.</p>
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
        <h2 id="receipt-history-title">최근 영수증 내역</h2>
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

function ReceiptRules({ variant = '' }) {
  return (
    <section
      className={['receipt-rules', variant ? `receipt-rules--${variant}` : 'receipt-panel'].join(' ')}
      aria-labelledby="receipt-rules-title"
    >
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
