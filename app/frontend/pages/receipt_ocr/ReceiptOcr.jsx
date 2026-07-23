import React, { useEffect, useRef, useState } from 'react'
import Cropper from 'react-easy-crop'
import { useNavigate } from 'react-router-dom'
import './ReceiptOcr.css'

import iconReceipt from '../../assets/extracted/icons/icon_receipt.png'
import iconRefrigerator from '../../assets/extracted/icons/icon_refrigerator.png'
import imageHello from '../../assets/extracted/images/image_hello.png'
import imageReceipt from '../../assets/extracted/images/image_receipt registration.png'
import { useAppDialog } from '../../components/AppDialog.jsx'
import { adjustCropPixelsForOffset, resizeCropBoxFromPointer } from './cropGeometry.js'
import { getReceiptAgeInDays, isOldReceipt } from './receiptAgePolicy.js'
import { requiresReceiptItemReview } from './receiptReviewPolicy.js'
import { API_URL } from '../../utils/api.js'
import { trackEvent } from '../../utils/analytics.js'
import {
  receiptHistory,
  receiptRows as rows,
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
const maxUploadSizeMb = 10
const maxReceiptImages = 5
const maxTotalUploadSizeMb = 25
const purchaseFlowHistoryLimit = 100
const acceptedImageTypes = ['image/jpeg', 'image/png', 'image/webp']
const ocrManualCropSuggestionMinScore = 0.75
const ocrWeakReviewScore = 0.85
// Main stepper indices (must match the order of receiptSteps).
const STEP = { UPLOAD: 0, ANALYZE: 1, CONFIRM: 2, STOCK: 3 }
const receiptHistoryChangedEventName = 'bobbeori-receipt-history-change'

const receiptHistoryRequests = new Map()

function fetchReceiptHistory(token, limit = 10, forceRefresh = false) {
  const requestKey = `${token}:${limit}`
  const pendingRequest = receiptHistoryRequests.get(requestKey)
  if (pendingRequest && !forceRefresh) return pendingRequest

  const promise = fetch(`${API_URL}/api/v1/receipts/history?limit=${limit}`, {
    headers: { Authorization: `Bearer ${token}` },
  }).then(async (response) => {
    if (!response.ok) throw new Error('영수증 내역을 불러오지 못했어요.')
    const data = await response.json().catch(() => ({}))
    return Array.isArray(data.receipts) ? data.receipts : []
  })
  receiptHistoryRequests.set(requestKey, promise)

  const clearRequest = () => {
    if (receiptHistoryRequests.get(requestKey) === promise) receiptHistoryRequests.delete(requestKey)
  }
  promise.then(clearRequest, clearRequest)

  return promise
}

const defaultCropBox = { w: 0.78, h: 0.86, x: 0, y: 0 }
const minCropBoxScale = 0.32
const defaultCropZoom = 1
const minCropZoom = 1
const maxCropZoom = 3

function parseSseBlock(block) {
  const dataLines = block
    .split(/\r?\n/)
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice(5).trimStart())

  if (dataLines.length === 0) {
    return null
  }

  return JSON.parse(dataLines.join('\n'))
}

async function readReceiptUploadStream(response, onEvent) {
  const reader = response.body?.getReader()

  if (!reader) {
    throw new Error('실시간 분석 상태를 읽지 못했어요.')
  }

  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { value, done } = await reader.read()

    if (done) {
      break
    }

    buffer += decoder.decode(value, { stream: true })
    const blocks = buffer.split(/\r?\n\r?\n/)
    buffer = blocks.pop() || ''

    blocks.forEach((block) => {
      const event = parseSseBlock(block)

      if (event) {
        onEvent(event)
      }
    })
  }

  buffer += decoder.decode()

  if (buffer.trim()) {
    const event = parseSseBlock(buffer)

    if (event) {
      onEvent(event)
    }
  }
}

function loadImage(src) {
  return new Promise((resolve, reject) => {
    const image = new Image()
    image.onload = () => resolve(image)
    image.onerror = () => reject(new Error('이미지를 불러오지 못했어요.'))
    image.src = src
  })
}

function canvasToBlob(canvas, type = 'image/jpeg', quality = 0.92) {
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (blob) {
        resolve(blob)
        return
      }
      reject(new Error('크롭 이미지를 만들지 못했어요.'))
    }, type, quality)
  })
}

async function createCroppedReceiptFile(imageSrc, cropPixels, originalFileName) {
  const image = await loadImage(imageSrc)
  const crop = cropPixels || {
    x: 0,
    y: 0,
    width: image.naturalWidth || image.width,
    height: image.naturalHeight || image.height,
  }
  const canvas = document.createElement('canvas')
  const context = canvas.getContext('2d')

  if (!context) {
    throw new Error('브라우저에서 이미지 크롭을 처리하지 못했어요.')
  }

  canvas.width = Math.max(1, Math.round(crop.width))
  canvas.height = Math.max(1, Math.round(crop.height))

  context.drawImage(
    image,
    Math.max(0, Math.round(crop.x)),
    Math.max(0, Math.round(crop.y)),
    Math.max(1, Math.round(crop.width)),
    Math.max(1, Math.round(crop.height)),
    0,
    0,
    canvas.width,
    canvas.height,
  )

  const blob = await canvasToBlob(canvas)
  const baseName = String(originalFileName || 'receipt')
    .replace(/\.[^.]+$/, '')
    .replace(/[^\w.-]+/g, '_')
    .slice(0, 80)
  return new File([blob], `${baseName || 'receipt'}_cropped.jpg`, { type: 'image/jpeg' })
}

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
  const anchorDate = options.anchorDate || new Date()
  const buckets = buildRecentWeekBuckets(anchorDate, weekCount)

  if (sourceReceipts.length === 0) {
    const weeklyData = buckets.map((bucket, index) => ({
      week: bucket.label,
      items: fallbackToMock ? fallbackWeeklyAmounts[index]?.items ?? 0 : 0,
      amount: fallbackToMock ? fallbackWeeklyAmounts[index]?.amount ?? 0 : 0,
    }))
    return {
      weeklyData,
      frequentIngredients: fallbackToMock ? getFrequentIngredients(mapMockHistoryToReceipts(receiptHistory)) : [],
      totalAmount: weeklyData.reduce((sum, data) => sum + data.amount, 0),
      totalItems: weeklyData.reduce((sum, data) => sum + data.items, 0),
    }
  }

  const datedReceipts = sourceReceipts.map((receipt) => ({
    ...receipt,
    parsedDate: parseReceiptDate(receipt.purchase_datetime || receipt.date),
  }))
  const indexByBucketKey = new Map(buckets.map((bucket, index) => [bucket.key, index]))
  const weeklyData = buckets.map((bucket) => ({ week: bucket.label, items: 0, amount: 0 }))
  const endOfAnchorDate = new Date(
    anchorDate.getFullYear(),
    anchorDate.getMonth(),
    anchorDate.getDate(),
    23,
    59,
    59,
    999,
  )
  const recentReceipts = datedReceipts.filter((receipt) => {
    if (!receipt.parsedDate || receipt.parsedDate > endOfAnchorDate) {
      return false
    }

    return indexByBucketKey.has(getWeekInfo(receipt.parsedDate).key)
  })

  recentReceipts.forEach((receipt) => {
    const weekIndex = indexByBucketKey.get(getWeekInfo(receipt.parsedDate).key)

    weeklyData[weekIndex].amount += getReceiptAmount(receipt)
    weeklyData[weekIndex].items += getReceiptItemCount(receipt)
  })

  return {
    weeklyData,
    frequentIngredients: getFrequentIngredients(recentReceipts),
    totalAmount: recentReceipts.reduce((sum, receipt) => sum + getReceiptAmount(receipt), 0),
    totalItems: recentReceipts.reduce((sum, receipt) => sum + getReceiptItemCount(receipt), 0),
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

function PurchaseFlowChart() {
  const chartId = 'receipt-chart-title'
  const [purchaseFlowData, setPurchaseFlowData] = useState(fallbackPurchaseFlowData)
  const [purchaseFlowStatus, setPurchaseFlowStatus] = useState('idle')

  useEffect(() => {
    let active = true
    let requestId = 0

    const loadPurchaseFlow = (forceRefresh = false) => {
      const token = window.localStorage.getItem('bobbeori-token')
      const currentRequestId = requestId + 1
      requestId = currentRequestId

      if (!token) {
        setPurchaseFlowData(fallbackPurchaseFlowData)
        setPurchaseFlowStatus('ready')
        return
      }

      setPurchaseFlowStatus('loading')

      fetchReceiptHistory(token, purchaseFlowHistoryLimit, forceRefresh)
        .then((receipts) => {
          if (!active || currentRequestId !== requestId) {
            return
          }

          setPurchaseFlowData(buildPurchaseFlowData(receipts))
          setPurchaseFlowStatus('ready')
        })
        .catch(() => {
          if (!active || currentRequestId !== requestId) {
            return
          }

          setPurchaseFlowData(fallbackPurchaseFlowData)
          setPurchaseFlowStatus('error')
        })
    }

    const handleReceiptHistoryChanged = () => loadPurchaseFlow(true)

    loadPurchaseFlow()
    window.addEventListener(receiptHistoryChangedEventName, handleReceiptHistoryChanged)

    return () => {
      active = false
      window.removeEventListener(receiptHistoryChangedEventName, handleReceiptHistoryChanged)
    }
  }, [])

  const weeklyPurchaseData = purchaseFlowData.weeklyData
  const frequentIngredientData = purchaseFlowData.frequentIngredients
  const weekCount = weeklyPurchaseData.length
  const maxAmount = Math.max(...weeklyPurchaseData.map((data) => data.amount), 1)
  const maxItems = Math.max(...weeklyPurchaseData.map((data) => data.items), 1)
  const totalAmount = purchaseFlowData.totalAmount ?? weeklyPurchaseData.reduce((sum, data) => sum + data.amount, 0)
  const totalItems = purchaseFlowData.totalItems ?? weeklyPurchaseData.reduce((sum, data) => sum + data.items, 0)

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

  return Boolean(window.localStorage.getItem('bobbeori-token'))
}

function getInitialEditingRows(nextRows) {
  return nextRows.reduce((acc, row) => {
    acc[row.id] = row.review !== false
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

function getPriceDigits(value) {
  return String(value ?? '').replace(/[^\d]/g, '')
}

function formatPriceInput(value) {
  const numericValue = getPriceDigits(value)

  return numericValue ? Number(numericValue).toLocaleString() : ''
}

function beginPriceInputEdit(event, updateValue) {
  const input = event.currentTarget
  const currentValue = input.value
  const selectionStart = input.selectionStart ?? currentValue.length
  const selectionEnd = input.selectionEnd ?? selectionStart
  const nextValue = getPriceDigits(currentValue)

  updateValue(nextValue)

  if (nextValue === currentValue || typeof window === 'undefined') {
    return
  }

  const nextSelectionStart = getPriceDigits(currentValue.slice(0, selectionStart)).length
  const nextSelectionEnd = getPriceDigits(currentValue.slice(0, selectionEnd)).length

  window.requestAnimationFrame(() => {
    if (document.activeElement === input) {
      input.setSelectionRange(nextSelectionStart, nextSelectionEnd)
    }
  })
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

function isInteractiveRowTarget(target) {
  return Boolean(
    target?.closest?.(
      [
        'button',
        'input',
        'select',
        'textarea',
        'label',
        'a',
        '[role="button"]',
        '[role="option"]',
        '.receipt-row-dropdown',
        '.receipt-ingredient-suggestions',
      ].join(','),
    ),
  )
}

function getOcrReviewPolicy(qualityScore) {
  const score = Number(qualityScore)

  if (
    Number.isFinite(score) &&
    score >= ocrManualCropSuggestionMinScore &&
    score < ocrWeakReviewScore
  ) {
    return {
      tone: 'caution',
      message: '분석을 완료했어요. 일부 항목의 인식 정확도가 낮을 수 있어요. 영수증 영역을 직접 지정하면 더 정확해질 수 있습니다.',
      suggestManualCrop: true,
    }
  }

  return {
    tone: 'info',
    message: '분석을 완료했어요. 항목을 확인해주세요.',
    suggestManualCrop: false,
  }
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

    const review = requiresReceiptItemReview(item)

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
      review,
      normalizationMatchType: item.normalization_match_type || 'none',
    }
  })
}

function ReceiptOcr() {
  const navigate = useNavigate()
  const { dialogNode, showAlert, showConfirm } = useAppDialog()
  const flowTimersRef = useRef([])
  const uploadRunIdRef = useRef(0)
  const previewImageUrlRef = useRef(null)
  const previewImageUrlsRef = useRef([])
  const cropImageUrlRef = useRef(null)
  const retakeInputRef = useRef(null)
  const ingredientSuggestionRequestRef = useRef(0)
  const ingredientSuggestionTimerRef = useRef(null)
  const [isLoggedIn, setIsLoggedIn] = useState(getAuthState)
  const [hasUploaded, setHasUploaded] = useState(false)
  const [activeStep, setActiveStep] = useState(STEP.UPLOAD)
  const [detectedRows, setDetectedRows] = useState(createInitialReceiptRows)
  const [editingRows, setEditingRows] = useState(() => getInitialEditingRows(createInitialReceiptRows()))
  const [receiptMeta, setReceiptMeta] = useState(null)
  const [isProcessing, setIsProcessing] = useState(false)
  const [previewImageUrl, setPreviewImageUrl] = useState(null)
  const [previewImages, setPreviewImages] = useState([])
  const [previewImageIndex, setPreviewImageIndex] = useState(0)
  const [lastReceiptSourceFiles, setLastReceiptSourceFiles] = useState([])
  const [orderReviewEntries, setOrderReviewEntries] = useState([])
  const [orderReviewSource, setOrderReviewSource] = useState('')
  const [receiptImageEntries, setReceiptImageEntries] = useState([])
  const [cropImageIndex, setCropImageIndex] = useState(0)
  const [cropFile, setCropFile] = useState(null)
  const [cropImageUrl, setCropImageUrl] = useState(null)
  const [cropSource, setCropSource] = useState('')
  const [crop, setCrop] = useState({ x: 0, y: 0 })
  const [cropBox, setCropBox] = useState(defaultCropBox)
  const [cropZoom, setCropZoom] = useState(defaultCropZoom)
  const [croppedAreaPixels, setCroppedAreaPixels] = useState(null)
  const [isCreatingCrop, setIsCreatingCrop] = useState(false)
  const [isAddRowOpen, setIsAddRowOpen] = useState(false)
  const [selectedRowIds, setSelectedRowIds] = useState([])
  const [isStocking, setIsStocking] = useState(false)
  const [ingredientSuggestions, setIngredientSuggestions] = useState({
    rowId: null,
    items: [],
    isOpen: false,
    focusedIndex: -1,
    isLoading: false,
  })

  const mappedCount = detectedRows.filter((row) => !row.review && !editingRows[row.id]).length
  const reviewCount = detectedRows.length - mappedCount
  const areAllRowsConfirmed = detectedRows.length > 0 && reviewCount === 0
  const totalAmount = detectedRows.reduce((sum, row) => {
    const numericPrice = Number(row.price.replace(/[^\d]/g, ''))
    return sum + (Number.isFinite(numericPrice) ? numericPrice : 0)
  }, 0)
  const visibleStep = hasUploaded && detectedRows.length > 0 && reviewCount === 0 ? STEP.STOCK : activeStep
  const isStockDisabled = reviewCount > 0 || detectedRows.length === 0 || isStocking
  const isCropPending = Boolean(cropFile && cropImageUrl)

  const clearFlowTimers = () => {
    flowTimersRef.current.forEach((timerId) => window.clearTimeout(timerId))
    flowTimersRef.current = []
  }

  const clearUploadedPreviewUrls = () => {
    if (previewImageUrlRef.current) {
      URL.revokeObjectURL(previewImageUrlRef.current)
      previewImageUrlRef.current = null
    }

    previewImageUrlsRef.current.forEach((url) => URL.revokeObjectURL(url))
    previewImageUrlsRef.current = []
  }

  const setUploadedPreviews = (files) => {
    clearUploadedPreviewUrls()

    const previewFiles = Array.isArray(files) ? files.filter(Boolean) : [files].filter(Boolean)
    const entries = previewFiles.map((file, index) => {
      const url = URL.createObjectURL(file)
      previewImageUrlsRef.current.push(url)
      return {
        id: `${Date.now()}-${index}-${file.name}-${file.size}`,
        name: file.name || `영수증 사진 ${index + 1}`,
        url,
      }
    })

    setPreviewImages(entries)
    setPreviewImageIndex(0)
    setPreviewImageUrl(entries[0]?.url || null)
  }

  const setUploadedPreview = (file) => {
    setUploadedPreviews(file ? [file] : [])
  }

  const setUploadedPreviewBlob = (blob) => {
    clearUploadedPreviewUrls()

    const url = blob ? URL.createObjectURL(blob) : null
    previewImageUrlRef.current = url
    setPreviewImages(url ? [{ id: 'saved-preview', name: '저장된 영수증', url }] : [])
    setPreviewImageIndex(0)
    setPreviewImageUrl(url)
  }

  const selectPreviewImage = (index) => {
    if (index < 0 || index >= previewImages.length) {
      return
    }

    setPreviewImageIndex(index)
    setPreviewImageUrl(previewImages[index].url)
  }

  const movePreviewImage = (direction) => {
    const nextIndex = previewImageIndex + direction
    selectPreviewImage(nextIndex)
  }

  const setCropPreview = (file) => {
    if (cropImageUrlRef.current) {
      URL.revokeObjectURL(cropImageUrlRef.current)
    }

    const url = file ? URL.createObjectURL(file) : null
    cropImageUrlRef.current = url
    setCropImageUrl(url)
  }

  const resetCropFrame = () => {
    setCrop({ x: 0, y: 0 })
    setCropBox(defaultCropBox)
    setCropZoom(defaultCropZoom)
    setCroppedAreaPixels(null)
    setIsCreatingCrop(false)
  }

  const clearCropSelection = () => {
    setCropPreview(null)
    setCropFile(null)
    setCropSource('')
    setReceiptImageEntries([])
    setCropImageIndex(0)
    resetCropFrame()
  }

  const validateReceiptImageFile = async (file) => {
    if (!file) {
      return false
    }

    if (!acceptedImageTypes.includes(file.type)) {
      await showAlert('PNG, JPG, WEBP 파일만 업로드할 수 있어요.', {
        title: '지원하지 않는 파일이에요',
      })
      return false
    }

    if (file.size > maxUploadSizeMb * 1024 * 1024) {
      await showAlert(`영수증 이미지는 ${maxUploadSizeMb}MB 이하만 업로드할 수 있어요.`, {
        title: '파일이 너무 커요',
      })
      return false
    }

    return true
  }

  const validateReceiptImageFiles = async (files) => {
    if (!files.length) {
      return false
    }

    if (files.length > maxReceiptImages) {
      await showAlert(`영수증 사진은 최대 ${maxReceiptImages}장까지 올릴 수 있어요.`, {
        title: '사진 수를 줄여주세요',
      })
      return false
    }

    const totalBytes = files.reduce((sum, file) => sum + file.size, 0)
    if (totalBytes > maxTotalUploadSizeMb * 1024 * 1024) {
      await showAlert(`전체 영수증 사진 용량은 ${maxTotalUploadSizeMb}MB 이하로 올려주세요.`, {
        title: '전체 파일 용량이 너무 커요',
      })
      return false
    }

    for (const file of files) {
      if (!(await validateReceiptImageFile(file))) {
        return false
      }
    }
    return true
  }

  const createReceiptImageEntries = (files) =>
    files.map((file, index) => ({
      id: `${Date.now()}-${index}-${file.name}-${file.size}`,
      sourceFile: file,
      croppedFile: null,
    }))

  const showCropImage = (entries, index) => {
    const entry = entries[index]
    if (!entry) {
      return
    }

    setCropImageIndex(index)
    setCropFile(entry.sourceFile)
    setCropPreview(entry.sourceFile)
    resetCropFrame()
  }

  const beginCropFlow = (files, source) => {
    const entries = createReceiptImageEntries(files)
    setReceiptImageEntries(entries)
    setCropSource(source || 'receipt images')
    showCropImage(entries, 0)
  }

  const beginOrderReview = (files, source) => {
    setOrderReviewEntries(createReceiptImageEntries(files))
    setOrderReviewSource(source || '업로드 이미지')
  }

  const clearOrderReview = () => {
    setOrderReviewEntries([])
    setOrderReviewSource('')
  }

  const loadSavedReceiptPreview = async (receiptId, token) => {
    if (!receiptId || !token) {
      return
    }

    const response = await fetch(`${API_URL}/api/v1/receipts/${receiptId}/image`, {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    })

    if (!response.ok) {
      return
    }

    const blob = await response.blob()
    setUploadedPreviewBlob(blob)
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

  const startUpload = async (selectedFiles, source) => {
    if (!isLoggedIn) {
      requestLogin()
      return
    }

    const token = window.localStorage.getItem('bobbeori-token')
    if (!token) {
      requestLogin()
      return
    }

    const files = Array.isArray(selectedFiles) ? selectedFiles : [selectedFiles].filter(Boolean)
    if (!(await validateReceiptImageFiles(files))) {
      return
    }

    uploadRunIdRef.current += 1
    clearFlowTimers()
    setUploadedPreview(null)
    setLastReceiptSourceFiles(files)
    setReceiptMeta(null)
    setDetectedRows([])
    setEditingRows({})
    setHasUploaded(false)
    setIsProcessing(false)
    setActiveStep(STEP.UPLOAD)
    setIsAddRowOpen(false)
    setSelectedRowIds([])

    if (files.length > 1) {
      beginOrderReview(files, source)
      return
    }

    await uploadReceiptImages(files, source || '업로드 이미지')
  }

  const uploadReceiptImages = async (selectedFiles, source, options = {}) => {
    if (!isLoggedIn) {
      requestLogin()
      return
    }

    const token = window.localStorage.getItem('bobbeori-token')
    if (!token) {
      requestLogin()
      return
    }

    const files = Array.isArray(selectedFiles) ? selectedFiles : [selectedFiles].filter(Boolean)
    if (!(await validateReceiptImageFiles(files))) {
      return
    }

    const uploadRunId = uploadRunIdRef.current + 1
    uploadRunIdRef.current = uploadRunId
    const cropMode = options.cropMode || 'auto'
    const manualCropSourceFiles = options.manualCropSourceFiles || files

    clearFlowTimers()
    clearCropSelection()
    clearOrderReview()
    setLastReceiptSourceFiles(manualCropSourceFiles)
    setUploadedPreviews(files)
    setReceiptMeta(null)
    setDetectedRows([])
    setEditingRows({})
    setHasUploaded(true)
    setIsProcessing(true)
    setActiveStep(STEP.ANALYZE)

    const formData = new FormData()
    files.forEach((file) => formData.append('files', file))
    formData.append('crop_mode', cropMode)

    try {
      const response = await fetch(`${API_URL}/api/v1/receipts/upload/stream`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
        },
        body: formData,
      })
      if (uploadRunIdRef.current !== uploadRunId) {
        return
      }

      if (response.status === 401) {
        window.localStorage.removeItem('bobbeori-token')
        window.dispatchEvent(new Event('bobbeori-auth-change'))
        setHasUploaded(false)
        setActiveStep(STEP.UPLOAD)
        clearFlowTimers()
        setIsProcessing(false)
        requestLogin()
        return
      }

      if (!response.ok) {
        const data = await response.json().catch(() => ({}))
        throw new Error(data.detail || '영수증 OCR 분석에 실패했어요.')
      }

      let data = null

      await readReceiptUploadStream(response, (event) => {
        if (uploadRunIdRef.current !== uploadRunId) {
          return
        }

        if (event.type === 'error') {
          throw new Error(event.message || '영수증 OCR 분석에 실패했어요.')
        }

        if (event.type === 'result') {
          data = event.data
        }
      })

      if (!data) {
        throw new Error('영수증 OCR 분석 결과를 받지 못했어요.')
      }

      if (uploadRunIdRef.current !== uploadRunId) {
        return
      }

      if (data.manual_crop_required) {
        setUploadedPreview(null)
        beginCropFlow(manualCropSourceFiles, source)
        setHasUploaded(false)
        setIsProcessing(false)
        setActiveStep(STEP.UPLOAD)
        setDetectedRows([])
        setEditingRows({})
        setReceiptMeta(null)
        await showAlert(data.manual_crop_message || '영수증 영역을 직접 맞춘 뒤 다시 분석해주세요.', {
          title: '영수증 영역 확인이 필요해요',
          confirmText: '확인',
        })
        return
      }

      if (data.needs_reupload) {
        setHasUploaded(false)
        setActiveStep(STEP.UPLOAD)
        setDetectedRows([])
        setEditingRows({})
        setReceiptMeta(null)
        await showAlert(
          data.reupload_message ||
            '영수증 이미지 인식 품질이 낮아요. 글자와 금액이 선명하게 보이도록 다시 촬영하거나 다른 이미지를 첨부해주세요.',
          {
            title: '영수증을 다시 첨부해주세요',
            confirmText: '확인',
          },
        )
        return
      }

      const nextRows = mapOcrItemsToRows(data.items)
      const reviewPolicy = getOcrReviewPolicy(data.quality_score)
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
        qualityScore: data.quality_score,
        qualityIssues: data.quality_issues || [],
        ocrStatus: data.ocr_status,
        reviewTone: reviewPolicy.tone,
        reviewMessage: reviewPolicy.message,
        suggestManualCrop: reviewPolicy.suggestManualCrop,
      })
      if (files.length === 1) {
        await loadSavedReceiptPreview(data.receipt_id, token)
      }
      trackEvent('receipt_ocr_complete', {
        item_count: nextRows.length,
        image_count: files.length,
        crop_mode: cropMode,
      })
      setActiveStep(STEP.CONFIRM)
    } catch (error) {
      if (uploadRunIdRef.current !== uploadRunId) {
        return
      }

      console.error(error)
      setHasUploaded(false)
      setActiveStep(STEP.UPLOAD)
      await showAlert(error.message || '영수증 분석 중 문제가 발생했어요.', {
        title: '분석에 실패했어요',
      })
    } finally {
      if (uploadRunIdRef.current === uploadRunId) {
        clearFlowTimers()
        setIsProcessing(false)
      }
    }
  }

  const applyCropAndUpload = async () => {
    if (!cropFile || !cropImageUrl || isCreatingCrop || isProcessing) {
      return
    }

    setIsCreatingCrop(true)

    try {
      const croppedFile = await createCroppedReceiptFile(cropImageUrl, croppedAreaPixels, cropFile.name)
      const nextEntries = receiptImageEntries.map((entry, index) =>
        index === cropImageIndex ? { ...entry, croppedFile } : entry,
      )
      const nextPendingIndex = nextEntries.findIndex((entry) => !entry.croppedFile)

      setReceiptImageEntries(nextEntries)
      if (nextPendingIndex >= 0) {
        setIsCreatingCrop(false)
        showCropImage(nextEntries, nextPendingIndex)
        return
      }

      await uploadReceiptImages(
        nextEntries.map((entry) => entry.croppedFile),
        cropSource || 'cropped receipt images',
        {
          cropMode: 'manual',
          manualCropSourceFiles: nextEntries.map((entry) => entry.sourceFile),
        },
      )
    } catch (error) {
      console.error(error)
      setIsCreatingCrop(false)
      await showAlert(error.message || '영수증 크롭 이미지를 만드는 중 문제가 발생했어요.', {
        title: '크롭에 실패했어요',
      })
    }
  }

  const selectCropImage = (index) => {
    if (isCreatingCrop || isProcessing || index === cropImageIndex) {
      return
    }
    showCropImage(receiptImageEntries, index)
  }

  const moveCropImage = (index, direction) => {
    if (isCreatingCrop || isProcessing) {
      return
    }

    const nextIndex = index + direction
    if (nextIndex < 0 || nextIndex >= receiptImageEntries.length) {
      return
    }

    const activeId = receiptImageEntries[cropImageIndex]?.id
    const reordered = [...receiptImageEntries]
    const [entry] = reordered.splice(index, 1)
    reordered.splice(nextIndex, 0, entry)
    setReceiptImageEntries(reordered)
    setCropImageIndex(Math.max(0, reordered.findIndex((item) => item.id === activeId)))
  }

  const reorderOrderReviewImage = (fromIndex, toIndex) => {
    if (
      fromIndex === toIndex ||
      fromIndex < 0 ||
      toIndex < 0 ||
      fromIndex >= orderReviewEntries.length ||
      toIndex >= orderReviewEntries.length
    ) {
      return
    }

    setOrderReviewEntries((prev) => {
      const reordered = [...prev]
      const [entry] = reordered.splice(fromIndex, 1)
      reordered.splice(toIndex, 0, entry)
      return reordered
    })
  }

  const moveOrderReviewImage = (index, direction) => {
    reorderOrderReviewImage(index, index + direction)
  }

  const confirmOrderAndUpload = async () => {
    if (isProcessing || orderReviewEntries.length === 0) {
      return
    }

    const files = orderReviewEntries.map((entry) => entry.sourceFile)
    const source = orderReviewSource || '업로드 이미지'
    clearOrderReview()
    await uploadReceiptImages(files, source)
  }

  const cancelOrderReview = () => {
    uploadRunIdRef.current += 1
    clearOrderReview()
    setLastReceiptSourceFiles([])
    setHasUploaded(false)
    setIsProcessing(false)
    setActiveStep(STEP.UPLOAD)
  }

  const cancelCropSelection = () => {
    uploadRunIdRef.current += 1
    clearCropSelection()
    setActiveStep(STEP.UPLOAD)
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
    setActiveStep(STEP.CONFIRM)
    setIsAddRowOpen(false)
  }

  const toggleRowSelect = (rowId) => {
    setSelectedRowIds((prev) => (prev.includes(rowId) ? prev.filter((value) => value !== rowId) : [...prev, rowId]))
  }

  const handleRowSelectClick = (event, rowId) => {
    if (isProcessing || isInteractiveRowTarget(event.target)) {
      return
    }

    toggleRowSelect(rowId)
  }

  const toggleAllRowsConfirmation = () => {
    const shouldConfirm = !areAllRowsConfirmed
    setDetectedRows((prev) => prev.map((row) => ({ ...row, review: !shouldConfirm })))
    setEditingRows(Object.fromEntries(detectedRows.map((row) => [row.id, !shouldConfirm])))
    setActiveStep(STEP.CONFIRM)
  }

  const deleteSelectedRows = async () => {
    if (selectedRowIds.length === 0) {
      return
    }

    const confirmed = await showConfirm(`총 ${selectedRowIds.length}개 삭제하시겠습니까?`, {
      title: '선택 삭제',
      confirmText: '삭제',
      cancelText: '취소',
    })

    if (!confirmed) {
      return
    }

    setDetectedRows((prev) => prev.filter((row) => !selectedRowIds.includes(row.id)))
    setEditingRows((prev) => {
      const next = { ...prev }
      selectedRowIds.forEach((rowId) => delete next[rowId])
      return next
    })
    setSelectedRowIds([])
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
    setActiveStep(STEP.CONFIRM)
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
    setActiveStep(STEP.CONFIRM)
  }

  const updateRowField = (rowId, field, value) => {
    setDetectedRows((prev) =>
      prev.map((row) =>
        row.id === rowId ? { ...row, [field]: field === 'price' ? getPriceDigits(value) : value, review: true } : row,
      ),
    )
    setEditingRows((prev) => ({ ...prev, [rowId]: true }))
    setActiveStep(STEP.CONFIRM)
  }

  const updateRowPriceDisplay = (rowId, value) => {
    setDetectedRows((prev) =>
      prev.map((row) => (row.id === rowId && row.price !== value ? { ...row, price: value } : row)),
    )
  }

  const beginRowPriceEdit = (event, rowId) => {
    beginPriceInputEdit(event, (value) => updateRowPriceDisplay(rowId, value))
  }

  const finishRowPriceEdit = (rowId) => {
    setDetectedRows((prev) =>
      prev.map((row) => {
        if (row.id !== rowId) {
          return row
        }

        const formattedPrice = formatPriceInput(row.price)
        return formattedPrice === row.price ? row : { ...row, price: formattedPrice }
      }),
    )
  }

  const closeIngredientSuggestions = () => {
    setIngredientSuggestions((prev) => ({
      ...prev,
      isOpen: false,
      focusedIndex: -1,
      isLoading: false,
    }))
  }

  const fetchIngredientSuggestions = async (rowId, keyword) => {
    const query = String(keyword || '').trim()
    const requestId = ingredientSuggestionRequestRef.current + 1
    ingredientSuggestionRequestRef.current = requestId

    if (!query) {
      setIngredientSuggestions({ rowId, items: [], isOpen: false, focusedIndex: -1, isLoading: false })
      return
    }

    setIngredientSuggestions((prev) => ({
      ...prev,
      rowId,
      isOpen: true,
      isLoading: true,
      focusedIndex: -1,
    }))

    try {
      const token = window.localStorage.getItem('bobbeori-token')
      const headers = token ? { Authorization: `Bearer ${token}` } : {}
      const params = new URLSearchParams({
        keyword: query,
        page: '1',
        page_size: '6',
      })
      const response = await fetch(`${API_URL}/api/v1/guide?${params.toString()}`, { headers })

      if (!response.ok) {
        throw new Error('ingredient guide search failed')
      }

      const data = await response.json()
      const items = Array.isArray(data?.items) ? data.items.filter((item) => item?.name) : []

      if (ingredientSuggestionRequestRef.current !== requestId) {
        return
      }

      setIngredientSuggestions({
        rowId,
        items,
        isOpen: items.length > 0,
        focusedIndex: items.length > 0 ? 0 : -1,
        isLoading: false,
      })
    } catch (error) {
      console.error(error)
      if (ingredientSuggestionRequestRef.current !== requestId) {
        return
      }
      setIngredientSuggestions({ rowId, items: [], isOpen: false, focusedIndex: -1, isLoading: false })
    }
  }

  const queueIngredientSuggestionSearch = (rowId, keyword) => {
    if (ingredientSuggestionTimerRef.current) {
      window.clearTimeout(ingredientSuggestionTimerRef.current)
    }

    ingredientSuggestionTimerRef.current = window.setTimeout(() => {
      fetchIngredientSuggestions(rowId, keyword)
    }, 180)
  }

  const updateRowNameField = (rowId, value) => {
    updateRowField(rowId, 'name', value)
    queueIngredientSuggestionSearch(rowId, value)
  }

  const selectIngredientSuggestion = (rowId, suggestion) => {
    if (!suggestion?.name) {
      return
    }

    updateRowField(rowId, 'name', suggestion.name)
    closeIngredientSuggestions()
  }

  const handleIngredientSuggestionKeyDown = (event, rowId) => {
    if (!ingredientSuggestions.isOpen || ingredientSuggestions.rowId !== rowId || ingredientSuggestions.items.length === 0) {
      return
    }

    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setIngredientSuggestions((prev) => ({
        ...prev,
        focusedIndex: Math.min(prev.focusedIndex + 1, prev.items.length - 1),
      }))
      return
    }

    if (event.key === 'ArrowUp') {
      event.preventDefault()
      setIngredientSuggestions((prev) => ({
        ...prev,
        focusedIndex: Math.max(prev.focusedIndex - 1, 0),
      }))
      return
    }

    if (event.key === 'Enter') {
      event.preventDefault()
      const selected = ingredientSuggestions.items[ingredientSuggestions.focusedIndex] || ingredientSuggestions.items[0]
      selectIngredientSuggestion(rowId, selected)
      return
    }

    if (event.key === 'Escape') {
      closeIngredientSuggestions()
    }
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
      setActiveStep(STEP.CONFIRM)
    } else {
      confirmRow(rowId)
    }
  }

  const confirmRow = (rowId) => {
    setDetectedRows((prev) => prev.map((row) => (row.id === rowId ? { ...row, review: false } : row)))
    setEditingRows((prev) => ({ ...prev, [rowId]: false }))
    setActiveStep(STEP.CONFIRM)
  }

  const resetAnalysis = () => {
    uploadRunIdRef.current += 1
    clearFlowTimers()
    setUploadedPreview(null)
    clearCropSelection()
    clearOrderReview()
    const initialRows = createInitialReceiptRows()
    setDetectedRows(initialRows)
    setEditingRows(getInitialEditingRows(initialRows))
    setReceiptMeta(null)
    setLastReceiptSourceFiles([])
    setHasUploaded(false)
    setIsProcessing(false)
    setActiveStep(STEP.UPLOAD)
    setIsAddRowOpen(false)
    setSelectedRowIds([])
  }

  const openRetakePicker = () => {
    if (isProcessing) {
      return
    }

    retakeInputRef.current?.click()
  }

  const openManualCropEditor = async () => {
    if (isProcessing) {
      return
    }

    if (!lastReceiptSourceFiles.length) {
      await showAlert('영수증 파일 정보가 없어 다시 첨부가 필요해요.', {
        title: '영역 조정을 시작할 수 없어요',
        confirmText: '확인',
      })
      openRetakePicker()
      return
    }

    uploadRunIdRef.current += 1
    clearFlowTimers()
    setUploadedPreview(null)
    clearOrderReview()
    beginCropFlow(lastReceiptSourceFiles, '수동 영역 조정')
    setHasUploaded(false)
    setIsProcessing(false)
    setActiveStep(STEP.UPLOAD)
  }

  const handleRetakeFileChange = (event) => {
    const files = Array.from(event.target.files || [])
    event.target.value = ''

    if (files.length) {
      startUpload(files, '재촬영 이미지')
    }
  }

  const stockIngredients = async () => {
    if (isStocking) {
      return
    }

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

    const receiptAgeInDays = getReceiptAgeInDays(receiptMeta.purchaseDatetime)
    const needsOldReceiptConfirmation = isOldReceipt(receiptMeta.purchaseDatetime)
    let oldReceiptConfirmed = false

    if (needsOldReceiptConfirmation) {
      oldReceiptConfirmed = await showConfirm(
        `구매일로부터 ${receiptAgeInDays}일이 지난 영수증입니다.\n일부 재료는 이미 소비기한이 지났을 수 있어요. 그래도 냉장고에 입고하시겠습니까?`,
        {
          title: '오래된 영수증이에요',
          confirmText: '그래도 입고하기',
          cancelText: '취소',
        },
      )

      if (!oldReceiptConfirmed) {
        return
      }
    }

    setIsStocking(true)

    const token = window.localStorage.getItem('bobbeori-token')
    if (!token) {
      setIsStocking(false)
      requestLogin()
      return
    }

    if (token) {
      const calendarCostEnabled = window.localStorage.getItem('bobbeori-calendar-cost-enabled') !== 'false'

      try {
        const response = await fetch(`${API_URL}/api/v1/receipts/confirm`, {
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
            old_receipt_confirmed: oldReceiptConfirmed,
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
        setIsStocking(false)
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
      clearUploadedPreviewUrls()
      if (cropImageUrlRef.current) {
        URL.revokeObjectURL(cropImageUrlRef.current)
      }
      if (ingredientSuggestionTimerRef.current) {
        window.clearTimeout(ingredientSuggestionTimerRef.current)
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

      <ol className="receipt-stepper" aria-label="영수증 등록 진행 단계">
        {steps.map((step, index) => (
          <li
            className={[
              index === visibleStep ? 'is-active' : '',
              hasUploaded && index < visibleStep ? 'is-done' : '',
            ]
              .filter(Boolean)
              .join(' ')}
            key={step}
            aria-current={index === visibleStep ? 'step' : undefined}
          >
            <b aria-hidden="true">{hasUploaded && index < visibleStep ? '✓' : index + 1}</b>
            <span>{step}</span>
          </li>
        ))}
      </ol>

      {!isLoggedIn ? (
        <div className="receipt-branch receipt-guest">
          <section className="receipt-panel receipt-login-notice" aria-labelledby="receipt-login-title">
            <ImageSlot className="receipt-login-notice__image" src={imageHello} />
            <h2 id="receipt-login-title">로그인이 필요해요</h2>
            <p>
            영수증 한 장으로 내 냉장고를 채워보세요.<br />
            로그인 후 바로 시작할 수 있어요.
            </p>
            <button className="receipt-primary-button" type="button" onClick={() => navigate('/login')}>
              로그인하고 영수증 등록하기
            </button>
          </section>
        </div>
      ) : isCropPending ? (
        <div className="receipt-branch receipt-crop-focus">
          <ReceiptCropPanel
            imageUrl={cropImageUrl}
            imageEntries={receiptImageEntries}
            currentIndex={cropImageIndex}
            crop={crop}
            cropBox={cropBox}
            zoom={cropZoom}
            isSubmitting={isCreatingCrop || isProcessing}
            onCropChange={setCrop}
            onCropComplete={(_, nextCroppedAreaPixels) => setCroppedAreaPixels(nextCroppedAreaPixels)}
            onCropBoxChange={setCropBox}
            onZoomChange={setCropZoom}
            onSelectImage={selectCropImage}
            onMoveImage={moveCropImage}
            onCancel={cancelCropSelection}
            onApply={applyCropAndUpload}
          />
        </div>
      ) : orderReviewEntries.length > 1 ? (
        <div className="receipt-branch receipt-order-focus">
          <ReceiptOrderReviewPanel
            imageEntries={orderReviewEntries}
            isSubmitting={isProcessing}
            onMoveImage={moveOrderReviewImage}
            onReorderImage={reorderOrderReviewImage}
            onCancel={cancelOrderReview}
            onConfirm={confirmOrderAndUpload}
          />
        </div>
      ) : !hasUploaded ? (
        <div className="receipt-branch receipt-before-grid">
          <UploadPanel canUpload={isLoggedIn} onRequireLogin={requestLogin} onStartUpload={startUpload} onNotify={showAlert} />
          <aside className="receipt-before-side" aria-label="영수증 입고 정보">
            <RecentHistory />
          </aside>
          <PurchaseFlowChart />
        </div>
      ) : (
        <>
          <div className="receipt-branch receipt-after-grid">
            <section className="receipt-panel receipt-preview-panel" aria-labelledby="preview-title">
              <div className="receipt-preview__title">
                <h2 id="preview-title">업로드한 영수증</h2>
                <div className="receipt-preview__actions">
                  <button type="button" disabled={isProcessing || !lastReceiptSourceFiles.length} onClick={openManualCropEditor}>
                    영역 조정
                  </button>
                  <button type="button" disabled={isProcessing} onClick={openRetakePicker}>
                    재업로드
                  </button>
                </div>
                <input
                  ref={retakeInputRef}
                  className="receipt-file-input"
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  multiple
                  onChange={handleRetakeFileChange}
                />
              </div>
              <ReceiptImageViewer
                src={previewImageUrl}
                images={previewImages}
                currentIndex={previewImageIndex}
                isScanning={isProcessing}
                onMove={movePreviewImage}
                onSelect={selectPreviewImage}
              />
            </section>

            <section className="receipt-panel receipt-mapping" aria-labelledby="mapping-title">
              <div className="receipt-mapping__title">
                <h2 id="mapping-title">
                  분석된 식재료 <span>({detectedRows.length})</span>
                </h2>
              </div>
              <div className="receipt-mapping__meta-row">
                {receiptMeta ? (
                  <div className="receipt-ocr-meta" aria-label="OCR 분석 참고 정보">
                    <label className="receipt-ocr-meta__field">
                      <small>매장명:</small>
                      <input
                        className="receipt-inline-input"
                        type="text"
                        value={receiptMeta.storeName || ''}
                        placeholder="상호명 미확인"
                        onChange={(event) => updateReceiptMetaField('storeName', event.target.value)}
                      />
                    </label>
                    <label className="receipt-ocr-meta__field">
                      <small>날짜:</small>
                      <input
                        className="receipt-inline-input receipt-inline-input--datetime"
                        type="datetime-local"
                        value={toDateTimeLocalValue(receiptMeta.purchaseDatetime)}
                        onChange={(event) =>
                          updateReceiptMetaField('purchaseDatetime', fromDateTimeLocalValue(event.target.value))
                        }
                      />
                    </label>
                  </div>
                ) : null}
                <button
                  className={`receipt-mapping__select-all ${areAllRowsConfirmed ? 'is-active' : ''}`}
                  type="button"
                  disabled={detectedRows.length === 0}
                  onClick={toggleAllRowsConfirmation}
                >
                  {areAllRowsConfirmed ? '전체 확인 취소' : '전체 확인'}
                </button>
              </div>

              {receiptMeta?.reviewMessage ? (
                <div className={`receipt-ocr-review receipt-ocr-review--${receiptMeta.reviewTone || 'info'}`}>
                  <p>{receiptMeta.reviewMessage}</p>
                  {receiptMeta.suggestManualCrop ? (
                    <button
                      type="button"
                      disabled={isProcessing || !lastReceiptSourceFiles.length}
                      onClick={openManualCropEditor}
                    >
                      영수증 영역 지정하기
                    </button>
                  ) : null}
                </div>
              ) : null}

              <div className="receipt-mapping-table" role="table" aria-label="분석된 식재료">
                {detectedRows.map((row) => {
                  const isEditing = Boolean(editingRows[row.id])
                  const isShowingIngredientSuggestions =
                    ingredientSuggestions.isOpen &&
                    ingredientSuggestions.rowId === row.id &&
                    ingredientSuggestions.items.length > 0

                  return (
                  <div
                    className={[
                      'receipt-mapping-row',
                      isEditing ? 'is-editing' : '',
                      isShowingIngredientSuggestions ? 'is-suggesting' : '',
                      'is-selectable',
                      selectedRowIds.includes(row.id) ? 'is-row-selected' : '',
                    ]
                      .filter(Boolean)
                      .join(' ')}
                    role="row"
                    aria-selected={selectedRowIds.includes(row.id)}
                    key={row.id}
                    onClick={(event) => handleRowSelectClick(event, row.id)}
                  >
                    <span className="receipt-mapping-name-cell" role="cell">
                      <b>
                        <small>원재료명: {row.raw}</small>
                        {isEditing ? (
                          <div className="receipt-ingredient-autocomplete">
                            <input
                              aria-label={`${row.raw} 표준 재료명`}
                              className="receipt-inline-input"
                              type="text"
                              autoComplete="off"
                              value={row.name}
                              onChange={(event) => updateRowNameField(row.id, event.target.value)}
                              onFocus={() => fetchIngredientSuggestions(row.id, row.name)}
                              onBlur={() => window.setTimeout(closeIngredientSuggestions, 120)}
                              onKeyDown={(event) => handleIngredientSuggestionKeyDown(event, row.id)}
                            />
                            {isShowingIngredientSuggestions ? (
                              <div className="receipt-ingredient-suggestions" role="listbox">
                                {ingredientSuggestions.items.map((suggestion, index) => (
                                    <button
                                      type="button"
                                      role="option"
                                      aria-selected={index === ingredientSuggestions.focusedIndex}
                                      className={index === ingredientSuggestions.focusedIndex ? 'is-focused' : ''}
                                      key={suggestion.code || `${suggestion.name}-${index}`}
                                      onMouseDown={(event) => {
                                        event.preventDefault()
                                        selectIngredientSuggestion(row.id, suggestion)
                                      }}
                                    >
                                      <strong>{suggestion.name}</strong>
                                    </button>
                                ))}
                              </div>
                            ) : null}
                          </div>
                        ) : (
                          row.name
                        )}
                      </b>
                    </span>
                    <span className="receipt-mapping-details" role="cell">
                      <div className="receipt-mapping-field receipt-quantity-field">
                        <small>수량</small>
                        {isEditing ? (
                          <>
                            <span className="receipt-quantity-control">
                              <button
                                aria-label={`${row.name} 수량 감소`}
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
                                onChange={(event) => updateQuantityAmount(row.id, event.target.value)}
                              />
                              <button
                                aria-label={`${row.name} 수량 증가`}
                                type="button"
                                onClick={() => stepQuantityAmount(row.id, 1)}
                              >
                                +
                              </button>
                            </span>
                            <ReceiptDropdown
                              ariaLabel={`${row.name} 단위`}
                              className="receipt-inline-select"
                              value={row.quantityUnit || '개'}
                              options={quantityUnitOptions}
                              onChange={(value) => updateQuantityUnit(row.id, value)}
                            />
                          </>
                        ) : (
                          <strong className="receipt-mapping-static-value">
                            {row.quantityAmount ?? 1}{row.quantityUnit || '개'}
                          </strong>
                        )}
                      </div>
                      <div className="receipt-mapping-field receipt-price-field">
                        <small>금액(원)</small>
                        {isEditing ? (
                          <input
                            aria-label={`${row.name} 금액`}
                            className="receipt-inline-input receipt-inline-input--price"
                            inputMode="numeric"
                            pattern="[0-9,]*"
                            type="text"
                            value={row.price}
                            onFocus={(event) => beginRowPriceEdit(event, row.id)}
                            onChange={(event) => updateRowField(row.id, 'price', event.target.value)}
                            onBlur={() => finishRowPriceEdit(row.id)}
                          />
                        ) : (
                          <strong className="receipt-mapping-static-value">
                            {row.price || '0'}원
                          </strong>
                        )}
                      </div>
                    </span>
                    <span role="cell" className="receipt-storage-cell">
                      <small>보관 위치</small>
                      {isEditing ? (
                        <ReceiptDropdown
                          ariaLabel={`${row.name} 보관 방법`}
                          className="receipt-storage-select"
                          value={row.storage || '냉장'}
                          options={storageOptions}
                          onChange={(value) => updateRowField(row.id, 'storage', value)}
                        />
                      ) : (
                        <strong className="receipt-mapping-static-value">{row.storage || '냉장'}</strong>
                      )}
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
                  <div className="receipt-row-tools">
                    <button className="receipt-add-row" type="button" onClick={addRow}>
                      항목 추가
                    </button>
                    <button
                      className="receipt-add-row receipt-row-tools__delete"
                      type="button"
                      disabled={selectedRowIds.length === 0}
                      onClick={deleteSelectedRows}
                    >
                      선택 삭제{selectedRowIds.length > 0 ? ` (${selectedRowIds.length})` : ''}
                    </button>
                  </div>
                  <div className="receipt-success">
                    <span>총상품<em>{detectedRows.length}개</em></span>
                    <span>총 금액<em>{totalAmount.toLocaleString()}원</em></span>
                    <span>확인 완료<em>{mappedCount}개</em></span>
                    <span>확인 필요<em>{reviewCount}개</em></span>
                  </div>
                  <button
                    className={`receipt-stock-button ${isStocking ? 'is-loading' : ''}`}
                    type="button"
                    disabled={isStockDisabled}
                    onClick={stockIngredients}
                  >
                    <ImageSlot className="receipt-stock-button__icon" src={iconRefrigerator} />
                    <span className="receipt-stock-button__title">
                      {isStocking ? '냉장고에 입고 중' : '냉장고에 입고하기'}
                    </span>
                    <small>
                      {isStocking
                        ? '재료를 저장하고 있어요. 잠시만 기다려주세요.'
                        : reviewCount > 0
                        ? `확인 필요 항목 ${reviewCount}개를 먼저 완료해주세요.`
                        : detectedRows.length === 0
                          ? '등록할 품목을 먼저 추가해주세요.'
                        : `총 ${detectedRows.length}개 재료가 등록돼요!`}
                    </small>
                    <span className="receipt-stock-button__arrow" aria-hidden="true">
                      {isStocking ? <i className="receipt-spinner" /> : '→'}
                    </span>
                  </button>
                </>
              ) : null}
            </section>
          </div>
        </>
      )}
      {isAddRowOpen ? <AddRowModal onClose={() => setIsAddRowOpen(false)} onSubmit={submitAddRow} /> : null}
      {dialogNode}
      {isStocking ? (
        <div className="receipt-stocking-overlay" role="status" aria-live="polite">
          <div className="receipt-stocking-card">
            <span className="receipt-stocking-card__spinner" aria-hidden="true" />
            <strong>냉장고에 입고 중이에요</strong>
            <p>재료와 구매 기록을 저장하고 있어요.</p>
          </div>
        </div>
      ) : null}
    </section>
  )
}

function ReceiptDropdown({ ariaLabel, className, value, options, onChange }) {
  const [isOpen, setIsOpen] = useState(false)

  return (
    <div
      className={`receipt-row-dropdown ${className}`}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) {
          setIsOpen(false)
        }
      }}
      onKeyDown={(event) => {
        if (event.key === 'Escape') {
          setIsOpen(false)
        }
      }}
    >
      <button
        className="receipt-row-dropdown__trigger"
        type="button"
        aria-label={ariaLabel}
        aria-haspopup="menu"
        aria-expanded={isOpen}
        onClick={() => setIsOpen((open) => !open)}
      >
        <span>{value}</span>
        <span className="receipt-row-dropdown__arrow" aria-hidden="true" />
      </button>
      {isOpen ? (
        <div className="receipt-row-dropdown__menu" role="menu">
          {options.map((option) => (
            <button
              className={value === option ? 'is-active' : ''}
              key={option}
              type="button"
              role="menuitemradio"
              aria-checked={value === option}
              onClick={() => {
                onChange(option)
                setIsOpen(false)
              }}
            >
              <span>{option}</span>
              {value === option ? <span aria-hidden="true">✓</span> : null}
            </button>
          ))}
        </div>
      ) : null}
    </div>
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
              onFocus={(event) => beginPriceInputEdit(event, setPrice)}
              onChange={(event) => setPrice(getPriceDigits(event.target.value))}
              onBlur={() => setPrice((value) => formatPriceInput(value))}
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

function ReceiptOrderReviewPanel({
  imageEntries,
  isSubmitting,
  onMoveImage,
  onReorderImage,
  onCancel,
  onConfirm,
}) {
  const [selectedEntryId, setSelectedEntryId] = useState(null)
  const [dragIndex, setDragIndex] = useState(null)
  const [dropIndex, setDropIndex] = useState(null)

  // Keyed by the set of images (not their order) so reordering keeps the same
  // object URLs instead of revoking and recreating them on every move.
  const entriesSignature = imageEntries
    .map((entry) => entry.id)
    .slice()
    .sort()
    .join('|')

  const [thumbnails, setThumbnails] = useState({})

  // Object URLs must be created inside the effect (not useMemo) so they are
  // recreated whenever the cleanup revokes them.
  useEffect(() => {
    const map = {}
    imageEntries.forEach((entry) => {
      if (entry.sourceFile) {
        map[entry.id] = URL.createObjectURL(entry.sourceFile)
      }
    })
    setThumbnails(map)

    return () => {
      Object.values(map).forEach((url) => URL.revokeObjectURL(url))
    }
  }, [entriesSignature])

  const selectedEntry =
    imageEntries.find((entry) => entry.id === selectedEntryId) || imageEntries[0] || null
  const selectedIndex = selectedEntry
    ? imageEntries.findIndex((entry) => entry.id === selectedEntry.id)
    : -1

  const endDrag = () => {
    setDragIndex(null)
    setDropIndex(null)
  }

  const handleDragStart = (index) => (event) => {
    if (isSubmitting) {
      event.preventDefault()
      return
    }

    setDragIndex(index)
    setDropIndex(index)
    event.dataTransfer.effectAllowed = 'move'
    // Firefox requires data to be set for the drag to start.
    event.dataTransfer.setData('text/plain', String(index))
  }

  const handleDragOver = (index) => (event) => {
    if (dragIndex === null) {
      return
    }

    event.preventDefault()
    event.dataTransfer.dropEffect = 'move'
    setDropIndex(index)
  }

  const handleDrop = (index) => (event) => {
    if (dragIndex === null) {
      return
    }

    event.preventDefault()
    onReorderImage?.(dragIndex, index)
    endDrag()
  }

  return (
    <section className="receipt-panel receipt-order-panel" aria-labelledby="receipt-order-title">
      <div className="receipt-preview__title">
        <div>
          <h2 id="receipt-order-title">
            사진 순서 확인
            <span className="receipt-order-count">({imageEntries.length}장)</span>
          </h2>
          <p>
            긴 영수증은 <b>위에서 아래 순서</b>로 이어 붙여 분석해요.
            <br />
            사진을 <b>드래그</b>해 순서를 바꾸고, 눌러서 내용을 확인하세요.
          </p>
        </div>
      </div>

      <ol className="receipt-crop-order receipt-order-list" aria-label="영수증 사진 분석 순서">
        {imageEntries.map((entry, index) => (
          <li
            key={entry.id}
            className={[
              entry.id === selectedEntry?.id ? 'is-active' : '',
              dragIndex === index ? 'is-dragging' : '',
              dragIndex !== null && dropIndex === index && dragIndex !== index ? 'is-drop-target' : '',
            ]
              .filter(Boolean)
              .join(' ')}
            draggable={!isSubmitting}
            onDragStart={handleDragStart(index)}
            onDragOver={handleDragOver(index)}
            onDrop={handleDrop(index)}
            onDragEnd={endDrag}
          >
            <span className="receipt-order-grip" aria-hidden="true" />
            <button
              type="button"
              className="receipt-crop-order__select"
              aria-pressed={entry.id === selectedEntry?.id}
              onClick={() => setSelectedEntryId(entry.id)}
            >
              <span>{index + 1}</span>
              <i className="receipt-order-thumb" aria-hidden="true">
                {thumbnails[entry.id] ? <img src={thumbnails[entry.id]} alt="" /> : null}
              </i>
              <b>{entry.sourceFile?.name || `영수증 사진 ${index + 1}`}</b>
              <em>{entry.sourceFile?.size ? `${(entry.sourceFile.size / 1024 / 1024).toFixed(1)}MB` : '선택됨'}</em>
            </button>
            <div className="receipt-crop-order__moves">
              <button
                type="button"
                disabled={isSubmitting || index === 0}
                aria-label={`${index + 1}번째 사진을 위로 이동`}
                onClick={() => onMoveImage(index, -1)}
              >
                ↑
              </button>
              <button
                type="button"
                disabled={isSubmitting || index === imageEntries.length - 1}
                aria-label={`${index + 1}번째 사진을 아래로 이동`}
                onClick={() => onMoveImage(index, 1)}
              >
                ↓
              </button>
            </div>
          </li>
        ))}
      </ol>

      {selectedEntry ? (
        <div className="receipt-order-preview">
          <div className="receipt-order-preview__bar">
            <strong>{selectedIndex + 1}번 사진 미리보기</strong>
            <em>{selectedEntry.sourceFile?.name || '영수증 사진'}</em>
          </div>
          <div className="receipt-order-preview__stage">
            {thumbnails[selectedEntry.id] ? (
              <img
                src={thumbnails[selectedEntry.id]}
                alt={`${selectedIndex + 1}번째 영수증 사진 미리보기`}
              />
            ) : null}
          </div>
        </div>
      ) : null}

      <div className="receipt-order-actions">
        <button className="receipt-soft-button" type="button" disabled={isSubmitting} onClick={onCancel}>
          다시 선택
        </button>
        <button className="receipt-primary-button" type="button" disabled={isSubmitting} onClick={onConfirm}>
          {isSubmitting ? '분석 준비 중...' : `${imageEntries.length}장 순서대로 분석`}
        </button>
      </div>
    </section>
  )
}

function ReceiptCropPanel({
  imageUrl,
  imageEntries,
  currentIndex,
  crop,
  cropBox,
  zoom,
  isSubmitting,
  onCropChange,
  onCropComplete,
  onCropBoxChange,
  onZoomChange,
  onSelectImage,
  onMoveImage,
  onCancel,
  onApply,
}) {
  const cropperRef = useRef(null)
  const [cropperSize, setCropperSize] = useState({ width: 0, height: 0 })
  const [cropAreaRect, setCropAreaRect] = useState(null)
  const [mediaSize, setMediaSize] = useState(null)
  const mediaAspect = mediaSize?.naturalWidth && mediaSize?.naturalHeight
    ? mediaSize.naturalWidth / mediaSize.naturalHeight
    : null

  useEffect(() => {
    setMediaSize(null)
  }, [imageUrl])

  useEffect(() => {
    const cropperElement = cropperRef.current

    if (!cropperElement) {
      return undefined
    }

    const updateCropperSize = () => {
      const rect = cropperElement.getBoundingClientRect()
      const nextSize = {
        width: Math.round(rect.width),
        height: Math.round(rect.height),
      }

      setCropperSize((currentSize) => {
        if (currentSize.width === nextSize.width && currentSize.height === nextSize.height) {
          return currentSize
        }

        return nextSize
      })
    }

    updateCropperSize()

    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', updateCropperSize)
      return () => window.removeEventListener('resize', updateCropperSize)
    }

    const resizeObserver = new ResizeObserver(updateCropperSize)
    resizeObserver.observe(cropperElement)

    return () => resizeObserver.disconnect()
  }, [])

  // Size the crop stage to the uploaded image's aspect ratio so the receipt
  // fills the area edge-to-edge instead of sitting inside gray letterbox bands.
  const cropperMaxHeight = 620
  const cropperMinHeight = 320
  const cropperHeight = mediaAspect && cropperSize.width > 0
    ? Math.round(Math.min(cropperMaxHeight, Math.max(cropperMinHeight, cropperSize.width / mediaAspect)))
    : null

  // The crop box can grow up to the full displayed image size on each axis,
  // so users can select the entire receipt — not just an inset region.
  // Derive the displayed (object-fit: contain) media size from the aspect
  // ratio and the current container size so it stays correct after resizes.
  const displayedMediaWidth = mediaAspect && cropperSize.width > 0 && cropperSize.height > 0
    ? Math.min(cropperSize.width, cropperSize.height * mediaAspect)
    : cropperSize.width
  const displayedMediaHeight = mediaAspect && cropperSize.width > 0 && cropperSize.height > 0
    ? displayedMediaWidth / mediaAspect
    : cropperSize.height
  const maxCropWidth = Math.max(120, Math.round(displayedMediaWidth))
  const maxCropHeight = Math.max(160, Math.round(displayedMediaHeight))
  const cropSize =
    cropperSize.width > 0 && cropperSize.height > 0
      ? {
          width: Math.round(maxCropWidth * cropBox.w),
          height: Math.round(maxCropHeight * cropBox.h),
        }
      : undefined
  const cropAreaOffsetX = (cropBox.x || 0) * maxCropWidth
  const cropAreaOffsetY = (cropBox.y || 0) * maxCropHeight
  const hasPendingImageAfterCurrent = imageEntries.some(
    (entry, index) => index !== currentIndex && !entry.croppedFile,
  )
  const applyLabel = hasPendingImageAfterCurrent
    ? '이 영역 저장하고 다음'
    : `${imageEntries.length}장 분석 시작`

  const reportCrop = (area, pixels) => {
    onCropComplete(
      area,
      adjustCropPixelsForOffset({
        pixels,
        cropBox,
        cropSize,
        displayedMediaSize: { width: maxCropWidth, height: maxCropHeight },
        naturalMediaSize: mediaSize,
      }),
    )
  }

  // react-easy-crop clamps the crop area to the visible media (letterboxing),
  // so read the actual rendered crop rectangle and sync the resize-handle overlay to it.
  useEffect(() => {
    const cropperElement = cropperRef.current
    if (!cropperElement) {
      return undefined
    }

    let frameId = null

    const syncCropAreaRect = () => {
      const cropAreaElement = cropperElement.querySelector('.reactEasyCrop_CropArea')
      if (!cropAreaElement) {
        return
      }

      const cropperRect = cropperElement.getBoundingClientRect()
      const areaRect = cropAreaElement.getBoundingClientRect()
      const nextRect = {
        left: areaRect.left - cropperRect.left,
        top: areaRect.top - cropperRect.top,
        width: areaRect.width,
        height: areaRect.height,
      }

      setCropAreaRect((current) => {
        if (
          current &&
          Math.abs(current.left - nextRect.left) < 0.5 &&
          Math.abs(current.top - nextRect.top) < 0.5 &&
          Math.abs(current.width - nextRect.width) < 0.5 &&
          Math.abs(current.height - nextRect.height) < 0.5
        ) {
          return current
        }
        return nextRect
      })
    }

    // Read after react-easy-crop has laid out the crop area for the new size.
    frameId = window.requestAnimationFrame(syncCropAreaRect)

    return () => {
      if (frameId) {
        window.cancelAnimationFrame(frameId)
      }
    }
  }, [cropSize?.width, cropSize?.height, cropBox.x, cropBox.y, cropperSize.width, cropperSize.height, imageUrl, zoom, crop])

  const startCropBoxResize = (handle) => (event) => {
    if (isSubmitting || !cropperRef.current || !cropAreaRect || event.button > 0) {
      return
    }

    event.preventDefault()
    event.stopPropagation()

    const cropperElement = cropperRef.current
    const cropperRect = cropperElement.getBoundingClientRect()
    const bounds = {
      left: cropperRect.left + (cropperRect.width - maxCropWidth) / 2,
      top: cropperRect.top + (cropperRect.height - maxCropHeight) / 2,
      right: cropperRect.left + (cropperRect.width + maxCropWidth) / 2,
      bottom: cropperRect.top + (cropperRect.height + maxCropHeight) / 2,
      width: maxCropWidth,
      height: maxCropHeight,
    }
    const initialRect = {
      left: cropperRect.left + cropAreaRect.left,
      top: cropperRect.top + cropAreaRect.top,
      right: cropperRect.left + cropAreaRect.left + cropAreaRect.width,
      bottom: cropperRect.top + cropAreaRect.top + cropAreaRect.height,
    }

    const updateCropBoxFromPointer = (clientX, clientY) => {
      onCropBoxChange(
        resizeCropBoxFromPointer({
          handle,
          pointerX: clientX,
          pointerY: clientY,
          initialRect,
          bounds,
          minScale: minCropBoxScale,
        }),
      )
    }

    updateCropBoxFromPointer(event.clientX, event.clientY)

    const handlePointerMove = (moveEvent) => {
      moveEvent.preventDefault()
      updateCropBoxFromPointer(moveEvent.clientX, moveEvent.clientY)
    }

    const stopResize = () => {
      window.removeEventListener('pointermove', handlePointerMove)
      window.removeEventListener('pointerup', stopResize)
      window.removeEventListener('pointercancel', stopResize)
      document.body.classList.remove('is-receipt-crop-resizing')
    }

    document.body.classList.add('is-receipt-crop-resizing')
    window.addEventListener('pointermove', handlePointerMove)
    window.addEventListener('pointerup', stopResize)
    window.addEventListener('pointercancel', stopResize)
  }

  return (
    <section className="receipt-panel receipt-crop-panel" aria-labelledby="receipt-crop-title">
      <div className="receipt-preview__title">
        <div>
          <h2 id="receipt-crop-title">
            영수증 영역 맞추기
            {imageEntries.length > 1 ? ` (${currentIndex + 1}/${imageEntries.length})` : ''}
          </h2>
          <p>사진은 영수증 상단부터 정렬하고, 각 영역이 잘리지 않도록 맞춰주세요.</p>
        </div>
      </div>
      {imageEntries.length > 1 ? (
        <ol className="receipt-crop-order" aria-label="영수증 사진 순서">
          {imageEntries.map((entry, index) => (
            <li className={index === currentIndex ? 'is-active' : ''} key={entry.id}>
              <button
                className="receipt-crop-order__select"
                type="button"
                disabled={isSubmitting}
                aria-current={index === currentIndex ? 'step' : undefined}
                onClick={() => onSelectImage(index)}
              >
                <span>{index + 1}</span>
                <b>{entry.sourceFile.name}</b>
                <em>{entry.croppedFile ? '영역 완료' : '조정 필요'}</em>
              </button>
              <div className="receipt-crop-order__moves">
                <button
                  type="button"
                  title="한 칸 위로"
                  aria-label={`${entry.sourceFile.name} 한 칸 위로`}
                  disabled={isSubmitting || index === 0}
                  onClick={() => onMoveImage(index, -1)}
                >
                  ↑
                </button>
                <button
                  type="button"
                  title="한 칸 아래로"
                  aria-label={`${entry.sourceFile.name} 한 칸 아래로`}
                  disabled={isSubmitting || index === imageEntries.length - 1}
                  onClick={() => onMoveImage(index, 1)}
                >
                  ↓
                </button>
              </div>
            </li>
          ))}
        </ol>
      ) : null}
      <div
        ref={cropperRef}
        className="receipt-cropper"
        aria-label="영수증 이미지 크롭"
        style={cropperHeight ? { height: `${cropperHeight}px` } : undefined}
      >
        {imageUrl ? (
          <Cropper
            image={imageUrl}
            crop={crop}
            zoom={zoom}
            minZoom={minCropZoom}
            maxZoom={maxCropZoom}
            cropSize={cropSize}
            objectFit="contain"
            showGrid={false}
            style={{
              cropAreaStyle: {
                marginLeft: `${cropAreaOffsetX}px`,
                marginTop: `${cropAreaOffsetY}px`,
              },
            }}
            zoomWithScroll
            onWheelRequest={(event) => event.ctrlKey}
            onCropChange={onCropChange}
            onCropAreaChange={reportCrop}
            onCropComplete={reportCrop}
            onZoomChange={onZoomChange}
            onMediaLoaded={(nextMediaSize) => {
              if (nextMediaSize?.naturalWidth && nextMediaSize?.naturalHeight) {
                setMediaSize(nextMediaSize)
              }
            }}
          />
        ) : (
          <div className="receipt-paper-image__empty">
            <p>크롭할 영수증 이미지를 불러올 수 없어요.</p>
          </div>
        )}
        {imageUrl ? (
          <button
            type="button"
            className="receipt-crop-refresh"
            disabled={isSubmitting}
            onClick={onCancel}
          >
            <i className="receipt-crop-refresh__icon" aria-hidden="true" />
            다시 선택
          </button>
        ) : null}
        {cropSize && cropAreaRect ? (
          <div
            className="receipt-crop-resize-box"
            aria-hidden="true"
            style={{
              left: `${cropAreaRect.left}px`,
              top: `${cropAreaRect.top}px`,
              width: `${cropAreaRect.width}px`,
              height: `${cropAreaRect.height}px`,
            }}
          >
            {['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w'].map((handle) => (
              <span
                key={handle}
                className={`receipt-crop-resize-box__handle is-${handle}`}
                onPointerDown={startCropBoxResize(handle)}
              />
            ))}
          </div>
        ) : null}
      </div>
      <div className="receipt-crop-controls">
        <label className="receipt-crop-zoom">
          <i className="receipt-crop-zoom__icon" aria-hidden="true" />
          <span>확대</span>
          <input
            type="range"
            min={minCropZoom}
            max={maxCropZoom}
            step="0.1"
            value={zoom}
            disabled={isSubmitting}
            onChange={(event) => onZoomChange(Number(event.target.value))}
          />
          <strong>{Math.round(zoom * 100)}%</strong>
        </label>
        <button
          className="receipt-primary-button receipt-crop-submit"
          type="button"
          disabled={!imageUrl || isSubmitting}
          onClick={onApply}
        >
          {isSubmitting ? '분석 준비 중...' : applyLabel}
        </button>
      </div>
    </section>
  )
}

function ReceiptImageViewer({ src, images = [], currentIndex = 0, isScanning = false, onMove, onSelect }) {
  const minZoom = 1
  const maxZoom = 3
  const zoomStep = 0.4
  const [zoom, setZoom] = useState(1)
  const [offset, setOffset] = useState({ x: 0, y: 0 })
  const [isDragging, setIsDragging] = useState(false)
  const dragStateRef = useRef(null)
  const hasMultipleImages = images.length > 1
  const currentImageName = images[currentIndex]?.name || '업로드한 영수증'

  useEffect(() => {
    setZoom(1)
    setOffset({ x: 0, y: 0 })
    dragStateRef.current = null
    setIsDragging(false)
  }, [src])

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
      {hasMultipleImages ? (
        <div className="receipt-image-viewer__pager" aria-label="영수증 사진 넘기기">
          <button
            type="button"
            aria-label="이전 영수증 사진"
            disabled={currentIndex <= 0}
            onClick={() => onMove?.(-1)}
          >
            ‹
          </button>
          <strong>{currentIndex + 1} / {images.length}</strong>
          <button
            type="button"
            aria-label="다음 영수증 사진"
            disabled={currentIndex >= images.length - 1}
            onClick={() => onMove?.(1)}
          >
            ›
          </button>
        </div>
      ) : null}
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
              alt={currentImageName}
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
      {hasMultipleImages ? (
        <div className="receipt-image-viewer__thumbs" aria-label="영수증 사진 선택">
          {images.map((image, index) => (
            <button
              type="button"
              className={index === currentIndex ? 'is-active' : ''}
              key={image.id || image.url}
              aria-label={`${index + 1}번째 사진 보기`}
              aria-current={index === currentIndex ? 'true' : undefined}
              onClick={() => onSelect?.(index)}
            >
              <img src={image.url} alt="" />
              <span>{index + 1}</span>
            </button>
          ))}
        </div>
      ) : null}
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

function UploadPanel({ canUpload = true, onRequireLogin, onStartUpload, onNotify }) {
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
    const files = Array.from(event.target.files || [])
    event.target.value = ''

    if (!canUpload) {
      onRequireLogin?.()
      return
    }

    if (files.length > maxReceiptImages) {
      onNotify?.(`영수증 사진은 최대 ${maxReceiptImages}장까지 올릴 수 있어요.`, { title: '사진 수를 줄여주세요' })
      return
    }

    if (files.length) {
      onStartUpload(files, source)
    }
  }

  const handleDrop = (event) => {
    event.preventDefault()
    setIsDragging(false)

    if (!canUpload) {
      onRequireLogin?.()
      return
    }

    const files = Array.from(event.dataTransfer.files || [])
    if (files.length > maxReceiptImages) {
      onNotify?.(`영수증 사진은 최대 ${maxReceiptImages}장까지 올릴 수 있어요.`, { title: '사진 수를 줄여주세요' })
      return
    }

    if (files.length) {
      onStartUpload(files, '업로드 이미지')
    }
  }

  const openUploadPicker = () => {
    if (!canUpload) {
      onRequireLogin?.()
      return
    }

    uploadInputRef.current?.click()
  }

  const openCameraPicker = () => {
    if (!canUpload) {
      onRequireLogin?.()
      return
    }

    cameraInputRef.current?.click()
  }

  return (
    <section className="receipt-panel receipt-upload" aria-labelledby="upload-title">
      <h2 id="upload-title">영수증 업로드</h2>
      <div
        className={[
          'receipt-dropzone',
          isDragging ? 'is-dragging' : '',
          !canUpload ? 'is-login-required' : '',
        ]
          .filter(Boolean)
          .join(' ')}
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
        <p>영수증 사진을 상단부터 최대 5장까지 선택하거나 여기로 드래그해주세요.</p>
        <input
          ref={uploadInputRef}
          className="receipt-file-input"
          type="file"
          accept="image/png,image/jpeg,image/webp"
          multiple
          onChange={(event) => handleFileChange(event, '업로드 이미지')}
        />
        {canUseCamera ? (
          <input
            ref={cameraInputRef}
            className="receipt-file-input"
            type="file"
            accept="image/png,image/jpeg,image/webp"
            capture="environment"
            onChange={(event) => handleFileChange(event, '카메라 촬영본')}
          />
        ) : null}
        <div className={canUseCamera ? undefined : 'is-single'}>
          <button className="receipt-primary-button" type="button" onClick={openUploadPicker}>
            이미지 업로드
          </button>
          {canUseCamera ? (
            <button className="receipt-soft-button" type="button" onClick={openCameraPicker}>
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
  const [selectionMode, setSelectionMode] = useState(false)
  const [selectedIds, setSelectedIds] = useState([])
  const [isBulkDeleting, setIsBulkDeleting] = useState(false)
  const [editingTitleId, setEditingTitleId] = useState(null)
  const [titleDraft, setTitleDraft] = useState('')
  const [isSavingTitle, setIsSavingTitle] = useState(false)

  useEffect(() => {
    const token = window.localStorage.getItem('bobbeori-token')

    if (!token) {
      setHistory([])
      setStatus('ready')
      return undefined
    }

    let active = true
    setStatus('loading')

    fetchReceiptHistory(token)
      .then((receipts) => receipts.map(mapHistoryEntry))
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

  const visibleHistory = showAllHistory || selectionMode ? history : history.slice(0, 3)
  const selectedHistory = history.find((item) => item.id === selectedId) || null

  const handleDelete = async (item) => {
    const confirmed = await showConfirm(
      `'${item.title}' 영수증 내역을 삭제할까요?\n삭제하면 구매 통계에서도 제외되며, 냉장고에 입고된 식재료는 유지됩니다.`,
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
      const response = await fetch(`${API_URL}/api/v1/receipts/${item.id}`, {
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
      window.dispatchEvent(new Event(receiptHistoryChangedEventName))
    } catch (error) {
      await showAlert(error.message || '영수증 내역 삭제 중 문제가 발생했어요.', { title: '삭제 실패' })
    } finally {
      setDeletingId(null)
    }
  }

  const startEditTitle = (item) => {
    setEditingTitleId(item.id)
    setTitleDraft(item.store === '상호명 미확인' ? '' : item.store)
  }

  const cancelEditTitle = () => {
    setEditingTitleId(null)
    setTitleDraft('')
  }

  const saveTitle = async (item) => {
    const trimmed = titleDraft.trim()

    if (!trimmed) {
      await showAlert('영수증 제목을 입력해주세요.', { title: '제목 수정' })
      return
    }

    if (trimmed === item.store) {
      cancelEditTitle()
      return
    }

    const token = window.localStorage.getItem('bobbeori-token')
    if (!token) {
      return
    }

    setIsSavingTitle(true)

    try {
      const response = await fetch(`${API_URL}/api/v1/receipts/${item.id}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ store_name: trimmed }),
      })

      if (!response.ok) {
        const data = await response.json().catch(() => ({}))
        throw new Error(data.detail || '영수증 제목 수정에 실패했어요.')
      }

      const updated = mapHistoryEntry(await response.json())
      setHistory((prev) => prev.map((entry) => (entry.id === item.id ? updated : entry)))
      cancelEditTitle()
    } catch (error) {
      await showAlert(error.message || '영수증 제목 수정 중 문제가 발생했어요.', { title: '수정 실패' })
    } finally {
      setIsSavingTitle(false)
    }
  }

  const enterSelectionMode = () => {
    setSelectionMode(true)
    setSelectedIds([])
  }

  const exitSelectionMode = () => {
    setSelectionMode(false)
    setSelectedIds([])
  }

  const toggleSelect = (id) => {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((value) => value !== id) : [...prev, id]))
  }

  const toggleSelectAll = () => {
    setSelectedIds((prev) => (prev.length === history.length ? [] : history.map((entry) => entry.id)))
  }

  const handleDeleteSelected = async () => {
    if (selectedIds.length === 0) {
      return
    }

    const confirmed = await showConfirm(
      `선택한 영수증 ${selectedIds.length}건을 삭제할까요?\n삭제하면 구매 통계에서도 제외되며, 냉장고에 입고된 식재료는 유지됩니다.`,
      { title: '선택 삭제', confirmText: '삭제', cancelText: '취소' },
    )

    if (!confirmed) {
      return
    }

    const token = window.localStorage.getItem('bobbeori-token')
    if (!token) {
      return
    }

    const targetIds = selectedIds
    setIsBulkDeleting(true)

    try {
      const results = await Promise.allSettled(
        targetIds.map((id) =>
          fetch(`${API_URL}/api/v1/receipts/${id}`, {
            method: 'DELETE',
            headers: { Authorization: `Bearer ${token}` },
          }),
        ),
      )

      const deletedIds = targetIds.filter(
        (id, index) => results[index].status === 'fulfilled' && results[index].value.ok,
      )
      const failedIds = targetIds.filter((id) => !deletedIds.includes(id))

      if (deletedIds.length > 0) {
        const remaining = history.filter((entry) => !deletedIds.includes(entry.id))
        setHistory(remaining)

        if (deletedIds.includes(selectedId)) {
          setSelectedId(remaining[0]?.id ?? null)
        }
        window.dispatchEvent(new Event(receiptHistoryChangedEventName))
      }

      if (failedIds.length > 0) {
        setSelectedIds(failedIds)
        await showAlert(`${deletedIds.length}건 삭제 완료, ${failedIds.length}건은 삭제하지 못했어요.`, {
          title: '일부 삭제 실패',
        })
      } else {
        exitSelectionMode()
      }
    } catch (error) {
      await showAlert(error.message || '선택 삭제 중 문제가 발생했어요.', { title: '삭제 실패' })
    } finally {
      setIsBulkDeleting(false)
    }
  }

  return (
    <section className="receipt-panel receipt-history" aria-labelledby="receipt-history-title">
      <div className="receipt-panel__title">
        <h2 id="receipt-history-title">최근 영수증 내역</h2>
        {status === 'ready' && history.length > 0 ? (
          <div className="receipt-history__actions">
            {selectionMode ? (
              <>
                <button type="button" onClick={toggleSelectAll}>
                  {selectedIds.length === history.length ? '전체 해제' : '전체 선택'}
                </button>
                <button
                  type="button"
                  className="receipt-history__select-delete"
                  disabled={selectedIds.length === 0 || isBulkDeleting}
                  onClick={handleDeleteSelected}
                >
                  {isBulkDeleting
                    ? '삭제 중...'
                    : `선택 삭제${selectedIds.length > 0 ? ` (${selectedIds.length})` : ''}`}
                </button>
                <button type="button" onClick={exitSelectionMode}>
                  취소
                </button>
              </>
            ) : (
              <>
                <button type="button" onClick={enterSelectionMode}>
                  선택 삭제
                </button>
                {history.length > 3 ? (
                  <button type="button" onClick={() => setShowAllHistory((prev) => !prev)}>
                    {showAllHistory ? '접기' : '내역보기'}
                  </button>
                ) : null}
              </>
            )}
          </div>
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
          <div className={`receipt-history-list ${selectionMode ? 'is-selecting' : ''}`}>
            {visibleHistory.map((item) => {
              const isChecked = selectedIds.includes(item.id)

              return (
                <button
                  className={[
                    selectionMode ? 'is-selectable' : '',
                    selectionMode ? (isChecked ? 'is-checked' : '') : selectedId === item.id ? 'is-active' : '',
                  ]
                    .filter(Boolean)
                    .join(' ')}
                  key={item.id}
                  type="button"
                  aria-pressed={selectionMode ? isChecked : undefined}
                  onClick={() => {
                    if (selectionMode) {
                      toggleSelect(item.id)
                      return
                    }

                    cancelEditTitle()
                    setSelectedId(item.id)
                  }}
                >
                  <span className="receipt-history-list__marker" aria-hidden="true" />
                  <div>
                    <strong>{item.title}</strong>
                    <p>{item.meta}</p>
                  </div>
                  <b>{item.amount}</b>
                  <em>{item.status}</em>
                </button>
              )
            })}
          </div>
          {!selectionMode && selectedHistory ? (
            <article className="receipt-history-detail" aria-label={`${selectedHistory.title} 상세 내역`}>
              <div>
                <span>{selectedHistory.date}</span>
                {editingTitleId === selectedHistory.id ? (
                  <div className="receipt-history-detail__title-edit">
                    <label className="receipt-ocr-meta__field receipt-history-detail__title-field">
                      <small>매장명:</small>
                      <input
                        className="receipt-inline-input"
                        type="text"
                        value={titleDraft}
                        maxLength={100}
                        placeholder="상호명 미확인"
                        autoFocus
                        disabled={isSavingTitle}
                        onChange={(event) => setTitleDraft(event.target.value)}
                        onKeyDown={(event) => {
                          if (event.key === 'Enter') {
                            saveTitle(selectedHistory)
                          } else if (event.key === 'Escape') {
                            cancelEditTitle()
                          }
                        }}
                      />
                    </label>
                    <button type="button" disabled={isSavingTitle} onClick={() => saveTitle(selectedHistory)}>
                      {isSavingTitle ? '저장 중...' : '저장'}
                    </button>
                    <button type="button" disabled={isSavingTitle} onClick={cancelEditTitle}>
                      취소
                    </button>
                  </div>
                ) : (
                  <div className="receipt-history-detail__title">
                    <button
                      type="button"
                      className="receipt-history-detail__title-trigger"
                      aria-label={`${selectedHistory.store} 매장명 수정`}
                      title="클릭하여 매장명 수정"
                      onClick={() => startEditTitle(selectedHistory)}
                    >
                      <strong>{selectedHistory.store}</strong>
                    </button>
                  </div>
                )}
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

export default ReceiptOcr
