import React, { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import './Fridge.css'

import imageAlarm from '../../assets/extracted/images/image_alarm.png'
import imagePutting from '../../assets/extracted/images/image_putting.png'
import { useAppDialog } from '../../components/AppDialog.jsx'
import IngredientModal from '../../components/modals/IngredientModal'
import ConfirmModal from '../../components/modals/ConfirmModal'
import { initialIngredientFormData as initialFormData } from '../../mock/fridgeMock.js'
import { API_URL } from '../../utils/api.js'
import { trackEvent } from '../../utils/analytics.js'
import {
  getIngredientImageUrl,
  normalizeIngredientImageName,
  useIngredientImageCatalog,
} from '../../utils/ingredientImages.js'
import { removeStoredRecipe } from '../../utils/savedRecipes.js'
import { getFridgeNameClass } from './fridgeName.js'

const FILTER_TYPES = ['전체', '냉장', '냉동', '실온', '소비 임박', '기한 지남']

const STORAGE_KEYS = ['냉장', '냉동', '실온']

const SORT_OPTIONS = [
  { value: 'latest', label: '최근 등록순' },
  { value: 'expiry', label: '소비기한 빠른 순' },
]

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
      {src ? (
        <img src={src} alt={alt} />
      ) : (
        <span className="fridge-image-placeholder" aria-hidden="true">
          <svg viewBox="0 0 48 48">
            <path d="M10 34h28M14 31a10 10 0 0 1 20 0M21 18h6M24 18v3" />
          </svg>
        </span>
      )}
    </span>
  )
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
  if (item.is_expiring_soon && !item.is_expired) return '소비 임박'
  if (item.d_day > 0) return `D-${item.d_day}`
  if (item.d_day === 0) return 'D-Day'
  return '기한 지남'
}

// 냉장고 재료 목록과 등록/수정/소비 흐름을 관리하는 페이지 컴포넌트입니다.
function Fridge() {
  const { dialogNode, showAlert } = useAppDialog()
  const location = useLocation()
  const navigate = useNavigate()
  const ingredientImageCatalog = useIngredientImageCatalog()
  const [ingredients, setIngredients] = useState([])
  const [summary, setSummary] = useState(buildSummary([]))
  const [activeFilter, setActiveFilter] = useState('전체')
  const [searchQuery, setSearchQuery] = useState('')
  const [sortType, setSortType] = useState('latest')
  const [isSortMenuOpen, setIsSortMenuOpen] = useState(false)
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [formData, setFormData] = useState(initialFormData)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [confirmModal, setConfirmModal] = useState({ isOpen: false, title: '', message: '', onConfirm: null })
  const [consumeTarget, setConsumeTarget] = useState(null)
  const [isEditMode, setIsEditMode] = useState(false)
  const [selectedIds, setSelectedIds] = useState(new Set())
  const [recentStockTick, setRecentStockTick] = useState(0)
  const [completionRecipe, setCompletionRecipe] = useState(() => location.state?.completionRecipe || null)
  const [completionIngredientRefs, setCompletionIngredientRefs] = useState(null)
  const [completionQuantities, setCompletionQuantities] = useState({})
  const [completionError, setCompletionError] = useState('')
  const [isCompletionLoading, setIsCompletionLoading] = useState(Boolean(location.state?.completionRecipe))
  const [isCompletionSubmitting, setIsCompletionSubmitting] = useState(false)
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

  const completionItems = useMemo(() => {
    if (!completionIngredientRefs) return []

    const ingredientIds = new Set(completionIngredientRefs.ingredientIds)
    const names = completionIngredientRefs.names.map(normalizeIngredientImageName)
    return ingredients.filter((item) => {
      if (ingredientIds.has(Number(item.ingredient_id))) return true

      const itemName = normalizeIngredientImageName(item.name)
      return names.some((name) => name && (itemName.includes(name) || name.includes(itemName)))
    })
  }, [completionIngredientRefs, ingredients])

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
  const isLoggedIn = Boolean(getToken())

  useEffect(() => {
    if (!completionRecipe) return undefined

    const controller = new AbortController()
    const loadCompletionIngredients = async () => {
      const token = getToken()
      if (!token) {
        setCompletionError('로그인 후 재료 소모를 확인할 수 있어요.')
        setIsCompletionLoading(false)
        return
      }

      try {
        const recipeId = completionRecipe.recipeId || completionRecipe.recipe_id || completionRecipe.id
        const response = await fetch(`${API_URL}/api/v1/recipes/${recipeId}`, {
          headers: { Authorization: `Bearer ${token}` },
          signal: controller.signal,
        })
        if (!response.ok) throw new Error('레시피 재료를 불러오지 못했어요.')

        const recipe = await response.json()
        const ownedIngredients = recipe.owned_ingredients || []
        const maybeOwnedIngredients = recipe.maybe_owned_ingredients || []
        setCompletionIngredientRefs({
          ingredientIds: ownedIngredients
            .map((ingredient) => Number(ingredient.ingredient_id))
            .filter(Number.isInteger),
          names: [
            ...ownedIngredients.map((ingredient) => ingredient.name),
            ...maybeOwnedIngredients.map((ingredient) => ingredient.fridge_ingredient_name),
          ].filter(Boolean),
        })
      } catch (error) {
        if (error.name !== 'AbortError') setCompletionError(error.message)
      } finally {
        if (!controller.signal.aborted) setIsCompletionLoading(false)
      }
    }

    loadCompletionIngredients()
    return () => controller.abort()
  }, [completionRecipe])

  useEffect(() => {
    if (!completionIngredientRefs) return
    setCompletionQuantities(
      Object.fromEntries(completionItems.map((item) => [item.id, String(item.quantity)])),
    )
  }, [completionIngredientRefs, completionItems])

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
    () => FILTER_TYPES.filter((filter) => filter === '전체' || filterCounts[filter] > 0),
    [filterCounts],
  )

  useEffect(() => {
    if (!visibleFilters.includes(activeFilter)) setActiveFilter('전체')
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
      if (sortType === 'expiry') return (a.d_day ?? 999) - (b.d_day ?? 999)
      return b.id - a.id
    })
  }, [activeFilter, ingredients, searchQuery, sortType])

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
    if (!getToken()) {
      navigate('/login')
      return
    }
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

  // 로그인한 사용자의 식재료를 백엔드 API에 저장합니다.
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
      closeModal()
      navigate('/login')
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
      if (!isEditing) {
        trackEvent('fridge_ingredient_add', { ingredient_id: String(savedItem.ingredient_id || savedItem.id) })
      }
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
  const executeDelete = async (id, consumedItem = null) => {
    const token = getToken()
    if (!token) {
      setIngredients((prev) => prev.filter((item) => item.id !== id))
      if (consumedItem) trackEvent('ingredient_consume', { ingredient_id: String(id), consume_all: true })
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
        if (consumedItem) trackEvent('ingredient_consume', { ingredient_id: String(id), consume_all: true })
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
        onConfirm: () => executeDelete(item.id, item),
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
      trackEvent('ingredient_consume', {
        ingredient_id: String(item.ingredient_id || item.id),
        quantity: consumeAmount,
        unit: item.unit,
        consume_all: false,
      })
      fetchFridgeData()
    } catch (err) {
      console.error(err)
      await showAlert('서버 오류로 소비 처리하지 못했습니다.', { title: '서버 오류' })
    }
  }

  const closeCompletionFlow = () => {
    setCompletionRecipe(null)
    navigate('/mypage?tab=saved', { replace: true })
  }

  const completeRecipeConsumption = async () => {
    const token = getToken()
    if (!token || !completionRecipe) return

    const updates = []
    for (const item of completionItems) {
      const value = completionQuantities[item.id]
      const remainingQuantity = Number(value)
      const currentQuantity = Number(item.quantity)
      if (String(value ?? '').trim() === '' || !Number.isFinite(remainingQuantity) || remainingQuantity < 0) {
        await showAlert(`${item.name}의 남은 수량을 확인해주세요.`, { title: '수량 확인' })
        return
      }
      if (remainingQuantity > currentQuantity) {
        await showAlert(`${item.name}의 남은 수량은 현재 수량보다 많을 수 없어요.`, { title: '수량 확인' })
        return
      }
      if (remainingQuantity !== currentQuantity) updates.push({ item, remainingQuantity })
    }

    setIsCompletionSubmitting(true)
    try {
      const responses = await Promise.all(updates.map(({ item, remainingQuantity }) => {
        if (remainingQuantity === 0) {
          return fetch(`${API_URL}/api/v1/inventory/${item.id}`, {
            method: 'DELETE',
            headers: { Authorization: `Bearer ${token}` },
          })
        }

        return fetch(`${API_URL}/api/v1/inventory/${item.id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
          body: JSON.stringify({
            name: item.name,
            category: item.category,
            storage_method: item.storage_method,
            quantity: remainingQuantity,
            unit: item.unit,
            purchase_date: item.purchase_date,
            expiration_date: item.expiration_date,
          }),
        })
      }))

      if (responses.some((response) => response.status === 401 || response.status === 403)) {
        await handleAuthFailure()
        return
      }
      if (responses.some((response) => !response.ok)) {
        throw new Error('재료 수량을 수정하지 못했어요.')
      }

      const recommendationId = Number(
        completionRecipe.recommendationId || completionRecipe.recommendation_id,
      )
      if (Number.isInteger(recommendationId)) {
        const deleteResponse = await fetch(`${API_URL}/api/v1/recommendations/${recommendationId}`, {
          method: 'DELETE',
          headers: { Authorization: `Bearer ${token}` },
        })
        if (!deleteResponse.ok && deleteResponse.status !== 404) {
          throw new Error('재료 수량은 반영했지만 저장 레시피를 삭제하지 못했어요.')
        }
      }

      removeStoredRecipe(completionRecipe.storageId)
      const legacyRecipe = window.localStorage.getItem('bobbeori-fridge-recipe')
      if (legacyRecipe) {
        try {
          const parsed = JSON.parse(legacyRecipe)
          if (String(parsed.id) === String(completionRecipe.recipeId || completionRecipe.id)) {
            window.localStorage.removeItem('bobbeori-fridge-recipe')
          }
        } catch {
          window.localStorage.removeItem('bobbeori-fridge-recipe')
        }
      }
      window.localStorage.setItem('bobbeori-last-cooked-recipe', completionRecipe.title)

      setCompletionRecipe(null)
      navigate('/fridge', { replace: true })
      await fetchFridgeData()
      await showAlert('재료 수량을 반영하고 저장된 레시피에서 삭제했어요.', { title: '요리 완료' })
    } catch (error) {
      await showAlert(error.message || '요리 완료 처리 중 오류가 발생했어요.', { title: '처리 실패' })
    } finally {
      setIsCompletionSubmitting(false)
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
        </div>
        {ingredients.length > 0 ? (
          <label className="fridge-search" aria-label="재료명 검색">
            <span aria-hidden="true" />
            <input
              type="search"
              placeholder="재료명이나 카테고리로 검색해보세요"
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
            />
          </label>
        ) : null}
      </div>

      <div className="fridge-layout">
        <main className="fridge-main">
          {ingredients.length > 0 ? (
            <div className="fridge-toolbar">
            <div className="fridge-filters" aria-label="재료 상태 필터">
              {visibleFilters.map((filter) => (
                <button
                  className={activeFilter === filter ? 'fridge-filter is-active' : 'fridge-filter'}
                  key={filter}
                  type="button"
                  onClick={() => setActiveFilter(filter)}
                >
                  {filter === '기한 지남' && filterCounts[filter] > 0 ? (
                    <>
                      <span className="fridge-filter__warning" aria-hidden="true">!</span>
                      {filter} {filterCounts[filter]}
                    </>
                  ) : filter}
                </button>
              ))}
            </div>

            <div className="fridge-toolbar-controls">
              <button
                type="button"
                className={`fridge-edit-toggle ${isEditMode ? 'is-active' : ''}`}
                onClick={() => {
                  setIsEditMode(!isEditMode)
                  setSelectedIds(new Set())
                }}
              >
                {isEditMode ? '선택 취소' : '일괄 선택'}
              </button>
              <div
                className="fridge-sort"
                onBlur={(event) => {
                  if (!event.currentTarget.contains(event.relatedTarget)) setIsSortMenuOpen(false)
                }}
                onKeyDown={(event) => {
                  if (event.key === 'Escape') setIsSortMenuOpen(false)
                }}
              >
                <button
                  type="button"
                  className="fridge-sort-trigger"
                  aria-haspopup="menu"
                  aria-expanded={isSortMenuOpen}
                  onClick={() => setIsSortMenuOpen((isOpen) => !isOpen)}
                >
                  {SORT_OPTIONS.find((option) => option.value === sortType)?.label}
                  <span className="fridge-sort-trigger__arrow" aria-hidden="true" />
                </button>
                {isSortMenuOpen ? (
                  <div className="fridge-sort-menu" role="menu">
                    {SORT_OPTIONS.map((option) => (
                      <button
                        type="button"
                        className={`fridge-sort-option${sortType === option.value ? ' is-active' : ''}`}
                        role="menuitemradio"
                        aria-checked={sortType === option.value}
                        key={option.value}
                        onClick={() => {
                          setSortType(option.value)
                          setIsSortMenuOpen(false)
                        }}
                      >
                        <span>{option.label}</span>
                        {sortType === option.value ? <span aria-hidden="true">✓</span> : null}
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
            </div>
            </div>
          ) : null}

          <div className="fridge-card-grid">
            {ingredients.length === 0 ? (
              <div className="fridge-empty-state">
                <ImageSlot className="fridge-empty-state__image" src={imagePutting} />
                <h3>{isLoggedIn ? '냉장고가 비어 있어요.' : '로그인하고 냉장고를 채워주세요!'}</h3>
                <p>
                  {isLoggedIn
                    ? '첫 재료를 등록하고 소비기한 관리를 시작해보세요.'
                    : '로그인 후 재료를 등록하고 소비기한을 관리할 수 있어요.'}
                </p>
                <button type="button" onClick={isLoggedIn ? openAddModal : () => navigate('/login')}>
                  {isLoggedIn ? '+ 첫 재료 추가하기' : '로그인하기'}
                </button>
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
                      <ImageSlot
                        className="fridge-item__image"
                        src={getIngredientImageUrl(ingredientImageCatalog, item.name, item.category)}
                      />
                    </div>
                    <div className="fridge-item__body">
                      <div className="fridge-item__title">
                      <h2 className={getFridgeNameClass(item.name)} title={item.name}>
                        {item.name}
                      </h2>
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
                          <dd className="fridge-dday-wrapper">
                            <span className="fridge-dday-copy">
                              <span className={item.is_expired ? 'fridge-dday-expired' : item.is_expiring_soon ? 'fridge-dday-urgent' : 'fridge-dday-normal'}>
                                {getDdayLabel(item)}
                              </span>
                              {item.expiration_date ? <small className="fridge-dday-date">· {item.expiration_date.replace(/-/g, '.')}</small> : null}
                            </span>
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

                {isLoggedIn ? (
                  <article className="fridge-add-card">
                    <ImageSlot className="fridge-add-card__image" src={imageAlarm} />
                    <strong>더 많은 재료를 추가해보세요.</strong>
                    <button type="button" onClick={openAddModal}>+ 재료 추가</button>
                  </article>
                ) : null}
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

      {completionRecipe && (
        <div className="fridge-modal-overlay">
          <div className="fridge-modal-content fridge-consumption-modal" onClick={(event) => event.stopPropagation()}>
            <div className="fridge-modal-header">
              <h2>재료 소모 확인</h2>
              <button type="button" onClick={closeCompletionFlow} aria-label="닫기">×</button>
            </div>
            <div className="fridge-modal-body">
              <p className="fridge-consumption-intro">
                <strong>{completionRecipe.title}</strong> 요리 후 냉장고에 남은 수량을 입력해주세요.
              </p>
              {isCompletionLoading ? (
                <p className="fridge-consumption-state">보유 재료를 확인하고 있어요.</p>
              ) : completionError ? (
                <p className="fridge-consumption-state is-error" role="alert">{completionError}</p>
              ) : completionItems.length === 0 ? (
                <p className="fridge-consumption-state">수정할 보유 재료가 없어요. 완료하면 저장된 레시피만 정리됩니다.</p>
              ) : (
                <div className="fridge-consumption-list">
                  {completionItems.map((item) => (
                    <div className="fridge-consumption-item" key={item.id}>
                      <div>
                        <strong>{item.name}</strong>
                        <span>현재 {Number(item.quantity)}{item.unit}</span>
                      </div>
                      <label>
                        <span>남은 수량</span>
                        <input
                          type="number"
                          min="0"
                          max={item.quantity}
                          step="0.5"
                          value={completionQuantities[item.id] ?? ''}
                          aria-label={`${item.name} 남은 수량`}
                          onChange={(event) => setCompletionQuantities((quantities) => ({
                            ...quantities,
                            [item.id]: event.target.value,
                          }))}
                        />
                        <b>{item.unit}</b>
                      </label>
                    </div>
                  ))}
                </div>
              )}
            </div>
            <div className="fridge-modal-footer">
              <button type="button" className="btn-cancel" onClick={closeCompletionFlow}>취소</button>
              <button
                type="button"
                className="btn-submit"
                disabled={isCompletionLoading || Boolean(completionError) || isCompletionSubmitting}
                onClick={completeRecipeConsumption}
              >
                {isCompletionSubmitting ? '반영 중...' : '수정 완료'}
              </button>
            </div>
          </div>
        </div>
      )}

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
      {isLoggedIn ? (
        <button className="fridge-floating-add" type="button" aria-label="재료 추가" onClick={openAddModal}>+</button>
      ) : null}
    </section>
  )
}

export default Fridge
