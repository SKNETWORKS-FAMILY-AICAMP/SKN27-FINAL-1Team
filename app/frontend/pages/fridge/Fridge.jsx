import React, { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import './Fridge.css'

import imageAlarm from '../../assets/extracted/images/image_alarm.png'
import imagePutting from '../../assets/extracted/images/image_putting.png'
import imageDefaultIngredient from '../../assets/extracted/images/image_default_ingredient.png'
import { useAppDialog } from '../../components/AppDialog.jsx'
import IngredientModal from '../../components/modals/IngredientModal'
import ConfirmModal from '../../components/modals/ConfirmModal'
import { initialIngredientFormData as initialFormData } from '../../mock/fridgeMock.js'
import { API_URL } from '../../utils/api.js'

const FILTER_TYPES = [
  { label: '전체', tone: '' },
  { label: '냉장', tone: 'cold' },
  { label: '냉동', tone: 'frozen' },
  { label: '실온', tone: 'room' },
  { label: '소비 임박', tone: 'soon' },
  { label: '기한 지남', tone: 'expired' },
]

const STORAGE_KEYS = ['냉장', '냉동', '실온']

// 보관 위치 배지 색상을 실제 보관 위치 기준으로 고정합니다.
function getStorageTone(storageMethod = '') {
  if (storageMethod === STORAGE_KEYS[0]) return 'is-cold'
  if (storageMethod === STORAGE_KEYS[1]) return 'is-frozen'
  if (storageMethod === STORAGE_KEYS[2]) return 'is-room'
  return ''
}

// 이미지가 없을 때도 같은 레이아웃을 유지하는 슬롯 컴포넌트입니다.
function ImageSlot({ src, alt = '', className = '' }) {
  return (
    <span className={`fridge-image-slot ${src ? 'is-filled' : ''} ${className}`}>
      {src ? <img src={src} alt={alt} /> : null}
    </span>
  )
}

// 식재료 이미지 파일명을 검색용 키로 정규화합니다.
function normalizeIngredientImageName(name = '') {
  return name.replace(/\.[^.]+$/, '').replace(/\s/g, '').toLowerCase()
}


const INGREDIENT_IMAGE_ALIASES = {
  계란: '달걀',
  쇠고기: '소고기',
  돈육: '돼지고기',
  고추가루: '고춧가루',
  케찹: '케첩',
}

// 이미지 파일명이 다른 동의어를 대표 이미지명으로 맞춥니다.
function normalizeIngredientImageKey(name = '') {
  const key = normalizeIngredientImageName(name)
  return INGREDIENT_IMAGE_ALIASES[key] || key
}

const ingredientImages = Object.entries(
  import.meta.glob('../../assets/extracted/ingredients/*.{png,jpg,jpeg,webp,svg}', {
    eager: true,
    import: 'default',
  }),
)
  .map(([path, src]) => {
    const fileName = path.split('/').pop() || ''
    const name = fileName.replace(/\.[^.]+$/, '')
    return { name, key: normalizeIngredientImageName(name), src }
  })
  .sort((a, b) => b.key.length - a.key.length)

// 재료 이름에 맞는 대표 식재료 이미지를 선택합니다.
function getIngredientIcon(name = '') {
  const key = normalizeIngredientImageKey(name)
  const image = ingredientImages.find((item) => item.key === key)
  return image?.src || imageDefaultIngredient
}

// 날짜 문자열을 로컬 Date 객체로 변환합니다.
function parseDate(value) {
  if (!value) return null
  return new Date(`${value}T00:00:00`)
}

// 소비기한 기준 D-day와 상태 플래그를 계산합니다.
function enrichIngredient(item) {
  const expirationDate = item.expiration_date || item.expirationDate
  const target = parseDate(expirationDate)
  if (!target) {
    return { ...item, is_expiring_soon: false, is_expired: false, status: item.status || 'normal' }
  }

  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const dDay = Math.ceil((target.getTime() - today.getTime()) / (1000 * 60 * 60 * 24))

  return {
    ...item,
    expiration_date: expirationDate,
    d_day: item.d_day ?? dDay,
    is_expired: item.is_expired ?? dDay < 0,
    is_expiring_soon: item.is_expiring_soon ?? (dDay >= 0 && dDay <= 3),
    status: item.status || (dDay < 0 ? 'expired' : dDay <= 3 ? 'expiring' : 'normal'),
  }
}

// 초성 나열 같은 식재료가 아닌 입력을 등록 전에 걸러냅니다.
const isValidIngredientName = (name) => /[가-힣A-Za-z]/.test((name || '').trim())

// 재료 목록에서 화면 상단 요약 값을 계산합니다.
function buildSummary(items) {
  const enrichedItems = items.map(enrichIngredient)
  return {
    total: enrichedItems.length,
    expiring_soon: enrichedItems.filter((item) => item.is_expiring_soon && !item.is_expired).length,
    expired: enrichedItems.filter((item) => item.is_expired).length,
    storage: {
      냉장: enrichedItems.filter((item) => item.storage_method === '냉장').length,
      냉동: enrichedItems.filter((item) => item.storage_method === '냉동').length,
      실온: enrichedItems.filter((item) => item.storage_method === '실온').length,
      기타: enrichedItems.filter((item) => !STORAGE_KEYS.includes(item.storage_method)).length,
    },
  }
}

// API 응답 또는 mock 데이터를 화면에서 쓰기 좋은 형태로 정규화합니다.
function normalizeIngredient(item) {
  return enrichIngredient({
    ...item,
    storage_method: item.storage_method || '냉장',
    unit: item.unit || '개',
    quantity: Number(item.quantity) || 1,
  })
}

// D-day 값을 사용자가 읽기 좋은 문구로 변환합니다.
function getDdayLabel(item) {
  if (item.d_day === null || item.d_day === undefined) return '-'
  if (item.d_day > 0) return `D-${item.d_day}`
  if (item.d_day === 0) return 'D-Day'
  return `D+${Math.abs(item.d_day)} 지남`
}

// 냉장고 재료 목록과 등록/수정/소비 흐름을 관리하는 페이지 컴포넌트입니다.
function Fridge() {
  const navigate = useNavigate()
  const { dialogNode, showAlert } = useAppDialog()
  const [ingredients, setIngredients] = useState([])
  const [summary, setSummary] = useState(buildSummary([]))
  const [activeFilter, setActiveFilter] = useState('전체')
  const [searchQuery, setSearchQuery] = useState('')
  const [viewMode, setViewMode] = useState('grid')
  const [sortType, setSortType] = useState('latest')
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [formData, setFormData] = useState(initialFormData)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [confirmModal, setConfirmModal] = useState({ isOpen: false, title: '', message: '', onConfirm: null })
  const [consumeTarget, setConsumeTarget] = useState(null)
  const [isEditMode, setIsEditMode] = useState(false)
  const [selectedIds, setSelectedIds] = useState(new Set())
  const [recentStockTick, setRecentStockTick] = useState(0)
  const recentStockedItemIdSet = useMemo(() => {
    const receiptItems = ingredients
      .filter((item) => item.receipt_item_id && item.created_at)
      .map((item) => ({ id: Number(item.id), createdAt: new Date(item.created_at).getTime() }))
      .filter((item) => Number.isFinite(item.createdAt))

    if (!receiptItems.length) return new Set()

    // 최신 OCR 입고 묶음만 잠시 강조합니다.
    const latestCreatedAt = Math.max(...receiptItems.map((item) => item.createdAt))
    if (Date.now() - latestCreatedAt > 60 * 1000) return new Set()

    return new Set(receiptItems.filter((item) => latestCreatedAt - item.createdAt <= 60 * 1000).map((item) => item.id))
  }, [ingredients, recentStockTick])

  // OCR 입고 강조가 1분 뒤 자동으로 사라지도록 화면을 한 번 갱신합니다.
  useEffect(() => {
    const receiptTimes = ingredients
      .filter((item) => item.receipt_item_id && item.created_at)
      .map((item) => new Date(item.created_at).getTime())
      .filter(Number.isFinite)

    if (!receiptTimes.length) return undefined

    const remainingMs = 60 * 1000 - (Date.now() - Math.max(...receiptTimes))
    if (remainingMs <= 0) return undefined

    const timer = window.setTimeout(() => setRecentStockTick((tick) => tick + 1), remainingMs + 50)
    return () => window.clearTimeout(timer)
  }, [ingredients])

  // 현재 브라우저에 저장된 로그인 토큰을 반환합니다.
  const getToken = () => window.localStorage.getItem('bobbeori-token')

  // 인증 실패 시 토큰을 제거하고 demo 데이터 화면으로 복귀합니다.
  const handleAuthFailure = async () => {
    window.localStorage.removeItem('bobbeori-token')
    setIngredients([])
    setSummary(buildSummary([]))
    await showAlert('로그인이 만료되었습니다. 다시 로그인한 뒤 이용해주세요.', { title: '로그인 만료' })
  }

  // 백엔드에서 냉장고 목록과 요약 정보를 가져옵니다.
  const fetchFridgeData = async () => {
    const token = getToken()
    if (!token) {
      setSummary(buildSummary(ingredients))
      return
    }

    try {
      const resIngredients = await fetch(`${API_URL}/api/v1/inventory`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (resIngredients.status === 401 || resIngredients.status === 403) {
        await handleAuthFailure()
        return
      }
      if (resIngredients.ok) {
        const data = await resIngredients.json()
        setIngredients(data.map(normalizeIngredient))
      }

      const resSummary = await fetch(`${API_URL}/api/v1/inventory/summary`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (resSummary.status === 401 || resSummary.status === 403) {
        await handleAuthFailure()
        return
      }
      if (resSummary.ok) {
        const data = await resSummary.json()
        setSummary(data)
      }
    } catch (err) {
      console.error('냉장고 데이터를 불러오지 못했습니다:', err)
    }
  }

  useEffect(() => {
    fetchFridgeData()
  }, [])

  useEffect(() => {
    // 챗봇에서 재료 등록/소비가 끝나면 냉장고 목록을 즉시 다시 불러옵니다.
    window.addEventListener('bobbeori:inventory-updated', fetchFridgeData)
    return () => window.removeEventListener('bobbeori:inventory-updated', fetchFridgeData)
  }, [])

  useEffect(() => {
    if (!getToken()) setSummary(buildSummary(ingredients))
  }, [ingredients])

  const filterCounts = useMemo(
    () => ({
      전체: summary.total,
      냉장: summary.storage?.냉장 || 0,
      냉동: summary.storage?.냉동 || 0,
      실온: summary.storage?.실온 || 0,
      '소비 임박': summary.expiring_soon || 0,
      '기한 지남': summary.expired || 0,
    }),
    [summary],
  )

  const visibleFilters = useMemo(
    () => FILTER_TYPES.filter((filter) => filter.label === '전체' || filterCounts[filter.label] > 0),
    [filterCounts],
  )

  useEffect(() => {
    if (!visibleFilters.some((filter) => filter.label === activeFilter)) setActiveFilter('전체')
  }, [activeFilter, visibleFilters])

  const sortedIngredients = useMemo(() => {
    const normalizedQuery = searchQuery.trim().toLowerCase()
    const filteredIngredients = ingredients.filter((item) => {
      const matchesCategory =
        activeFilter === '전체' ||
        (activeFilter === '냉장' && item.storage_method === '냉장') ||
        (activeFilter === '냉동' && item.storage_method === '냉동') ||
        (activeFilter === '실온' && item.storage_method === '실온') ||
        (activeFilter === '소비 임박' && item.is_expiring_soon && !item.is_expired) ||
        (activeFilter === '기한 지남' && item.is_expired)
      const matchesSearch =
        normalizedQuery === '' ||
        item.name.toLowerCase().includes(normalizedQuery) ||
        (item.category && item.category.toLowerCase().includes(normalizedQuery))

      return matchesCategory && matchesSearch
    })

    return [...filteredIngredients].sort((a, b) => {
      if (sortType === 'oldest') return a.id - b.id
      if (sortType === 'expiry') return (a.d_day ?? 999) - (b.d_day ?? 999)
      return b.id - a.id
    })
  }, [activeFilter, ingredients, searchQuery, sortType])

  // 현재 정렬 상태의 버튼 라벨을 반환합니다.
  const getSortLabel = () => {
    if (sortType === 'oldest') return '등록일 오래된순'
    if (sortType === 'expiry') return '소비기한 임박순'
    return '등록일 최신순'
  }

  // 최신순, 오래된순, 소비기한순 정렬을 순환합니다.
  const toggleSort = () => {
    setSortType((prev) => {
      if (prev === 'latest') return 'oldest'
      if (prev === 'oldest') return 'expiry'
      return 'latest'
    })
  }

  // 입력 폼의 단일 필드 변경을 반영하고, 수정 중 기준값이 바뀌면 소비기한을 자동 재계산 상태로 되돌립니다.
  const handleFormChange = (event) => {
    const { name, value } = event.target
    setFormData((prev) => {
      const nextFormData = { ...prev, [name]: value }

      if (editingId !== null && ['category', 'storage_method', 'purchase_date'].includes(name)) {
        nextFormData.expiration_date = ''
      }

      return nextFormData
    })
  }

  // 등록/수정 모달을 닫고 폼을 초기화합니다.
  const closeModal = () => {
    setIsModalOpen(false)
    setFormData(initialFormData)
    setEditingId(null)
  }

  // 새 식재료 등록 모달을 엽니다.
  const openAddModal = () => {
    setFormData(initialFormData)
    setEditingId(null)
    setIsModalOpen(true)
  }

  // 기존 식재료 정보를 폼에 채우고, 소비기한은 비워 자동 재계산되도록 수정 모달을 엽니다.
  const openEditModal = (item) => {
    setFormData({
      name: item.name || '',
      category: item.category || '기타',
      storage_method: item.storage_method || '냉장',
      quantity: Number(item.quantity) || 1,
      unit: item.unit || '개',
      purchase_date: item.purchase_date || new Date().toISOString().split('T')[0],
      expiration_date: item.expiration_date || '',
    })
    setEditingId(item.id)
    setIsModalOpen(true)
  }

  // 로그인 상태에 따라 로컬 mock 또는 백엔드 API로 식재료를 저장합니다.
  const handleSubmitIngredient = async () => {
    if (!formData.name.trim()) {
      await showAlert('재료 이름을 입력해주세요.', { title: '입력 확인' })
      return
    }

    if (!isValidIngredientName(formData.name)) {
      await showAlert('올바른 식재료 이름을 입력해주세요.', { title: '입력 확인' })
      return
    }
    const payload = {
      ...formData,
      quantity: Math.round(Number(formData.quantity) * 2) / 2,
      purchase_date: formData.purchase_date || null,
      expiration_date: formData.expiration_date || null,
    }

    const token = getToken()
    if (!token) {
      setIngredients((prev) => {
        if (editingId !== null) {
          return prev.map((item) => (item.id === editingId ? normalizeIngredient({ ...item, ...payload }) : item))
        }
        return [normalizeIngredient({ ...payload, id: Date.now() }), ...prev]
      })
      setActiveFilter('전체')
      setSearchQuery('')
      closeModal()
      return
    }

    setIsSubmitting(true)
    try {
      const isEditing = editingId !== null
      const url = isEditing ? `${API_URL}/api/v1/inventory/${editingId}` : `${API_URL}/api/v1/inventory`
      const response = await fetch(url, {
        method: isEditing ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify(payload),
      })

      if (response.status === 401 || response.status === 403) {
        await handleAuthFailure()
        closeModal()
        return
      }
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}))
        await showAlert(errData.detail || '재료 저장에 실패했습니다.')
        return
      }

      const savedItem = await response.json()
      setIngredients((prev) => {
        if (isEditing) {
          return prev.map((item) => (item.id === editingId ? normalizeIngredient(savedItem) : item))
        }
        return [normalizeIngredient(savedItem), ...prev]
      })
      closeModal()
      fetchFridgeData()
    } catch (err) {
      console.error(err)
      await showAlert('서버 통신 중 오류가 발생했습니다.', { title: '서버 오류' })
    } finally {
      setIsSubmitting(false)
    }
  }

  // 식재료를 삭제하거나, 로그인 전 상태에서는 로컬 목록에서 제거합니다.
  const executeDelete = async (id) => {
    const token = getToken()
    if (!token) {
      setIngredients((prev) => prev.filter((item) => item.id !== id))
      setConfirmModal({ isOpen: false, title: '', message: '', onConfirm: null })
      return
    }

    try {
      const response = await fetch(`${API_URL}/api/v1/inventory/${id}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      })
      if (response.status === 401 || response.status === 403) {
        await handleAuthFailure()
        return
      }
      if (response.ok) {
        setConfirmModal({ isOpen: false, title: '', message: '', onConfirm: null })
        fetchFridgeData()
      } else {
        await showAlert('폐기에 실패했습니다.', { title: '폐기 실패' })
      }
    } catch (err) {
      console.error(err)
      await showAlert('서버 오류로 폐기하지 못했습니다.', { title: '서버 오류' })
    }
  }

  // 다중 폐기를 위한 선택 토글
  const toggleSelect = (id) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  // 전체 선택 토글 (현재 화면에 필터링/검색되어 보이는 재료 기준)
  const toggleSelectAll = () => {
    if (selectedIds.size === sortedIngredients.length) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(sortedIngredients.map((item) => item.id)))
    }
  }

  // 다중 삭제 실행
  const executeBulkDelete = async () => {
    if (selectedIds.size === 0) return

    const token = getToken()
    const idsArray = Array.from(selectedIds)

    if (!token) {
      setIngredients((prev) => prev.filter((item) => !selectedIds.has(item.id)))
      setSelectedIds(new Set())
      setIsEditMode(false)
      setConfirmModal({ isOpen: false, title: '', message: '', onConfirm: null })
      return
    }

    try {
      const response = await fetch(`${API_URL}/api/v1/inventory/bulk`, {
        method: 'DELETE',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ ingredient_ids: idsArray }),
      })
      
      if (response.status === 401 || response.status === 403) {
        await handleAuthFailure()
        return
      }
      if (response.ok) {
        setConfirmModal({ isOpen: false, title: '', message: '', onConfirm: null })
        setSelectedIds(new Set())
        setIsEditMode(false)
        fetchFridgeData()
      } else {
        await showAlert('일괄 폐기에 실패했습니다.', { title: '폐기 실패' })
      }
    } catch (err) {
      console.error(err)
      await showAlert('서버 오류로 폐기하지 못했습니다.', { title: '서버 오류' })
    }
  }

  // 삭제 확인 모달을 엽니다.
  const handleDeleteClick = (id, name) => {
    setConfirmModal({
      isOpen: true,
      title: '재료 폐기',
      message: (
        <>
          <span style={{ color: 'var(--figma-coral)', fontWeight: 'bold', fontSize: '18px' }}>{name}</span>을<br />
          냉장고에서 완전히 폐기하시겠습니까?
        </>
      ),
      onConfirm: () => executeDelete(id),
    })
  }

  // 소비 수량 입력 모달을 엽니다.
  const handleConsumeClick = (item) => {
    setConsumeTarget({ item, consumeAmount: 1 })
  }

  // 일부 소비는 수량 수정, 전체 소비는 삭제로 처리합니다.
  const executeConsume = async (item, consumeAmount) => {
    if (Number.isNaN(consumeAmount) || consumeAmount <= 0) {
      await showAlert('올바른 소비 수량을 입력해주세요.', { title: '입력 오류' })
      return
    }

    const currentQty = Number(item.quantity)
    if (consumeAmount > currentQty) {
      await showAlert(`보유 수량(${currentQty}${item.unit})보다 많이 소비할 수 없습니다.`, { title: '수량 초과' })
      return
    }

    setConsumeTarget(null)
    if (consumeAmount === currentQty) {
      setConfirmModal({
        isOpen: true,
        title: '모두 소비',
        message: <span style={{ color: 'var(--figma-coral)', fontWeight: 'bold', fontSize: '18px' }}>{item.name}을 모두 소비 처리할까요?</span>,
        onConfirm: () => executeDelete(item.id),
      })
      return
    }

    const newQuantity = Math.round((currentQty - consumeAmount) * 2) / 2
    const payload = {
      name: item.name,
      category: item.category,
      storage_method: item.storage_method,
      quantity: newQuantity,
      unit: item.unit,
      purchase_date: item.purchase_date,
      expiration_date: item.expiration_date,
    }

    const token = getToken()
    if (!token) {
      setIngredients((prev) => prev.map((target) => (target.id === item.id ? normalizeIngredient({ ...target, quantity: newQuantity }) : target)))
      return
    }

    try {
      const response = await fetch(`${API_URL}/api/v1/inventory/${item.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify(payload),
      })
      if (response.status === 401 || response.status === 403) {
        await handleAuthFailure()
        return
      }
      if (!response.ok) {
        await showAlert('소비 처리에 실패했습니다.', { title: '소비 처리 실패' })
        return
      }
      fetchFridgeData()
    } catch (err) {
      console.error(err)
      await showAlert('서버 오류로 소비 처리하지 못했습니다.', { title: '서버 오류' })
    }
  }

  // 소비 모달은 공통 ConfirmModal이 아니라서 Enter 확인을 여기서 처리합니다.
  useEffect(() => {
    if (!consumeTarget) return

    const handleKeyDown = (event) => {
      if (event.key !== 'Enter') return
      event.preventDefault()
      executeConsume(consumeTarget.item, Number(consumeTarget.consumeAmount))
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [consumeTarget])


  return (
    <section className="fridge-page" aria-labelledby="fridge-title">
      <div className="fridge-hero">
        <div className="fridge-hero__copy">
          <h1 id="fridge-title">냉장고 재료 관리</h1>
          <p>우리 집 재료를 한눈에 관리하고, 소비기한이 가까운 재료를 먼저 확인해요.</p>
          <label className="fridge-search" aria-label="재료명 검색">
            <span aria-hidden="true" />
            <input
              type="search"
              placeholder="재료명이나 카테고리로 검색해보세요"
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
            />
          </label>
        </div>

        <div className="fridge-hero__actions">
          <button className="fridge-hero-card" type="button" onClick={() => navigate('/receipt-ocr')}>
            <div>
              <strong>영수증 OCR 입고</strong>
              <p>영수증 촬영으로 재료를 한 번에 등록해요.</p>
            </div>
          </button>
          <button className="fridge-hero-card fridge-hero-card--add" type="button" onClick={() => navigate('/recipe-fridge')}>
            <div>
              <strong>레시피 추천 받기</strong>
              <p>보유 재료로 만들 수 있는 메뉴를 추천받아요.</p>
            </div>
          </button>
        </div>

        <ImageSlot className="fridge-hero__image" src={imagePutting} />
      </div>

      <div className="fridge-layout">
        <main className="fridge-main">
          <div className="fridge-toolbar">
            <div className="fridge-filters" aria-label="재료 상태 필터">
              {visibleFilters.map((filter) => (
                <button
                  className={['fridge-filter', activeFilter === filter.label ? 'is-active' : '', filter.tone ? `is-${filter.tone}` : '']
                    .filter(Boolean)
                    .join(' ')}
                  key={filter.label}
                  type="button"
                  onClick={() => setActiveFilter(filter.label)}
                >
                  {filter.label} ({filterCounts[filter.label]})
                </button>
              ))}
            </div>

            <div className="fridge-view-controls">
              {ingredients.length > 0 ? (
                <button
                  type="button"
                  className={`fridge-edit-toggle ${isEditMode ? 'is-active' : ''}`}
                  onClick={() => {
                    setIsEditMode(!isEditMode)
                    setSelectedIds(new Set())
                  }}
                >
                  {isEditMode ? '선택 취소' : '선택 폐기'}
                </button>
              ) : null}
              <button type="button" onClick={toggleSort}>{getSortLabel()}</button>
              <button className={viewMode === 'grid' ? 'fridge-view-button is-grid is-active' : 'fridge-view-button is-grid'} type="button" aria-label="그리드 보기" onClick={() => setViewMode('grid')}>
                <span />
              </button>
              <button className={viewMode === 'list' ? 'fridge-view-button is-list is-active' : 'fridge-view-button is-list'} type="button" aria-label="리스트 보기" onClick={() => setViewMode('list')}>
                <span />
              </button>
            </div>
          </div>

          <div className={viewMode === 'list' ? 'fridge-card-grid is-list' : 'fridge-card-grid'}>
            {ingredients.length === 0 ? (
              <div className="fridge-empty-state">
                <ImageSlot className="fridge-empty-state__image" src={imagePutting} />
                <h3>냉장고가 비어 있어요.</h3>
                <p>첫 재료를 등록하고 소비기한 관리를 시작해보세요.</p>
                <button type="button" onClick={openAddModal}>+ 첫 재료 추가하기</button>
              </div>
            ) : sortedIngredients.length === 0 ? (
              <div className="fridge-empty-state">
                <h3>조건에 맞는 재료가 없습니다.</h3>
                <button type="button" onClick={() => setActiveFilter('전체')}>전체 보기</button>
              </div>
            ) : (
              <>
                {sortedIngredients.map((item) => {
                  const isRecentlyStocked = recentStockedItemIdSet.has(Number(item.id))

                  return (
                  <article 
                    className={[
                      'fridge-item',
                      item.is_expired ? 'is-expired' : item.is_expiring_soon ? 'is-urgent' : '',
                      selectedIds.has(item.id) ? 'is-selected' : '',
                      isRecentlyStocked ? 'is-recent-stocked' : '',
                    ].filter(Boolean).join(' ')}
                    key={item.id}
                    onClick={() => {
                      if (isEditMode) toggleSelect(item.id)
                    }}
                    style={{ cursor: isEditMode ? 'pointer' : 'default' }}
                  >
                    {isEditMode && (
                      <div className="fridge-item__checkbox">
                        <input 
                          type="checkbox" 
                          checked={selectedIds.has(item.id)} 
                          onChange={() => toggleSelect(item.id)} 
                          onClick={(e) => e.stopPropagation()}
                        />
                      </div>
                    )}
                    <div className="fridge-item__left">
                      <ImageSlot className="fridge-item__image" src={getIngredientIcon(item.name)} />
                      {item.is_ai_recommended ? (
                        <span className="fridge-ai-badge is-bottom-left" title="AI가 추천한 소비기한입니다">AI</span>
                      ) : null}
                    </div>
                    <div className="fridge-item__body">
                      <div className="fridge-item__title">
                        <h2>{item.name}</h2>
                        <span className={['fridge-storage-badge', getStorageTone(item.storage_method)].filter(Boolean).join(' ')}>{item.storage_method}</span>
                      </div>
                      <dl>
                        <div>
                          <dt>카테고리</dt>
                          <dd>{item.category || '-'}</dd>
                        </div>
                        <div>
                          <dt>수량</dt>
                          <dd>{Number(item.quantity)}{item.unit}</dd>
                        </div>
                        <div>
                          <dt>소비기한</dt>
                          <dd className="fridge-dday-wrapper" style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', alignItems: 'center' }}>
                            <span className={item.is_expired ? 'fridge-dday-expired' : item.is_expiring_soon ? 'fridge-dday-urgent' : 'fridge-dday-normal'} style={{ whiteSpace: 'nowrap' }}>
                              {getDdayLabel(item)}
                            </span>
                            {item.expiration_date ? <small className="fridge-dday-date" style={{ color: '#8b673e', opacity: 0.8, whiteSpace: 'nowrap' }}>({item.expiration_date})</small> : null}
                          </dd>
                        </div>
                      </dl>
                    </div>
                    <div className={`fridge-item__actions ${isEditMode ? 'is-edit-mode' : ''}`}>
                      <button type="button" onClick={() => openEditModal(item)}>수정</button>
                      <button type="button" onClick={() => handleConsumeClick(item)}>소비</button>
                      <button type="button" onClick={() => handleDeleteClick(item.id, item.name)}>폐기</button>
                    </div>
                  </article>
                  )
                })}

                <article className="fridge-add-card">
                  <ImageSlot className="fridge-add-card__image" src={imageAlarm} />
                  <strong>더 많은 재료를 추가해보세요.</strong>
                  <button type="button" onClick={openAddModal}>+ 재료 추가</button>
                </article>
              </>
            )}
          </div>
        </main>
      </div>

      <IngredientModal
        isOpen={isModalOpen}
        editingId={editingId}
        formData={formData}
        handleFormChange={handleFormChange}
        onClose={closeModal}
        onSubmit={handleSubmitIngredient}
        isSubmitting={isSubmitting}
      />

      <ConfirmModal
        isOpen={confirmModal.isOpen}
        title={confirmModal.title}
        message={confirmModal.message}
        onConfirm={confirmModal.onConfirm}
        onClose={() => setConfirmModal({ ...confirmModal, isOpen: false })}
      />

      {consumeTarget && (
        <div className="fridge-modal-overlay">
          <div className="fridge-modal-content fridge-confirm-modal" onClick={(event) => event.stopPropagation()}>
            <div className="fridge-modal-header">
              <h2>재료 소비</h2>
              <button type="button" onClick={() => setConsumeTarget(null)} aria-label="닫기">×</button>
            </div>
            <div className="fridge-modal-body" style={{ textAlign: 'center', padding: '30px 20px', fontSize: '16px', lineHeight: '1.6' }}>
              <span style={{ color: 'var(--figma-coral)', fontWeight: 'bold', fontSize: '18px' }}>{consumeTarget.item.name}</span>을 소비할까요?<br /><br />
              소비할 수량:{' '}
              <input
                type="number"
                min="0.5"
                max={consumeTarget.item.quantity}
                step="0.5"
                value={consumeTarget.consumeAmount}
                onChange={(event) => setConsumeTarget({ ...consumeTarget, consumeAmount: event.target.value })}
                style={{ width: '80px', padding: '8px', textAlign: 'center', borderRadius: '8px', border: '1px solid #ddd', fontSize: '16px' }}
              /> {consumeTarget.item.unit}
            </div>
            <div className="fridge-modal-footer">
              <button type="button" className="btn-cancel" onClick={() => setConsumeTarget(null)}>취소</button>
              <button type="button" className="btn-submit btn-danger" onClick={() => executeConsume(consumeTarget.item, Number(consumeTarget.consumeAmount))}>확인</button>
            </div>
          </div>
        </div>
      )}

      {dialogNode}

      {isEditMode && (
        <div className="fridge-bulk-bar">
          <div className="fridge-bulk-bar__content">
            <button 
              type="button" 
              className={`btn-select-all ${selectedIds.size > 0 && selectedIds.size === sortedIngredients.length ? 'is-active' : ''}`} 
              onClick={toggleSelectAll}
            >
              {selectedIds.size > 0 && selectedIds.size === sortedIngredients.length ? '전체 해제' : '전체 선택'}
            </button>
            <span className="fridge-bulk-bar__count">
              {selectedIds.size}개 선택됨
            </span>
            <div className="fridge-bulk-bar__actions">
              <button 
                type="button" 
                className="btn-cancel" 
                onClick={() => {
                  setIsEditMode(false)
                  setSelectedIds(new Set())
                }}
              >
                취소
              </button>
              <button 
                type="button" 
                className="btn-submit btn-danger" 
                onClick={() => {
                  if(selectedIds.size === 0) return
                  setConfirmModal({
                    isOpen: true,
                    title: '다중 폐기',
                    message: <span style={{ color: 'var(--figma-coral)', fontWeight: 'bold', fontSize: '18px' }}>선택한 {selectedIds.size}개의 재료를 일괄 폐기하시겠습니까?</span>,
                    onConfirm: executeBulkDelete,
                  })
                }}
                disabled={selectedIds.size === 0}
              >
                선택 항목 폐기
              </button>
            </div>
          </div>
        </div>
      )}
      <button className="fridge-floating-add" type="button" aria-label="재료 추가" onClick={openAddModal}>+</button>
    </section>
  )
}

export default Fridge
