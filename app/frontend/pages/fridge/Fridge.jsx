import React, { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import './Fridge.css'

import iconEgg from '../../assets/extracted/icons/icon_egg.png'
import iconMushroom from '../../assets/extracted/icons/icon_mushroom.png'
import iconOnion from '../../assets/extracted/icons/icon_onion.png'
import iconReceipt from '../../assets/extracted/icons/icon_receipt.png'
import imageAlarm from '../../assets/extracted/images/image_alarm.png'
import imagePutting from '../../assets/extracted/images/image_putting.png'
import { useAppDialog } from '../../components/AppDialog.jsx'
import IngredientModal from '../../components/modals/IngredientModal'
import ConfirmModal from '../../components/modals/ConfirmModal'
import { demoIngredients, initialIngredientFormData as initialFormData } from '../../mock/fridgeMock.js'

const FILTER_TYPES = [
  { label: '전체', tone: '' },
  { label: '냉장', tone: 'cold' },
  { label: '냉동', tone: 'frozen' },
  { label: '소비 임박', tone: 'soon' },
]

function ImageSlot({ src, alt = '', className = '' }) {
  return (
    <span className={`fridge-image-slot ${src ? 'is-filled' : ''} ${className}`}>
      {src ? <img src={src} alt={alt} /> : null}
    </span>
  )
}

function getIngredientIcon(name = '') {
  if (name.includes('양파')) return iconOnion
  if (name.includes('버섯')) return iconMushroom
  if (name.includes('계란') || name.includes('달걀')) return iconEgg
  return null
}

function buildSummary(items) {
  return {
    total: items.length,
    expiring_soon: items.filter((item) => item.is_expiring_soon).length,
    storage: {
      냉장: items.filter((item) => item.storage_method === '냉장').length,
      냉동: items.filter((item) => item.storage_method === '냉동').length,
      실온: items.filter((item) => item.storage_method === '실온').length,
      기타: items.filter((item) => !['냉장', '냉동', '실온'].includes(item.storage_method)).length,
    },
  }
}

function getDdayLabel(item) {
  if (item.d_day !== null && item.d_day !== undefined) {
    if (item.d_day > 0) return `D-${item.d_day}`
    if (item.d_day === 0) return 'D-Day'
    return `D+${Math.abs(item.d_day)} 지남`
  }

  return '-'
}

function Fridge() {
  const navigate = useNavigate()
  const { dialogNode, showAlert } = useAppDialog()
  const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000'
  const [ingredients, setIngredients] = useState(demoIngredients)
  const [summary, setSummary] = useState(buildSummary(demoIngredients))
  const [activeFilter, setActiveFilter] = useState('전체')
  const [searchQuery, setSearchQuery] = useState('')
  const [viewMode, setViewMode] = useState('grid')
  const [sortType, setSortType] = useState('latest')
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [formData, setFormData] = useState(initialFormData)
  const [confirmModal, setConfirmModal] = useState({
    isOpen: false,
    title: '',
    message: '',
    onConfirm: null,
  })
  const [stockedCount, setStockedCount] = useState(() => {
    if (typeof window === 'undefined') {
      return 0
    }

    return Number(window.localStorage.getItem('bobbeori-last-stocked-count') ?? 0)
  })

  const hasToken = () => Boolean(window.localStorage.getItem('bobbeori-token'))

  const fetchFridgeData = async () => {
    const token = window.localStorage.getItem('bobbeori-token')
    if (!token) {
      const nextSummary = buildSummary(ingredients)
      setSummary(nextSummary)
      return
    }

    try {
      const resIngredients = await fetch(`${apiUrl}/api/v1/inventory`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (resIngredients.ok) {
        const data = await resIngredients.json()
        setIngredients(data)
      }

      const resSummary = await fetch(`${apiUrl}/api/v1/inventory/summary`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (resSummary.ok) {
        const data = await resSummary.json()
        setSummary(data)
      }
    } catch (err) {
      console.error('냉장고 데이터 불러오기 오류:', err)
    }
  }

  useEffect(() => {
    fetchFridgeData()
  }, [])

  useEffect(() => {
    if (!hasToken()) {
      setSummary(buildSummary(ingredients))
    }
  }, [ingredients])

  const filterCounts = useMemo(
    () => ({
      전체: summary.total,
      냉장: summary.storage?.냉장 || 0,
      냉동: summary.storage?.냉동 || 0,
      '소비 임박': summary.expiring_soon,
    }),
    [summary],
  )

  const sortedIngredients = useMemo(() => {
    const normalizedQuery = searchQuery.trim().toLowerCase()
    const filteredIngredients = ingredients.filter((item) => {
      const matchesCategory =
        activeFilter === '전체' ||
        (activeFilter === '냉장' && item.storage_method === '냉장') ||
        (activeFilter === '냉동' && item.storage_method === '냉동') ||
        (activeFilter === '소비 임박' && item.is_expiring_soon)
      const matchesSearch =
        normalizedQuery === '' ||
        item.name.toLowerCase().includes(normalizedQuery) ||
        (item.category && item.category.toLowerCase().includes(normalizedQuery))

      return matchesCategory && matchesSearch
    })

    return [...filteredIngredients].sort((a, b) => {
      if (sortType === 'oldest') {
        return a.id - b.id
      }

      if (sortType === 'expiry') {
        const aDay = a.d_day ?? 999
        const bDay = b.d_day ?? 999
        return aDay - bDay
      }

      return b.id - a.id
    })
  }, [activeFilter, ingredients, searchQuery, sortType])

  const getSortLabel = () => {
    if (sortType === 'oldest') return '등록일 오래된순'
    if (sortType === 'expiry') return '소비기한 임박순'
    return '등록일 최신순'
  }

  const toggleSort = () => {
    setSortType((prev) => {
      if (prev === 'latest') return 'oldest'
      if (prev === 'oldest') return 'expiry'
      return 'latest'
    })
  }

  const handleFormChange = (event) => {
    const { name, value } = event.target
    setFormData((prev) => ({ ...prev, [name]: value }))
  }

  const closeModal = () => {
    setIsModalOpen(false)
    setFormData(initialFormData)
    setEditingId(null)
  }

  const openAddModal = () => {
    setFormData(initialFormData)
    setEditingId(null)
    setIsModalOpen(true)
  }

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

  const handleSubmitIngredient = async () => {
    if (!formData.name.trim()) {
      await showAlert('재료 이름을 입력해주세요.', {
        title: '입력 확인',
      })
      return
    }

    const payload = {
      ...formData,
      quantity: Math.round(Number(formData.quantity) * 10) / 10,
      expiration_date: formData.expiration_date || null,
    }

    if (!hasToken()) {
      setIngredients((prev) => {
        if (editingId !== null) {
          return prev.map((item) => (item.id === editingId ? { ...item, ...payload } : item))
        }

        return [
          {
            ...payload,
            id: Date.now(),
            d_day: payload.expiration_date ? 7 : null,
            is_expiring_soon: false,
          },
          ...prev,
        ]
      })
      setActiveFilter('전체')
      setSearchQuery('')
      closeModal()
      return
    }

    try {
      const token = window.localStorage.getItem('bobbeori-token')
      const isEditing = editingId !== null
      const url = isEditing
        ? `${apiUrl}/api/v1/inventory/${editingId}`
        : `${apiUrl}/api/v1/inventory`

      const response = await fetch(url, {
        method: isEditing ? 'PUT' : 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(payload),
      })

      if (response.ok) {
        closeModal()
        fetchFridgeData()
      } else {
        const errData = await response.json()
        await showAlert(`재료 저장에 실패했습니다: ${errData.detail || '알 수 없는 에러'}`, {
          title: '저장 실패',
        })
      }
    } catch (err) {
      console.error(err)
      await showAlert('서버 통신 중 오류가 발생했습니다.', {
        title: '서버 오류',
      })
    }
  }

  const executeDelete = async (id) => {
    if (!hasToken()) {
      setIngredients((prev) => prev.filter((item) => item.id !== id))
      setConfirmModal({ isOpen: false, title: '', message: '', onConfirm: null })
      return
    }

    try {
      const token = window.localStorage.getItem('bobbeori-token')
      const response = await fetch(`${apiUrl}/api/v1/inventory/${id}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      })

      if (response.ok) {
        setConfirmModal({ isOpen: false, title: '', message: '', onConfirm: null })
        fetchFridgeData()
      } else {
        await showAlert('삭제에 실패했습니다.', {
          title: '삭제 실패',
        })
      }
    } catch (err) {
      console.error(err)
      await showAlert('서버 오류로 삭제하지 못했습니다.', {
        title: '서버 오류',
      })
    }
  }

  const handleDeleteClick = (id, name) => {
    setConfirmModal({
      isOpen: true,
      title: '재료 삭제',
      message: (
        <>
          <span style={{ color: 'var(--figma-coral)', fontWeight: 'bold', fontSize: '18px' }}>{name}</span>을(를)<br />
          냉장고에서 완전히 삭제하시겠습니까?
        </>
      ),
      onConfirm: () => executeDelete(id),
    })
  }

  const handleConsumeClick = async (item) => {
    if (Number(item.quantity) <= 1) {
      setConfirmModal({
        isOpen: true,
        title: '모두 소비',
        message: (
          <>
            <span style={{ color: 'var(--figma-coral)', fontWeight: 'bold', fontSize: '18px' }}>{item.name}</span>의 남은 수량이 1개 이하입니다.<br />
            모두 소비 처리하고 삭제할까요?
          </>
        ),
        onConfirm: () => executeDelete(item.id),
      })
      return
    }

    const newQuantity = Math.round((Number(item.quantity) - 1) * 10) / 10
    const payload = {
      name: item.name,
      category: item.category,
      storage_method: item.storage_method,
      quantity: newQuantity,
      unit: item.unit,
      purchase_date: item.purchase_date,
      expiration_date: item.expiration_date,
    }

    if (!hasToken()) {
      setIngredients((prev) =>
        prev.map((target) => (target.id === item.id ? { ...target, quantity: newQuantity } : target)),
      )
      return
    }

    try {
      const token = window.localStorage.getItem('bobbeori-token')
      const response = await fetch(`${apiUrl}/api/v1/inventory/${item.id}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(payload),
      })

      if (response.ok) {
        fetchFridgeData()
      } else {
        await showAlert('소비 처리에 실패했습니다.', {
          title: '소비 처리 실패',
        })
      }
    } catch (err) {
      console.error(err)
      await showAlert('서버 오류로 소비 처리하지 못했습니다.', {
        title: '서버 오류',
      })
    }
  }

  const clearStockNotice = () => {
    setStockedCount(0)
    window.localStorage.removeItem('bobbeori-last-stocked-count')
  }

  return (
    <section className="fridge-page" aria-labelledby="fridge-title">
      <div className="fridge-hero">
        <div className="fridge-hero__copy">
          <h1 id="fridge-title">냉장고 재료 관리</h1>
          <p>우리 집 재료를 한눈에 관리하고, 알뜰하게 소비해요!</p>
          {stockedCount > 0 ? (
            <div className="fridge-stock-notice">
              <span>영수증에서 {stockedCount}개 재료가 입고됐어요.</span>
              <button type="button" onClick={clearStockNotice}>확인</button>
            </div>
          ) : null}
          <label className="fridge-search" aria-label="재료명 검색">
            <span aria-hidden="true" />
            <input
              type="search"
              placeholder="재료명으로 검색해보세요"
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
            />
          </label>
        </div>

        <div className="fridge-hero__actions">
          <button className="fridge-hero-card" type="button" onClick={() => navigate('/receipt-ocr')}>
            <div>
              <strong>영수증 OCR 입고</strong>
              <p>영수증 촬영으로 재료를 한 번에 등록해요</p>
            </div>
            <ImageSlot className="fridge-hero-card__image" src={iconReceipt} />
          </button>
          <button className="fridge-hero-card fridge-hero-card--add" type="button" onClick={openAddModal}>
            <div>
              <strong>+ 재료 추가</strong>
              <p>직접 입력해서 재료를 추가해요</p>
            </div>
            <ImageSlot className="fridge-hero-card__image" src={imageAlarm} />
          </button>
        </div>

        <ImageSlot className="fridge-hero__image" src={imagePutting} />
      </div>

      <div className="fridge-layout">
        <main className="fridge-main">
          <div className="fridge-toolbar">
            <div className="fridge-filters" aria-label="재료 상태 필터">
              {FILTER_TYPES.map((filter) => (
                <button
                  className={[
                    'fridge-filter',
                    activeFilter === filter.label ? 'is-active' : '',
                    filter.tone ? `is-${filter.tone}` : '',
                  ]
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
              <button type="button" onClick={toggleSort}>
                {getSortLabel()}
              </button>
              <button
                className={viewMode === 'grid' ? 'is-active' : ''}
                type="button"
                aria-label="그리드 보기"
                onClick={() => setViewMode('grid')}
              >
                <span />
              </button>
              <button
                className={viewMode === 'list' ? 'is-active' : ''}
                type="button"
                aria-label="리스트 보기"
                onClick={() => setViewMode('list')}
              >
                <span />
              </button>
            </div>
          </div>

          <div className={viewMode === 'list' ? 'fridge-card-grid is-list' : 'fridge-card-grid'}>
            {ingredients.length === 0 ? (
              <div className="fridge-empty-state">
                <ImageSlot className="fridge-empty-state__image" src={imagePutting} />
                <h3>냉장고가 텅 비었어요!</h3>
                <p>첫 식재료를 등록하고 관리해보세요.</p>
                <button type="button" onClick={openAddModal}>+ 첫 재료 추가하기</button>
              </div>
            ) : sortedIngredients.length === 0 ? (
              <div className="fridge-empty-state">
                <h3>해당 조건의 재료가 없습니다.</h3>
                <button type="button" onClick={() => setActiveFilter('전체')}>전체 보기</button>
              </div>
            ) : (
              <>
                {sortedIngredients.map((item) => (
                  <article className={`fridge-item ${item.is_expiring_soon ? 'is-urgent' : ''}`} key={item.id}>
                    <ImageSlot className="fridge-item__image" src={getIngredientIcon(item.name)} />
                    <div className="fridge-item__body">
                      <div className="fridge-item__title">
                        <h2>{item.name}</h2>
                        <span className={item.is_expiring_soon ? 'is-urgent' : ''}>
                          {item.storage_method}
                        </span>
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
                          <dd className={item.is_expiring_soon ? 'fridge-dday-urgent' : 'fridge-dday-normal'}>
                            {getDdayLabel(item)}
                            {item.expiration_date ? <small className="fridge-dday-date">({item.expiration_date})</small> : null}
                          </dd>
                        </div>
                      </dl>
                    </div>
                    <div className="fridge-item__actions">
                      <button type="button" onClick={() => openEditModal(item)}>수정</button>
                      <button type="button" onClick={() => handleConsumeClick(item)}>소비</button>
                      <button type="button" onClick={() => handleDeleteClick(item.id, item.name)}>삭제</button>
                    </div>
                  </article>
                ))}

                <article className="fridge-add-card">
                  <ImageSlot className="fridge-add-card__image" src={imageAlarm} />
                  <strong>더 많은 재료를 추가해보세요!</strong>
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
      />

      <ConfirmModal
        isOpen={confirmModal.isOpen}
        title={confirmModal.title}
        message={confirmModal.message}
        onConfirm={confirmModal.onConfirm}
        onClose={() => setConfirmModal({ ...confirmModal, isOpen: false })}
      />
      {dialogNode}

      <section className="fridge-bottom-tip">
        <strong>알뜰 팁</strong>
        <span>소비 임박 재료로 맛있는 레시피를 추천받아 보세요!</span>
        <button type="button" onClick={() => navigate('/recipe-fridge')}>레시피 추천 받기</button>
        <ImageSlot className="fridge-bottom-tip__image" src={imageAlarm} />
      </section>

      <button className="fridge-floating-add" type="button" aria-label="재료 추가" onClick={openAddModal}>
        +
      </button>
    </section>
  )
}

export default Fridge
