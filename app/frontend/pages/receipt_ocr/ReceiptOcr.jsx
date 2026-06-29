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

const fallbackWeeklyAmounts = [
  { items: 8, amount: 32600 },
  { items: 12, amount: 48700 },
  { items: 9, amount: 35400 },
  { items: 15, amount: 61200 },
]

const purchaseFlowWeekCount = 4

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

function getItemDisplayName(item) {
  const rawName = typeof item === 'string' ? item : item?.normalized_name || item?.raw_name || item?.name || ''

  return String(rawName)
    .replace(/\s*\d+(?:\.\d+)?\s*(?:kg|g|개|단|팩|통|봉|송이)$/i, '')
    .trim()
}

function getFrequentIngredients(receipts) {
  const counts = receipts.reduce((acc, receipt) => {
    const receiptItems = receipt.items || []

    receiptItems.forEach((item) => {
      const ingredientName = getItemDisplayName(item)

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
    .slice(0, 7)
}

function parseReceiptDate(value) {
  if (!value) {
    return null
  }

  const normalized = String(value).trim().replace(/\./g, '-').replace(' ', 'T')
  const parsedDate = new Date(normalized)

  return Number.isNaN(parsedDate.getTime()) ? null : parsedDate
}

function getReceiptAmount(receipt) {
  if (receipt.total_amount != null) {
    return Number(receipt.total_amount) || 0
  }

  if (receipt.amount != null) {
    return Number(String(receipt.amount).replace(/[^\d.-]/g, '')) || 0
  }

  return (receipt.items || []).reduce((sum, item) => sum + (Number(item?.item_amount) || 0), 0)
}

function getReceiptItemCount(receipt) {
  if (receipt.item_count != null) {
    return Number(receipt.item_count) || 0
  }

  return Array.isArray(receipt.items) ? receipt.items.length : 0
}

function mapMockHistoryToReceipts(history) {
  return history.map((receipt) => ({
    purchase_datetime: receipt.date,
    total_amount: getReceiptAmount(receipt),
    item_count: getReceiptItemCount(receipt),
    items: (receipt.items || []).map((item) => ({ raw_name: item, normalized_name: getItemDisplayName(item) })),
  }))
}

// 달력 주(월~일)가 속한 날짜의 그 주 월요일을 반환합니다.
function getWeekMonday(date) {
  const local = new Date(date.getFullYear(), date.getMonth(), date.getDate())
  const mondayOffset = (local.getDay() + 6) % 7 // 월=0 ... 일=6
  local.setDate(local.getDate() - mondayOffset)
  return local
}

// ISO 방식: 달력 주(월~일)를 그 주의 목요일이 속한 달/주차로 계산합니다.
// 예) 6/29(월)이 속한 주는 목요일이 7/2라 "7월 1주차"가 됩니다.
function getWeekInfo(date) {
  const monday = getWeekMonday(date)
  const thursday = new Date(monday)
  thursday.setDate(monday.getDate() + 3)
  const weekOfMonth = Math.ceil(thursday.getDate() / 7)

  return {
    key: `${thursday.getFullYear()}-${thursday.getMonth()}-${weekOfMonth}`,
    label: `${thursday.getMonth() + 1}월 ${weekOfMonth}주차`,
    monday,
  }
}

// 접속일(anchorDate)이 속한 주차부터 과거로 weekCount개의 주 버킷을 만듭니다(오래된 주차가 앞).
function buildRecentWeekBuckets(anchorDate, weekCount) {
  const buckets = []
  let cursorMonday = getWeekMonday(anchorDate)

  for (let i = 0; i < weekCount; i += 1) {
    const info = getWeekInfo(cursorMonday)
    buckets.unshift({ key: info.key, label: info.label })
    cursorMonday = new Date(cursorMonday)
    cursorMonday.setDate(cursorMonday.getDate() - 7)
  }

  return buckets
}

function buildPurchaseFlowData(receipts, options = {}) {
  const weekCount = options.weekCount || purchaseFlowWeekCount
  const fallbackToMock = options.fallbackToMock ?? false
  const sourceReceipts = Array.isArray(receipts) ? receipts : []
  const buckets = buildRecentWeekBuckets(new Date(), weekCount)

  if (sourceReceipts.length === 0) {
    const weeklyData = buckets.map((bucket, index) => ({
      week: bucket.label,
      items: fallbackToMock ? fallbackWeeklyAmounts[index]?.items ?? 0 : 0,
      amount: fallbackToMock ? fallbackWeeklyAmounts[index]?.amount ?? 0 : 0,
    }))
    return {
      weeklyData,
      frequentIngredients: fallbackToMock ? getFrequentIngredients(mapMockHistoryToReceipts(receiptHistory)) : [],
    }
  }

  const datedReceipts = sourceReceipts.map((receipt) => ({
    ...receipt,
    parsedDate: parseReceiptDate(receipt.purchase_datetime || receipt.date),
  }))
  const indexByBucketKey = new Map(buckets.map((bucket, index) => [bucket.key, index]))
  const weeklyData = buckets.map((bucket) => ({ week: bucket.label, items: 0, amount: 0 }))

  datedReceipts.forEach((receipt) => {
    if (!receipt.parsedDate) {
      return
    }

    const weekIndex = indexByBucketKey.get(getWeekInfo(receipt.parsedDate).key)

    if (weekIndex === undefined) {
      return
    }

    weeklyData[weekIndex].amount += getReceiptAmount(receipt)
    weeklyData[weekIndex].items += getReceiptItemCount(receipt)
  })

  return {
    weeklyData,
    frequentIngredients: getFrequentIngredients(datedReceipts),
  }
}

const fallbackPurchaseFlowData = buildPurchaseFlowData(mapMockHistoryToReceipts(receiptHistory), {
  fallbackToMock: true,
})
const staticSpendSparkPoints = '8,32 32,24 56,30 80,16 108,26'
const staticSpendSparkArea = `8,40 ${staticSpendSparkPoints} 108,40`
const staticItemBars = [
  { x: 8, y: 22, height: 18 },
  { x: 30, y: 12, height: 28 },
  { x: 52, y: 24, height: 16 },
  { x: 74, y: 8, height: 32 },
  { x: 96, y: 18, height: 22 },
]

function ImageSlot({ src, alt = '', className = '' }) {
  return (
    <span className={`receipt-image-slot ${src ? 'is-filled' : ''} ${className}`}>
      {src ? <img src={src} alt={alt} /> : null}
    </span>
  )
}

function formatManwon(amount) {
  return `${(amount / 10000).toFixed(1)}만`
}

function PurchaseFlowChart({ isLoggedIn }) {
  const chartId = isLoggedIn ? 'receipt-chart-title' : 'receipt-guest-chart-title'
  const [purchaseFlowData, setPurchaseFlowData] = useState(fallbackPurchaseFlowData)
  const [purchaseFlowStatus, setPurchaseFlowStatus] = useState('idle')

  useEffect(() => {
    if (!isLoggedIn) {
      setPurchaseFlowData(fallbackPurchaseFlowData)
      setPurchaseFlowStatus('idle')
      return undefined
    }

    const token = window.localStorage.getItem('bobbeori-token')

    if (!token) {
      setPurchaseFlowData(fallbackPurchaseFlowData)
      setPurchaseFlowStatus('ready')
      return undefined
    }

    let active = true
    setPurchaseFlowStatus('loading')

    fetch(`${apiUrl}/api/v1/receipts/history?limit=100`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error('식재료 구매 흐름을 불러오지 못했어요.')
        }

        const data = await response.json().catch(() => ({}))
        return Array.isArray(data.receipts) ? data.receipts : []
      })
      .then((receipts) => {
        if (!active) {
          return
        }

        setPurchaseFlowData(buildPurchaseFlowData(receipts))
        setPurchaseFlowStatus('ready')
      })
      .catch(() => {
        if (!active) {
          return
        }

        setPurchaseFlowData(fallbackPurchaseFlowData)
        setPurchaseFlowStatus('error')
      })

    return () => {
      active = false
    }
  }, [isLoggedIn])

  if (!isLoggedIn) {
    return (
      <section className="receipt-panel receipt-chart" aria-labelledby={chartId}>
        <div>
          <h2 id={chartId}>식재료 구매 흐름</h2>
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
    )
  }

  const weeklyPurchaseData = purchaseFlowData.weeklyData
  const frequentIngredientData = purchaseFlowData.frequentIngredients
  const weekCount = weeklyPurchaseData.length
  const maxAmount = Math.max(...weeklyPurchaseData.map((data) => data.amount), 1)
  const maxItems = Math.max(...weeklyPurchaseData.map((data) => data.items), 1)
  const totalAmount = weeklyPurchaseData.reduce((sum, data) => sum + data.amount, 0)
  const totalItems = weeklyPurchaseData.reduce((sum, data) => sum + data.items, 0)

  const baseline = 96
  const points = weeklyPurchaseData.map((data, index) => {
    const x = 30 + index * ((320 - 60) / (weekCount - 1))
    const barHeight = data.amount > 0 ? Math.max((data.amount / maxAmount) * 56, 5) : 0
    const barY = baseline - barHeight
    // 0개인 주는 바닥선(92)에 붙고, 값이 클수록 위로 올라갑니다.
    const dotY = 92 - (data.items / maxItems) * 48

    return { ...data, x, barHeight, barY, dotY }
  })
  const linePoints = points.map((point) => `${point.x},${point.dotY}`).join(' ')

  return (
    <section
      className="receipt-panel receipt-chart is-logged-in"
      aria-busy={purchaseFlowStatus === 'loading'}
      aria-labelledby={chartId}
    >
      <div className="receipt-chart__head">
        <h2 id={chartId}>식재료 구매 흐름</h2>
        <p>이번 주를 기준으로 최근 {weekCount}주간 주차별 구매 금액과 품목 수를 보여줘요.</p>
      </div>

      <div className="receipt-dashboard">
        <article className="receipt-dash-card receipt-dash-trend" aria-label="주차별 구매 금액과 품목 수 그래프">
          <header className="receipt-dash-card__head">
            <h3>구매 트렌드</h3>
            <span className="receipt-dash-pill">최근 {weekCount}주</span>
          </header>
          <div className="receipt-week-chart__plot">
            <svg viewBox="0 0 320 124" focusable="false">
              <defs>
                <linearGradient id="receipt-week-bar-gradient" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="0%" stopColor="#ffbe75" />
                  <stop offset="100%" stopColor="#ffe9a8" />
                </linearGradient>
              </defs>
              <path className="receipt-week-chart__grid" d="M24 34 H296 M24 65 H296 M24 96 H296" />
              {points.map((point) => (
                <g key={`${point.week}-bar`}>
                  <rect
                    className="receipt-week-chart__bar"
                    height={point.barHeight}
                    rx="5"
                    width="26"
                    x={point.x - 13}
                    y={point.barY}
                  />
                  {point.amount > 0 ? (
                    <text className="receipt-week-chart__amount" x={point.x} y={baseline - 8}>
                      {formatManwon(point.amount)}
                    </text>
                  ) : null}
                </g>
              ))}
              <polyline className="receipt-week-chart__line" points={linePoints} />
              {points.map((point) => (
                <g key={point.week}>
                  <circle
                    className={`receipt-week-chart__dot ${point.items === 0 ? 'is-empty' : ''}`}
                    cx={point.x}
                    cy={point.dotY}
                    r="3.4"
                  />
                  {point.items > 0 ? (
                    <text className="receipt-week-chart__value" x={point.x} y={point.dotY - 8}>
                      {point.items}개
                    </text>
                  ) : (
                    <text
                      className="receipt-week-chart__value receipt-week-chart__value--empty"
                      x={point.x}
                      y={point.dotY - 8}
                    >
                      0개
                    </text>
                  )}
                  <text className="receipt-week-chart__label" x={point.x} y="118">
                    {point.week}
                  </text>
                </g>
              ))}
            </svg>
          </div>
          <div className="receipt-week-chart__legend">
            <span className="is-amount">구매 금액</span>
            <span className="is-items">품목 수</span>
          </div>
        </article>

        <div className="receipt-dash-mini">
          <article className="receipt-dash-card receipt-dash-stat">
            <div className="receipt-dash-stat__head">
              <h4>총 지출</h4>
              <span>최근 {weekCount}주</span>
            </div>
            <strong>{totalAmount.toLocaleString()}원</strong>
            <svg className="receipt-dash-spark" viewBox="0 0 116 44" focusable="false" aria-hidden="true">
              <polygon className="receipt-dash-spark__area" points={staticSpendSparkArea} />
              <polyline className="receipt-dash-spark__line" points={staticSpendSparkPoints} />
            </svg>
          </article>
          <article className="receipt-dash-card receipt-dash-stat">
            <div className="receipt-dash-stat__head">
              <h4>총 품목</h4>
              <span>최근 {weekCount}주</span>
            </div>
            <strong>{totalItems}개</strong>
            <svg className="receipt-dash-minibars" viewBox="0 0 116 44" focusable="false" aria-hidden="true">
              {staticItemBars.map((bar) => (
                <rect key={`${bar.x}-${bar.height}`} x={bar.x} y={bar.y} width="14" height={bar.height} rx="3" />
              ))}
            </svg>
          </article>
        </div>

        <article className="receipt-dash-card receipt-dash-frequent" aria-labelledby="receipt-frequent-title">
          <header className="receipt-dash-card__head">
            <h3 id="receipt-frequent-title">자주 산 재료</h3>
            <span>최근 {weekCount}주</span>
          </header>
          {frequentIngredientData.length > 0 ? (
            <ul>
              {frequentIngredientData.map((ingredient, index) => (
                <li key={ingredient.name}>
                  <i className="receipt-dash-frequent__dot" data-rank={index} aria-hidden="true" />
                  <b>{ingredient.name}</b>
                  <strong>{ingredient.count}회</strong>
                </li>
              ))}
            </ul>
          ) : (
            <p className="receipt-dash-empty">최근 구매 데이터가 없어요.</p>
          )}
        </article>
      </div>
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

function formatPriceInput(value) {
  const numericValue = String(value ?? '').replace(/[^\d]/g, '')

  return numericValue ? Number(numericValue).toLocaleString() : ''
}

function toDateTimeLocalValue(value) {
  if (!value) {
    return ''
  }

  const normalized = String(value).trim().replace(' ', 'T')
  const match = normalized.match(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/)

  // 초는 화면에 표시하지 않고 분까지만 잘라서 보여줍니다(OCR이 읽은 초 정보는 원본에 유지).
  return match ? match[0] : ''
}

function fromDateTimeLocalValue(value) {
  return value ? String(value).replace('T', ' ') : ''
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
      category: '식재료',
      storage: '냉장',
      review: true,
    }
  })
}

function ReceiptOcr() {
  const navigate = useNavigate()
  const { dialogNode, showAlert, showConfirm } = useAppDialog()
  const flowTimersRef = useRef([])
  const previewImageUrlRef = useRef(null)
  const [isLoggedIn, setIsLoggedIn] = useState(getAuthState)
  const [hasUploaded, setHasUploaded] = useState(false)
  const [activeStep, setActiveStep] = useState(0)
  const [detectedRows, setDetectedRows] = useState(createInitialReceiptRows)
  const [editingRows, setEditingRows] = useState(() => getInitialEditingRows(createInitialReceiptRows()))
  const [receiptSource, setReceiptSource] = useState('샘플 영수증')
  const [receiptMeta, setReceiptMeta] = useState(null)
  const [isProcessing, setIsProcessing] = useState(false)
  const [analysisStep, setAnalysisStep] = useState(0)
  const [previewImageUrl, setPreviewImageUrl] = useState(null)
  const [isAddRowOpen, setIsAddRowOpen] = useState(false)

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

  const setUploadedPreview = (file) => {
    if (previewImageUrlRef.current) {
      URL.revokeObjectURL(previewImageUrlRef.current)
    }

    const url = file ? URL.createObjectURL(file) : null
    previewImageUrlRef.current = url
    setPreviewImageUrl(url)
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
    setUploadedPreview(file)
    setReceiptSource(file.name || source)
    setReceiptMeta(null)
    setDetectedRows([])
    setEditingRows({})
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

      if (response.status === 401) {
        window.localStorage.removeItem('bobbeori-token')
        window.dispatchEvent(new Event('bobbeori-auth-change'))
        setHasUploaded(false)
        setActiveStep(0)
        clearFlowTimers()
        setIsProcessing(false)
        requestLogin()
        return
      }

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

  const addRow = () => {
    setIsAddRowOpen(true)
  }

  const submitAddRow = (form) => {
    const name = form.name.trim()

    if (!name) {
      return
    }

    const newRowId = `manual-${Date.now()}-${name}`

    setDetectedRows((prev) => [
      ...prev,
      {
        id: newRowId,
        raw: name,
        name,
        quantity: `${form.quantityAmount}${form.quantityUnit}`,
        quantityAmount: form.quantityAmount,
        quantityUnit: form.quantityUnit,
        price: formatPriceInput(form.price),
        category: '기타',
        storage: form.storage || '냉장',
        review: true,
      },
    ])
    setEditingRows((prev) => ({ ...prev, [newRowId]: true }))
    setHasUploaded(true)
    setActiveStep(2)
    setIsAddRowOpen(false)
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

  const updateReceiptMetaField = (field, value) => {
    setReceiptMeta((prev) => {
      if (!prev) {
        return prev
      }

      return {
        ...prev,
        [field]: field === 'totalAmount' ? formatPriceInput(value) : value,
      }
    })
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
    setUploadedPreview(null)
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

    const confirmed = await showConfirm(`총 ${detectedRows.length}개 재료를 냉장고에 입고하시겠습니까?`, {
      title: '냉장고 입고',
      confirmText: '입고하기',
      cancelText: '취소',
    })

    if (!confirmed) {
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
              storage_method: row.storage || '냉장',
              item_memo: null,
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
      if (previewImageUrlRef.current) {
        URL.revokeObjectURL(previewImageUrlRef.current)
      }
      window.removeEventListener('bobbeori-auth-change', syncAuthState)
      window.removeEventListener('storage', syncAuthState)
    }
  }, [])

  return (
    <section className="receipt-page" aria-labelledby="receipt-title">
      <div className="receipt-hero">
        <div className="receipt-hero__copy">
          <h1 id="receipt-title">
            구매한 식재료를
            <br />
            한번에 정리하세요
          </h1>
          <p>영수증을 올리면 재료명, 수량, 금액을 확인해 냉장고 관리까지 이어져요.</p>
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
              tabIndex={-1}
              aria-current={index === activeStep ? 'step' : undefined}
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
              <ReceiptImageViewer src={previewImageUrl} isScanning={isProcessing} />
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
              맞게 인식됐는지 확인해주세요! 수정 후 확인 완료를 누르면 해당 항목이 저장돼요.
              </p>
              {receiptMeta ? (
                <div className="receipt-ocr-meta" aria-label="OCR 분석 참고 정보">
                  <label className="receipt-ocr-meta__field">
                    <small>매장명</small>
                    <input
                      className="receipt-inline-input"
                      type="text"
                      value={receiptMeta.storeName || ''}
                      placeholder="상호명 미확인"
                      onChange={(event) => updateReceiptMetaField('storeName', event.target.value)}
                    />
                  </label>
                  <label className="receipt-ocr-meta__field">
                    <small>날짜</small>
                    <input
                      className="receipt-inline-input receipt-inline-input--datetime"
                      type="datetime-local"
                      value={toDateTimeLocalValue(receiptMeta.purchaseDatetime)}
                      onChange={(event) =>
                        updateReceiptMetaField('purchaseDatetime', fromDateTimeLocalValue(event.target.value))
                      }
                    />
                  </label>
                  <label className="receipt-ocr-meta__field">
                    <small>총액(원)</small>
                    <input
                      className="receipt-inline-input receipt-inline-input--price"
                      inputMode="numeric"
                      pattern="[0-9,]*"
                      type="text"
                      value={formatPriceInput(receiptMeta.totalAmount)}
                      placeholder="미확인"
                      onChange={(event) => updateReceiptMetaField('totalAmount', event.target.value)}
                    />
                  </label>
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
                  isProcessing ? (
                    <div className="receipt-empty-items receipt-empty-items--loading" role="row">
                      <span className="receipt-loading-spinner" aria-hidden="true" />
                      <strong>영수증을 분석하고 있어요.</strong>
                      <p>업로드한 영수증에서 품목과 금액을 읽는 중이에요. 잠시만 기다려주세요.</p>
                      <div className="receipt-loading-bar" role="progressbar" aria-label="영수증 분석 진행 중">
                        <span />
                      </div>
                    </div>
                  ) : (
                    <div className="receipt-empty-items" role="row">
                      <strong>인식된 품목이 없어요.</strong>
                      <p>카드전표처럼 품목 리스트가 없는 영수증일 수 있어요. 필요한 품목은 아래에서 직접 추가해주세요.</p>
                    </div>
                  )
                ) : null}
              </div>

              {!isProcessing ? (
                <>
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
                </>
              ) : null}
            </section>
          </div>
        </>
      )}
      {isAddRowOpen ? <AddRowModal onClose={() => setIsAddRowOpen(false)} onSubmit={submitAddRow} /> : null}
      {dialogNode}
    </section>
  )
}

function AddRowModal({ onClose, onSubmit }) {
  const [name, setName] = useState('')
  const [quantityAmount, setQuantityAmount] = useState('1')
  const [quantityUnit, setQuantityUnit] = useState('개')
  const [price, setPrice] = useState('')
  const [storage, setStorage] = useState('냉장')

  const trimmedName = name.trim()
  const canSubmit = trimmedName.length > 0

  const handleSubmit = () => {
    if (!canSubmit) {
      return
    }

    const parsedAmount = Number.parseFloat(quantityAmount)

    onSubmit({
      name: trimmedName,
      quantityAmount: Number.isFinite(parsedAmount) && parsedAmount > 0 ? parsedAmount : 1,
      quantityUnit,
      price,
      storage,
    })
  }

  return (
    <div className="app-dialog-overlay" role="presentation" onMouseDown={onClose}>
      <section
        className="app-dialog-card receipt-add-card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="receipt-add-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="app-dialog-card__header">
          <span>품목 추가</span>
          <button type="button" aria-label="닫기" onClick={onClose}>
            x
          </button>
        </div>
        <h2 id="receipt-add-title">행 추가</h2>
        <p>추가할 품목 정보를 입력해주세요.</p>

        <div className="receipt-add-form">
          <label className="receipt-add-form__full">
            <small>재료명</small>
            <input
              type="text"
              value={name}
              placeholder="예: 대파"
              onChange={(event) => setName(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  handleSubmit()
                }
              }}
            />
          </label>
          <label>
            <small>수량</small>
            <input
              type="number"
              min="0"
              step={quantityUnit === 'kg' ? '0.1' : '1'}
              value={quantityAmount}
              onChange={(event) => setQuantityAmount(event.target.value)}
            />
          </label>
          <label>
            <small>단위</small>
            <select value={quantityUnit} onChange={(event) => setQuantityUnit(event.target.value)}>
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
              type="text"
              inputMode="numeric"
              pattern="[0-9,]*"
              value={price}
              placeholder="0"
              onChange={(event) => setPrice(formatPriceInput(event.target.value))}
            />
          </label>
          <label>
            <small>보관 방법</small>
            <select value={storage} onChange={(event) => setStorage(event.target.value)}>
              {storageOptions.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="app-dialog-card__actions">
          <button className="app-dialog-card__secondary" type="button" onClick={onClose}>
            취소
          </button>
          <button className="app-dialog-card__primary" type="button" disabled={!canSubmit} onClick={handleSubmit}>
            추가
          </button>
        </div>
      </section>
    </div>
  )
}

function ReceiptImageViewer({ src, isScanning = false }) {
  const minZoom = 1
  const maxZoom = 4
  const zoomStep = 0.4
  const [zoom, setZoom] = useState(1)
  const [offset, setOffset] = useState({ x: 0, y: 0 })
  const [isDragging, setIsDragging] = useState(false)
  const dragStateRef = useRef(null)

  const clampZoom = (value) => Math.min(maxZoom, Math.max(minZoom, Math.round(value * 100) / 100))

  const resetView = () => {
    setZoom(1)
    setOffset({ x: 0, y: 0 })
  }

  const zoomIn = () => setZoom((current) => clampZoom(current + zoomStep))
  const zoomOut = () =>
    setZoom((current) => {
      const next = clampZoom(current - zoomStep)
      if (next <= minZoom) {
        setOffset({ x: 0, y: 0 })
      }
      return next
    })

  const isZoomed = zoom > minZoom

  const handlePointerDown = (event) => {
    if (!isZoomed) {
      return
    }

    event.preventDefault()
    dragStateRef.current = {
      startX: event.clientX,
      startY: event.clientY,
      originX: offset.x,
      originY: offset.y,
    }
    setIsDragging(true)
    event.currentTarget.setPointerCapture?.(event.pointerId)
  }

  const handlePointerMove = (event) => {
    if (!dragStateRef.current) {
      return
    }

    setOffset({
      x: dragStateRef.current.originX + (event.clientX - dragStateRef.current.startX),
      y: dragStateRef.current.originY + (event.clientY - dragStateRef.current.startY),
    })
  }

  const handlePointerUp = (event) => {
    if (!dragStateRef.current) {
      return
    }

    dragStateRef.current = null
    setIsDragging(false)
    event.currentTarget.releasePointerCapture?.(event.pointerId)
  }

  const stageClassName = [
    'receipt-image-viewer__stage',
    isZoomed ? 'is-zoomable' : '',
    isDragging ? 'is-dragging' : '',
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <div className="receipt-image-viewer">
      <div
        className={stageClassName}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerLeave={handlePointerUp}
        onDoubleClick={resetView}
      >
        {src ? (
          <>
            <img
              alt="업로드한 영수증 이미지"
              draggable="false"
              src={src}
              style={{ transform: `translate(${offset.x}px, ${offset.y}px) scale(${zoom})` }}
            />
            {isScanning && (
              <div className="receipt-scan-overlay" aria-hidden="true">
                <div className="receipt-scan-overlay__laser" />
              </div>
            )}
          </>
        ) : (
          <div className="receipt-paper-image__empty">
            <p>업로드한 영수증 이미지를 불러올 수 없어요.</p>
          </div>
        )}
      </div>
      <div className="receipt-image-viewer__controls">
        <span>영수증 확대</span>
        <button aria-label="축소" disabled={!src || zoom <= minZoom} type="button" onClick={zoomOut}>
          −
        </button>
        <strong>{Math.round(zoom * 100)}%</strong>
        <button aria-label="확대" disabled={!src || zoom >= maxZoom} type="button" onClick={zoomIn}>
          +
        </button>
        <button className="receipt-image-viewer__reset" disabled={!src || (!isZoomed && offset.x === 0 && offset.y === 0)} type="button" onClick={resetView}>
          원래대로
        </button>
      </div>
    </div>
  )
}

function detectCameraCapture() {
  if (typeof window === 'undefined' || typeof navigator === 'undefined') {
    return false
  }

  const isCoarsePointer = window.matchMedia?.('(pointer: coarse)')?.matches
  const isMobileViewport = window.matchMedia?.('(max-width: 760px)')?.matches
  const isMobileUa = /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent || '')

  return Boolean(isCoarsePointer || isMobileUa || isMobileViewport)
}

function UploadPanel({ onStartUpload }) {
  const uploadInputRef = useRef(null)
  const cameraInputRef = useRef(null)
  const [isDragging, setIsDragging] = useState(false)
  const [canUseCamera, setCanUseCamera] = useState(detectCameraCapture)

  useEffect(() => {
    const update = () => setCanUseCamera(detectCameraCapture())
    const mediaQueries = [
      window.matchMedia('(pointer: coarse)'),
      window.matchMedia('(max-width: 760px)'),
    ]

    mediaQueries.forEach((mediaQuery) => mediaQuery.addEventListener?.('change', update))
    window.addEventListener('resize', update)
    update()

    return () => {
      mediaQueries.forEach((mediaQuery) => mediaQuery.removeEventListener?.('change', update))
      window.removeEventListener('resize', update)
    }
  }, [])

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
        <p>
          {canUseCamera
            ? '영수증 사진(PNG, JPG, JPEG)을 드래그하거나 업로드/촬영 버튼을 눌러주세요.'
            : '영수증 사진(PNG, JPG, JPEG)을 드래그하거나 업로드 버튼을 눌러주세요.'}
        </p>
        <input
          ref={uploadInputRef}
          className="receipt-file-input"
          type="file"
          accept="image/png,image/jpeg,image/webp"
          onChange={(event) => handleFileChange(event, '업로드 이미지')}
        />
        {canUseCamera ? (
          <input
            ref={cameraInputRef}
            className="receipt-file-input"
            type="file"
            accept="image/*"
            capture="environment"
            onChange={(event) => handleFileChange(event, '카메라 촬영본')}
          />
        ) : null}
        <div className={canUseCamera ? undefined : 'is-single'}>
          <button className="receipt-primary-button" type="button" onClick={() => uploadInputRef.current?.click()}>
            이미지 업로드
          </button>
          {canUseCamera ? (
            <button className="receipt-soft-button" type="button" onClick={() => cameraInputRef.current?.click()}>
              카메라 촬영
            </button>
          ) : null}
        </div>
      </div>
      <p className="receipt-tip">영수증 전체가 보이도록 밝은 곳에서 정면으로 촬영해주세요.</p>
    </section>
  )
}

function formatHistoryItemLabel(item) {
  const name = item.normalized_name || item.raw_name || '품목'

  if (item.quantity == null) {
    return name
  }

  const amount = Number.isInteger(item.quantity) ? item.quantity : Number(item.quantity)
  return `${name} ${amount}${item.unit || ''}`.trim()
}

function mapHistoryEntry(entry) {
  return {
    id: entry.receipt_id,
    title: entry.store_name || '영수증',
    meta: `${entry.item_count}개 품목 등록`,
    amount: entry.total_amount != null ? `${entry.total_amount.toLocaleString()}원` : '금액 미확인',
    status: '완료',
    date: entry.purchase_datetime || '구매일시 미확인',
    store: entry.store_name || '상호명 미확인',
    items: (entry.items || []).map(formatHistoryItemLabel),
    note: `총 ${entry.item_count}개 품목이 냉장고에 등록된 영수증이에요.`,
  }
}

function RecentHistory() {
  const { dialogNode, showAlert, showConfirm } = useAppDialog()
  const [history, setHistory] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [showAllHistory, setShowAllHistory] = useState(false)
  const [status, setStatus] = useState('loading')
  const [deletingId, setDeletingId] = useState(null)

  useEffect(() => {
    const token = window.localStorage.getItem('bobbeori-token')

    if (!token) {
      setHistory([])
      setStatus('ready')
      return undefined
    }

    let active = true
    setStatus('loading')

    fetch(`${apiUrl}/api/v1/receipts/history`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error('최근 영수증 내역을 불러오지 못했어요.')
        }

        const data = await response.json().catch(() => ({}))
        return Array.isArray(data.receipts) ? data.receipts.map(mapHistoryEntry) : []
      })
      .then((entries) => {
        if (!active) {
          return
        }

        setHistory(entries)
        setSelectedId(entries[0]?.id ?? null)
        setStatus('ready')
      })
      .catch(() => {
        if (active) {
          setStatus('error')
        }
      })

    return () => {
      active = false
    }
  }, [])

  const visibleHistory = showAllHistory ? history : history.slice(0, 3)
  const selectedHistory = history.find((item) => item.id === selectedId) || null

  const handleDelete = async (item) => {
    const confirmed = await showConfirm(
      `'${item.title}' 영수증 내역을 삭제할까요? 이미 냉장고에 등록된 재료는 그대로 유지돼요.`,
      { title: '영수증 내역 삭제', confirmText: '삭제', cancelText: '취소' },
    )

    if (!confirmed) {
      return
    }

    const token = window.localStorage.getItem('bobbeori-token')
    if (!token) {
      return
    }

    setDeletingId(item.id)

    try {
      const response = await fetch(`${apiUrl}/api/v1/receipts/${item.id}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      })

      if (!response.ok) {
        const data = await response.json().catch(() => ({}))
        throw new Error(data.detail || '영수증 내역 삭제에 실패했어요.')
      }

      const remaining = history.filter((entry) => entry.id !== item.id)
      setHistory(remaining)

      if (selectedId === item.id) {
        setSelectedId(remaining[0]?.id ?? null)
      }
    } catch (error) {
      await showAlert(error.message || '영수증 내역 삭제 중 문제가 발생했어요.', { title: '삭제 실패' })
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <section className="receipt-panel receipt-history" aria-labelledby="receipt-history-title">
      <div className="receipt-panel__title">
        <h2 id="receipt-history-title">최근 영수증 내역</h2>
        {history.length > 3 ? (
          <button type="button" onClick={() => setShowAllHistory((prev) => !prev)}>
            {showAllHistory ? '접기' : '내역보기'}
          </button>
        ) : null}
      </div>
      {status === 'loading' ? (
        <p className="receipt-history__placeholder">최근 영수증 내역을 불러오는 중이에요.</p>
      ) : status === 'error' ? (
        <p className="receipt-history__placeholder">내역을 불러오지 못했어요. 잠시 후 다시 시도해주세요.</p>
      ) : history.length === 0 ? (
        <p className="receipt-history__placeholder">
          아직 등록한 영수증이 없어요. 영수증을 업로드해 첫 내역을 만들어보세요.
        </p>
      ) : (
        <>
          <div className="receipt-history-list">
            {visibleHistory.map((item) => (
              <button
                className={selectedId === item.id ? 'is-active' : ''}
                key={item.id}
                type="button"
                onClick={() => setSelectedId(item.id)}
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
                {selectedHistory.items.length > 0 ? (
                  selectedHistory.items.map((item, index) => (
                    <li key={`${selectedHistory.id}-${index}`}>{item}</li>
                  ))
                ) : (
                  <li>등록된 품목이 없어요.</li>
                )}
              </ul>
              <p>{selectedHistory.note}</p>
              <div className="receipt-history-detail__actions">
                <button
                  className="receipt-history-delete"
                  type="button"
                  disabled={deletingId === selectedHistory.id}
                  onClick={() => handleDelete(selectedHistory)}
                >
                  {deletingId === selectedHistory.id ? '삭제 중...' : '내역 삭제'}
                </button>
              </div>
            </article>
          ) : null}
        </>
      )}
      {dialogNode}
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
