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
const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const maxUploadSizeMb = 10
const acceptedImageTypes = ['image/jpeg', 'image/png', 'image/webp']
const aiAnalysisSteps = [
  '이미지 업로드 중',
  '영수증 내용 분석 중',
  '표준 재료명 매칭 중',
  '확인 화면 준비 중',
]

function getFrequentIngredients(history) {
  const counts = history.reduce((acc, receipt) => {
    receipt.items.forEach((item) => {
      const ingredientName = String(item)
        .replace(/\s*\d+(?:\.\d+)?\s*(?:kg|g|개|단|팩|통|봉|송이)$/i, '')
        .trim()

      if (!ingredientName) {
        return
      }

      acc[ingredientName] = (acc[ingredientName] || 0) + 1
    })

    return acc
  }, {})

  return Object.entries(counts)
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name))
    .slice(0, 4)
}

const frequentIngredientData = getFrequentIngredients(receiptHistory)

function ImageSlot({ src, alt = '', className = '' }) {
  return (
    <span className={`receipt-image-slot ${src ? 'is-filled' : ''} ${className}`}>
      {src ? <img src={src} alt={alt} /> : null}
    </span>
  )
}

function FrequentIngredientsChart() {
  const maxCount = Math.max(...frequentIngredientData.map((ingredient) => ingredient.count), 1)

  return (
    <section className="receipt-frequent-chart" aria-labelledby="receipt-frequent-title">
      <div className="receipt-frequent-chart__title">
        <h3 id="receipt-frequent-title">자주 구매한 재료</h3>
        <span>최근 영수증 기준</span>
      </div>
      <ul>
        {frequentIngredientData.map((ingredient) => (
          <li key={ingredient.name}>
            <span>{ingredient.name}</span>
            <div aria-hidden="true">
              <b style={{ width: `${Math.max((ingredient.count / maxCount) * 100, 18)}%` }} />
            </div>
            <strong>{ingredient.count}회</strong>
          </li>
        ))}
      </ul>
    </section>
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
    <section className={`receipt-panel receipt-chart ${isLoggedIn ? 'is-logged-in' : ''}`} aria-labelledby={chartId}>
      <div>
        <h2 id={chartId}>식재료 구매 흐름</h2>
        <p>
          {isLoggedIn
            ? '최근 구매일 기준으로 주차별 식재료 구매량과 금액을 보여줘요.'
            : '최근 구매 금액과 월별 구매 횟수를 기준으로 보여줘요.'}
        </p>
      </div>
      {isLoggedIn ? (
        <>
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
          <FrequentIngredientsChart />
        </>
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
    acc[row.id] = true
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
  return nextRows.map((row, index) => ({
    id: row.id || `mock-${index}-${row.raw || row.name || 'item'}`,
    ...row,
    ...parseQuantity(row.quantity),
    storage: row.storage || '냉장',
  }))
}

function createInitialReceiptRows() {
  return normalizeReceiptRows(rows).map((row) => ({ ...row, price: formatPriceInput(row.price) }))
}

function formatQuantity(row) {
  return `${row.quantityAmount ?? 1}${row.quantityUnit || '개'}`
}

function formatPriceInput(value) {
  const numericValue = String(value ?? '').replace(/[^\d]/g, '')

  return numericValue ? Number(numericValue).toLocaleString() : ''
}

function toNumber(value, fallback = null) {
  const numericValue = Number(String(value ?? '').replace(/[^\d.-]/g, ''))

  return Number.isFinite(numericValue) ? numericValue : fallback
}

function normalizeOcrUnit(unit) {
  return quantityUnitOptions.includes(unit) ? unit : '개'
}

function mapOcrItemsToRows(items = []) {
  return items.map((item, index) => {
    const rawName = item.raw_name || `품목 ${index + 1}`
    const quantityAmount = Number.parseFloat(item.quantity)
    const safeQuantityAmount = Number.isFinite(quantityAmount) && quantityAmount > 0 ? quantityAmount : 1
    const quantityUnit = normalizeOcrUnit(item.unit)

    return {
      id: `ocr-${index}-${rawName}`,
      raw: rawName,
      name: item.normalized_name || rawName,
      quantity: `${safeQuantityAmount}${quantityUnit}`,
      quantityAmount: safeQuantityAmount,
      quantityUnit,
      price: formatPriceInput(item.item_amount),
      category: item.is_food === false ? '기타' : '식재료',
      storage: '냉장',
      review: true,
    }
  })
}

function ReceiptOcr() {
  const navigate = useNavigate()
  const { dialogNode, showAlert, showConfirm, showPrompt } = useAppDialog()
  const flowTimersRef = useRef([])
  const [isLoggedIn, setIsLoggedIn] = useState(getAuthState)
  const [hasUploaded, setHasUploaded] = useState(false)
  const [activeStep, setActiveStep] = useState(0)
  const [detectedRows, setDetectedRows] = useState(createInitialReceiptRows)
  const [editingRows, setEditingRows] = useState(() => getInitialEditingRows(createInitialReceiptRows()))
  const [receiptSource, setReceiptSource] = useState('샘플 영수증')
  const [receiptMeta, setReceiptMeta] = useState(null)
  const [isProcessing, setIsProcessing] = useState(false)
  const [analysisStep, setAnalysisStep] = useState(0)
  const [previewScale, setPreviewScale] = useState('normal')

  const mappedCount = detectedRows.filter((row) => !row.review && !editingRows[row.id]).length
  const reviewCount = detectedRows.length - mappedCount
  const totalAmount = detectedRows.reduce((sum, row) => {
    const numericPrice = Number(row.price.replace(/[^\d]/g, ''))
    return sum + (Number.isFinite(numericPrice) ? numericPrice : 0)
  }, 0)
  const progressPercent = hasUploaded ? Math.round(((activeStep + 1) / steps.length) * 100) : 0
  const currentStepLabel = steps[activeStep]
  const isReadyToStock = hasUploaded && activeStep >= steps.length - 1
  const isAllConfirmed = detectedRows.length > 0 && reviewCount === 0
  const isStockDisabled = reviewCount > 0 || detectedRows.length === 0
  const isShowingAnalysisProgress = isProcessing && activeStep === 1
  const analysisProgressPercent = Math.round(((analysisStep + 1) / aiAnalysisSteps.length) * 100)

  const progressDescriptions = [
    '영수증을 올리거나 촬영하면 분석을 시작해요.',
    isProcessing
      ? `${receiptSource} 기준으로 품목과 금액을 읽는 중이에요.`
      : `${receiptSource} 기준으로 품목과 금액을 읽었어요.`,
    detectedRows.length === 0
      ? '품목 리스트를 찾지 못했어요. 필요한 품목은 직접 추가해서 등록할 수 있어요.'
      : reviewCount
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

  const startUpload = async (file, source) => {
    if (!isLoggedIn) {
      requestLogin()
      return
    }

    const token = window.localStorage.getItem('bobbeori-token')
    if (!token) {
      requestLogin()
      return
    }

    if (!file) {
      return
    }

    if (!acceptedImageTypes.includes(file.type)) {
      await showAlert('JPG, PNG, WEBP 형식의 영수증 이미지만 업로드할 수 있어요.', {
        title: '지원하지 않는 파일이에요',
      })
      return
    }

    if (file.size > maxUploadSizeMb * 1024 * 1024) {
      await showAlert(`영수증 이미지는 ${maxUploadSizeMb}MB 이하만 업로드할 수 있어요.`, {
        title: '파일이 너무 커요',
      })
      return
    }

    clearFlowTimers()
    setReceiptSource(file.name || source)
    setReceiptMeta(null)
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
    ]

    const formData = new FormData()
    formData.append('file', file)

    try {
      const response = await fetch(`${apiUrl}/api/v1/receipts/upload`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
        },
        body: formData,
      })
      const data = await response.json().catch(() => ({}))

      if (!response.ok) {
        throw new Error(data.detail || '영수증 OCR 분석에 실패했어요.')
      }

      const nextRows = mapOcrItemsToRows(data.items)
      setDetectedRows(nextRows)
      setEditingRows(getInitialEditingRows(nextRows))
      setReceiptMeta({
        receiptId: data.receipt_id,
        originalFileName: data.original_file_name,
        originalFilePath: data.original_file_path,
        storeName: data.store_name,
        purchaseDatetime: data.purchase_datetime,
        totalAmount: data.total_amount,
        confidenceNote: data.confidence_note,
      })
      setReceiptSource(data.store_name || data.original_file_name || file.name || source)
      setAnalysisStep(aiAnalysisSteps.length - 1)
      setActiveStep(2)
    } catch (error) {
      console.error(error)
      setHasUploaded(false)
      setActiveStep(0)
      await showAlert(error.message || '영수증 분석 중 문제가 발생했어요.', {
        title: '분석에 실패했어요',
      })
    } finally {
      clearFlowTimers()
      setIsProcessing(false)
    }
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

    const newRowId = `manual-${Date.now()}-${name.trim()}`

    setDetectedRows((prev) => [
      ...prev,
      {
        id: newRowId,
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
    setEditingRows((prev) => ({ ...prev, [newRowId]: true }))
    setHasUploaded(true)
    setActiveStep(2)
  }

  const updateQuantityAmount = (rowId, nextAmount) => {
    const numericAmount = Number.parseFloat(nextAmount)
    const safeAmount = Number.isFinite(numericAmount) ? Math.max(0, numericAmount) : 0

    setDetectedRows((prev) =>
      prev.map((row) =>
        row.id === rowId
          ? {
              ...row,
              quantityAmount: safeAmount,
              quantity: `${safeAmount}${row.quantityUnit || '개'}`,
              review: true,
            }
          : row,
      ),
    )
    setEditingRows((prev) => ({ ...prev, [rowId]: true }))
    setActiveStep(2)
  }

  const stepQuantityAmount = (rowId, direction) => {
    const targetRow = detectedRows.find((row) => row.id === rowId)
    const currentAmount = Number.parseFloat(targetRow?.quantityAmount)
    const nextAmount = Math.max(0, (Number.isFinite(currentAmount) ? currentAmount : 0) + direction)

    updateQuantityAmount(rowId, nextAmount)
  }

  const updateQuantityUnit = (rowId, unit) => {
    if (!quantityUnitOptions.includes(unit)) {
      return
    }

    setDetectedRows((prev) =>
      prev.map((row) =>
        row.id === rowId
          ? {
              ...row,
              quantityUnit: unit,
              quantity: `${row.quantityAmount ?? 1}${unit}`,
              review: true,
            }
          : row,
      ),
    )
    setEditingRows((prev) => ({ ...prev, [rowId]: true }))
    setActiveStep(2)
  }

  const updateRowField = (rowId, field, value) => {
    setDetectedRows((prev) =>
      prev.map((row) =>
        row.id === rowId ? { ...row, [field]: field === 'price' ? formatPriceInput(value) : value, review: true } : row,
      ),
    )
    setEditingRows((prev) => ({ ...prev, [rowId]: true }))
    setActiveStep(2)
  }

  const setRowEditing = (rowId, isEditing) => {
    setEditingRows((prev) => ({ ...prev, [rowId]: isEditing }))

    if (isEditing) {
      setDetectedRows((prev) => prev.map((row) => (row.id === rowId ? { ...row, review: true } : row)))
      setActiveStep(2)
    } else {
      confirmRow(rowId)
    }
  }

  const confirmRow = (rowId) => {
    setDetectedRows((prev) => prev.map((row) => (row.id === rowId ? { ...row, review: false } : row)))
    setEditingRows((prev) => ({ ...prev, [rowId]: false }))
    setActiveStep(2)
  }

  const toggleAllRowsConfirmation = () => {
    const nextReviewState = isAllConfirmed

    setDetectedRows((prev) => prev.map((row) => ({ ...row, review: nextReviewState })))
    setEditingRows(
      detectedRows.reduce((nextEditingRows, row) => {
        nextEditingRows[row.id] = nextReviewState
        return nextEditingRows
      }, {}),
    )
    setActiveStep(2)
  }

  const resetAnalysis = () => {
    clearFlowTimers()
    const initialRows = createInitialReceiptRows()
    setDetectedRows(initialRows)
    setEditingRows(getInitialEditingRows(initialRows))
    setReceiptSource('샘플 영수증')
    setReceiptMeta(null)
    setHasUploaded(false)
    setIsProcessing(false)
    setAnalysisStep(0)
    setActiveStep(0)
  }

  const stockIngredients = async () => {
    if (!hasUploaded) {
      return
    }

    if (detectedRows.length === 0) {
      await showAlert('입고할 품목이 없어요. 품목을 직접 추가한 뒤 다시 시도해주세요.', {
        title: '품목이 필요해요',
      })
      return
    }

    if (reviewCount > 0) {
      await showAlert('확인 필요 항목이 남아 있어요. 모든 항목을 확인 완료로 바꾼 뒤 냉장고에 입고할 수 있어요.', {
        title: '확인이 필요해요',
      })
      return
    }

    if (!receiptMeta?.receiptId) {
      await showAlert('영수증 업로드 정보가 없어 입고할 수 없어요. 영수증을 다시 업로드해주세요.', {
        title: '영수증 정보가 필요해요',
      })
      return
    }

    const token = window.localStorage.getItem('bobbeori-token')
    if (token) {
      const calendarCostEnabled = window.localStorage.getItem('bobbeori-calendar-cost-enabled') !== 'false'

      try {
        const response = await fetch(`${apiUrl}/api/v1/receipts/confirm`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            receipt_id: receiptMeta.receiptId,
            store_name: receiptMeta.storeName,
            purchase_datetime: receiptMeta.purchaseDatetime,
            total_amount: totalAmount,
            calendar_cost_enabled: calendarCostEnabled,
            items: detectedRows.map((row) => ({
              raw_name: row.raw,
              normalized_name: row.name,
              quantity: toNumber(row.quantityAmount, 1),
              unit: row.quantityUnit || '개',
              item_amount: toNumber(row.price, 0),
              is_food: row.category !== '기타',
              storage_method: row.storage || '냉장',
              memo: null,
            })),
          }),
        })
        const data = await response.json().catch(() => ({}))

        if (!response.ok) {
          throw new Error(data.detail || '냉장고 입고 저장에 실패했어요.')
        }
      } catch (err) {
        console.error(err)
        await showAlert(err.message || '냉장고 입고 저장 중 문제가 발생했어요.', {
          title: '저장에 실패했어요',
        })
        return
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
                <strong>{receiptMeta?.storeName || 'BABBEORI MART'}</strong>
                <span>{receiptMeta?.purchaseDatetime || '2026.06.18 14:32'}</span>
                <dl>
                  {detectedRows.length > 0 ? (
                    detectedRows.map((row) => (
                      <div key={row.id}>
                        <dt>{row.raw}</dt>
                        <dd>{formatQuantity(row)}</dd>
                        <dd>{row.price}원</dd>
                      </div>
                    ))
                  ) : (
                    <div className="receipt-paper__empty">
                      <dt>인식된 품목 없음</dt>
                      <dd>-</dd>
                      <dd>-</dd>
                    </div>
                  )}
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
                  <button type="button" disabled={detectedRows.length === 0} onClick={toggleAllRowsConfirmation}>
                    {isAllConfirmed ? '전체 확인 취소' : '전체 확인'}
                  </button>
                  <span>전체 금액 {totalAmount.toLocaleString()}원</span>
                </div>
              </div>
              <p className="receipt-mapping__helper">
                OCR 결과는 먼저 모두 수정 가능하게 열려 있어요. 수량과 금액을 확인한 뒤 확정을 누르면 해당 행이 잠깁니다.
              </p>
              {receiptMeta ? (
                <div className="receipt-ocr-meta" aria-label="OCR 분석 참고 정보">
                  <span>{receiptMeta.storeName || '상호명 미확인'}</span>
                  <span>{receiptMeta.purchaseDatetime || '구매일시 미확인'}</span>
                  <span>
                    OCR 총액{' '}
                    {formatPriceInput(receiptMeta.totalAmount) ? `${formatPriceInput(receiptMeta.totalAmount)}원` : '미확인'}
                  </span>
                  {receiptMeta.confidenceNote ? <p>{receiptMeta.confidenceNote}</p> : null}
                </div>
              ) : null}

              <div className="receipt-mapping-table" role="table" aria-label="표준 재료명 매칭 결과">
                <div className="receipt-mapping-row receipt-mapping-row--head" role="row">
                  <span role="columnheader">재료</span>
                  <span role="columnheader">입고 정보</span>
                  <span role="columnheader">보관</span>
                  <span role="columnheader">확인</span>
                </div>
                {detectedRows.map((row) => {
                  const isEditing = Boolean(editingRows[row.id])

                  return (
                  <div className={`receipt-mapping-row ${isEditing ? 'is-editing' : ''}`} role="row" key={row.id}>
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
                            onChange={(event) => updateRowField(row.id, 'name', event.target.value)}
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
                            onClick={() => stepQuantityAmount(row.id, -1)}
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
                            onChange={(event) => updateQuantityAmount(row.id, event.target.value)}
                          />
                          <button
                            aria-label={`${row.name} 수량 증가`}
                            disabled={!isEditing}
                            type="button"
                            onClick={() => stepQuantityAmount(row.id, 1)}
                          >
                            +
                          </button>
                        </span>
                        <select
                          aria-label={`${row.name} 단위`}
                          className="receipt-inline-select"
                          disabled={!isEditing}
                          value={row.quantityUnit || '개'}
                          onChange={(event) => updateQuantityUnit(row.id, event.target.value)}
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
                          onChange={(event) => updateRowField(row.id, 'price', event.target.value)}
                        />
                      </label>
                    </span>
                    <span role="cell" className="receipt-storage-cell">
                      <select
                        aria-label={`${row.name} 보관 방법`}
                        className="receipt-storage-select"
                        disabled={!isEditing}
                        value={row.storage || '냉장'}
                        onChange={(event) => updateRowField(row.id, 'storage', event.target.value)}
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
                              confirmRow(row.id)
                              return
                            }

                            setRowEditing(row.id, true)
                          }}
                        />
                        <span aria-hidden="true" />
                        <b>{!row.review && !isEditing ? '확인 완료' : '확인 필요'}</b>
                      </label>
                    </span>
                  </div>
                  )
                })}
                {detectedRows.length === 0 ? (
                  <div className="receipt-empty-items" role="row">
                    <strong>인식된 품목이 없어요.</strong>
                    <p>카드전표처럼 품목 리스트가 없는 영수증일 수 있어요. 필요한 품목은 아래에서 직접 추가해주세요.</p>
                  </div>
                ) : null}
              </div>

              <button className="receipt-add-row" type="button" onClick={addRow}>
                + 행 추가
              </button>
              <div className="receipt-success">
                <span>총상품<em>{detectedRows.length}개</em></span>
                <span>총 금액<em>{totalAmount.toLocaleString()}원</em></span>
                <span>확인 완료<em>{mappedCount}개</em></span>
                <span>확인 필요<em>{reviewCount}개</em></span>
              </div>
              <button
                className="receipt-stock-button"
                type="button"
                disabled={isStockDisabled}
                onClick={stockIngredients}
              >
                <ImageSlot className="receipt-stock-button__icon" src={iconRefrigerator} />
                <span className="receipt-stock-button__title">냉장고에 입고하기</span>
                <small>
                  {reviewCount > 0
                    ? `확인 필요 항목 ${reviewCount}개를 먼저 완료해주세요.`
                    : detectedRows.length === 0
                      ? '등록할 품목을 먼저 추가해주세요.'
                    : `총 ${detectedRows.length}개 재료가 등록돼요!`}
                </small>
                <span className="receipt-stock-button__arrow" aria-hidden="true">→</span>
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
  const uploadInputRef = useRef(null)
  const cameraInputRef = useRef(null)
  const [isDragging, setIsDragging] = useState(false)

  const handleFileChange = (event, source) => {
    const file = event.target.files?.[0]
    event.target.value = ''

    if (file) {
      onStartUpload(file, source)
    }
  }

  const handleDrop = (event) => {
    event.preventDefault()
    setIsDragging(false)

    const file = event.dataTransfer.files?.[0]
    if (file) {
      onStartUpload(file, '업로드 이미지')
    }
  }

  return (
    <section className="receipt-panel receipt-upload" aria-labelledby="upload-title">
      <h2 id="upload-title">영수증 업로드</h2>
      <div
        className={`receipt-dropzone ${isDragging ? 'is-dragging' : ''}`}
        onDragEnter={(event) => {
          event.preventDefault()
          setIsDragging(true)
        }}
        onDragOver={(event) => {
          event.preventDefault()
          setIsDragging(true)
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={handleDrop}
      >
        <ImageSlot className="receipt-dropzone__icon" src={iconReceipt} />
        <p>영수증 사진(PNG, JPG, JPEG)을 드래그하거나 업로드/촬영 버튼을 눌러주세요.</p>
        <input
          ref={uploadInputRef}
          className="receipt-file-input"
          type="file"
          accept="image/png,image/jpeg,image/webp"
          onChange={(event) => handleFileChange(event, '업로드 이미지')}
        />
        <input
          ref={cameraInputRef}
          className="receipt-file-input"
          type="file"
          accept="image/*"
          capture="environment"
          onChange={(event) => handleFileChange(event, '카메라 촬영본')}
        />
        <div>
          <button className="receipt-primary-button" type="button" onClick={() => uploadInputRef.current?.click()}>
            이미지 업로드
          </button>
          <button className="receipt-soft-button" type="button" onClick={() => cameraInputRef.current?.click()}>
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
