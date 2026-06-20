import React, { useState, useEffect } from 'react'
import './Fridge.css'

import iconEgg from '../../assets/extracted/icons/icon_egg.png'
import iconMushroom from '../../assets/extracted/icons/icon_mushroom.png'
import iconOnion from '../../assets/extracted/icons/icon_onion.png'
import iconReceipt from '../../assets/extracted/icons/icon_receipt.png'
import iconRefrigerator from '../../assets/extracted/icons/icon_refrigerator.png'
import imageAlarm from '../../assets/extracted/images/image_alarm.png'
import imagePutting from '../../assets/extracted/images/image_putting.png'

import IngredientModal from '../../components/modals/IngredientModal'
import ConfirmModal from '../../components/modals/ConfirmModal'
import StatsModal from '../../components/modals/StatsModal'

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

function Fridge() {
  const initialFormData = {
    name: '',
    category: '채소',
    quantity: 1,
    unit: '개',
    storage_method: '냉장',
    expiration_date: ''
  }

  const [ingredients, setIngredients] = useState([])
  const [summary, setSummary] = useState({
    total: 0,
    expiring_soon: 0,
    storage: { 냉장: 0, 냉동: 0, 실온: 0, 기타: 0 }
  })
  const [activeFilter, setActiveFilter] = useState('전체')
  const [searchQuery, setSearchQuery] = useState('')
  const [sortType, setSortType] = useState('latest') // 'latest', 'oldest'
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [formData, setFormData] = useState(initialFormData)
  const [isStatsOpen, setIsStatsOpen] = useState(false)
  const [confirmModal, setConfirmModal] = useState({
    isOpen: false,
    title: '',
    message: '',
    onConfirm: null
  })
  const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000'

  useEffect(() => {
    fetchFridgeData()
  }, [])

  const fetchFridgeData = async () => {
    try {
      const token = localStorage.getItem('bobbeori-token')
      if (!token) return // 토큰이 없으면 로그인 페이지로 이동하는 로직은 추후 보완 가능

      const resIngredients = await fetch(`${apiUrl}/api/v1/inventory`, {
        headers: { Authorization: `Bearer ${token}` }
      })
      if (resIngredients.ok) {
        const data = await resIngredients.json()
        setIngredients(data)
      }

      const resSummary = await fetch(`${apiUrl}/api/v1/inventory/summary`, {
        headers: { Authorization: `Bearer ${token}` }
      })
      if (resSummary.ok) {
        const data = await resSummary.json()
        setSummary(data)
      }
    } catch (err) {
      console.error('냉장고 데이터 불러오기 오류:', err)
    }
  }

  // 필터 로직
  const filteredIngredients = ingredients.filter((item) => {
    // 1. 카테고리 필터
    let passCategory = true
    if (activeFilter === '냉장') passCategory = item.storage_method === '냉장'
    else if (activeFilter === '냉동') passCategory = item.storage_method === '냉동'
    else if (activeFilter === '소비 임박') passCategory = item.is_expiring_soon
    
    // 2. 검색어 필터
    let passSearch = true
    if (searchQuery.trim() !== '') {
      // 이름이나 카테고리로 검색 가능
      passSearch = item.name.includes(searchQuery.trim()) || 
                   (item.category && item.category.includes(searchQuery.trim()))
    }

    return passCategory && passSearch
  })

  // 정렬 로직 적용
  const sortedIngredients = [...filteredIngredients].sort((a, b) => {
    if (sortType === 'latest') {
      return b.id - a.id // 최신 등록순 (ID가 클수록 최근)
    } else if (sortType === 'oldest') {
      return a.id - b.id // 오래된 순
    }
    return 0
  })

  const toggleSort = () => {
    if (sortType === 'latest') setSortType('oldest')
    else setSortType('latest')
  }

  const getSortLabel = () => {
    if (sortType === 'latest') return '등록일 최신순'
    return '등록일 오래된순'
  }

  // 폼 입력 핸들러
  const handleFormChange = (e) => {
    const { name, value } = e.target
    setFormData(prev => ({ ...prev, [name]: value }))
  }

  // 폼 제출 핸들러 (추가 및 수정 공통)
  const handleSubmitIngredient = async () => {
    if (!formData.name.trim()) {
      alert('재료 이름을 입력해주세요.')
      return
    }

    const payload = {
      ...formData,
      quantity: Math.round(Number(formData.quantity) * 10) / 10
    }
    if (!payload.expiration_date) {
      payload.expiration_date = null
    }

    try {
      const token = localStorage.getItem('bobbeori-token')
      const isEditing = editingId !== null
      const url = isEditing 
        ? `${apiUrl}/api/v1/inventory/${editingId}`
        : `${apiUrl}/api/v1/inventory`
      
      const response = await fetch(url, {
        method: isEditing ? 'PUT' : 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify(payload)
      })

      if (response.ok) {
        closeModal()
        fetchFridgeData() // 데이터 리로드
      } else {
        const errData = await response.json()
        alert(`재료 저장에 실패했습니다: ${errData.detail || '알 수 없는 에러'}`)
      }
    } catch (err) {
      console.error(err)
      alert('서버 통신 중 오류가 발생했습니다.')
    }
  }

  // 삭제 핸들러 (실제 API 호출)
  const executeDelete = async (id) => {
    try {
      const token = localStorage.getItem('bobbeori-token')
      const response = await fetch(`${apiUrl}/api/v1/inventory/${id}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` }
      })

      if (response.ok) {
        setConfirmModal({ isOpen: false, title: '', message: '', onConfirm: null })
        fetchFridgeData()
      } else {
        alert('삭제에 실패했습니다.')
      }
    } catch (err) {
      console.error(err)
      alert('서버 오류로 삭제하지 못했습니다.')
    }
  }

  // 삭제 컨펌 모달 띄우기
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
      onConfirm: () => executeDelete(id)
    })
  }

  // 소비 핸들러 (1개 차감)
  const handleConsumeClick = async (item) => {
    // 1개 이하일 때 소비를 누르면 컨펌 모달 띄우기
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
        onConfirm: () => executeDelete(item.id)
      })
      return
    }

    // 1개 차감 로직
    const newQuantity = Math.round((Number(item.quantity) - 1) * 10) / 10
    const payload = {
      name: item.name,
      category: item.category,
      storage_method: item.storage_method,
      quantity: newQuantity,
      unit: item.unit,
      purchase_date: item.purchase_date,
      expiration_date: item.expiration_date
    }

    try {
      const token = localStorage.getItem('bobbeori-token')
      const response = await fetch(`${apiUrl}/api/v1/inventory/${item.id}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify(payload)
      })

      if (response.ok) {
        fetchFridgeData()
      } else {
        alert('소비 처리에 실패했습니다.')
      }
    } catch (err) {
      console.error(err)
      alert('서버 오류로 소비 처리하지 못했습니다.')
    }
  }

  // 수정 버튼 클릭 핸들러
  const openEditModal = (item) => {
    setFormData({
      name: item.name || '',
      category: item.category || '기타',
      storage_method: item.storage_method || '냉장',
      quantity: Number(item.quantity) || 1,
      unit: item.unit || '개',
      purchase_date: item.purchase_date || new Date().toISOString().split('T')[0],
      expiration_date: item.expiration_date || ''
    })
    setEditingId(item.id)
    setIsModalOpen(true)
  }

  const openAddModal = () => {
    setFormData(initialFormData)
    setEditingId(null)
    setIsModalOpen(true)
  }

  const closeModal = () => {
    setIsModalOpen(false)
    setFormData(initialFormData)
    setEditingId(null)
  }

  return (
    <section className="fridge-page" aria-labelledby="fridge-title">
      <div className="fridge-hero">
        <div className="fridge-hero__copy">
          <h1 id="fridge-title">냉장고 재료 관리</h1>
          <p>우리 집 재료를 한눈에 관리하고, 알뜰하게 소비해요!</p>
          <label className="fridge-search" aria-label="재료명 검색">
            <span aria-hidden="true" />
            <input 
              type="search" 
              placeholder="재료명으로 검색해보세요" 
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </label>
        </div>

        <div className="fridge-hero__actions">
          <button className="fridge-hero-card" type="button">
            <div>
              <strong>영수증 OCR 입고</strong>
              <p>영수증 촬영으로 재료를 한 번에 등록해요</p>
            </div>
            <ImageSlot className="fridge-hero-card__image" src={iconReceipt} />
          </button>
          <button className="fridge-hero-card fridge-hero-card--add" type="button" onClick={() => setIsModalOpen(true)}>
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
        <aside className="fridge-sidebar" aria-label="냉장고 요약">
          <section className="fridge-panel fridge-summary">
            <h2>요약 정보</h2>
            <dl>
              <div>
                <dt>전체 재료</dt>
                <dd>{summary.total}개</dd>
              </div>
              <div>
                <dt>냉장</dt>
                <dd>{summary.storage['냉장'] || 0}개</dd>
              </div>
              <div>
                <dt>냉동</dt>
                <dd>{summary.storage['냉동'] || 0}개</dd>
              </div>
              <div>
                <dt>실온</dt>
                <dd>{summary.storage['실온'] || 0}개</dd>
              </div>
              <div>
                <dt>소비 임박 (D-3↓)</dt>
                <dd>{summary.expiring_soon}개</dd>
              </div>
            </dl>
            <button 
              type="button" 
              onClick={() => setIsStatsOpen(true)}
              style={{ width: '100%', marginTop: '12px', padding: '8px', background: 'var(--figma-coral)', color: '#fff', border: 'none', borderRadius: '8px', cursor: 'pointer', fontWeight: 'bold' }}
            >
              상세 통계 보기
            </button>
          </section>

          <section className="fridge-panel fridge-quick">
            <h2>빠른 이동</h2>
            <ul>
              <li>
                소비 임박 재료 <strong>3</strong>
              </li>
              <li>최근 소비 내역</li>
              <li>자주 먹는 재료</li>
              <li>
                휴지통 <strong>2</strong>
              </li>
            </ul>
          </section>

          <section className="fridge-panel fridge-tip">
            <ImageSlot className="fridge-tip__image" src={imageAlarm} />
            <h2>오늘도 알뜰하게!</h2>
            <p>소비 임박 재료 {summary.expiring_soon}개가 있어요. 우선 소비해볼까요?</p>
          </section>
        </aside>

        <main className="fridge-main">
          <div className="fridge-toolbar">
            <div className="fridge-filters" aria-label="재료 상태 필터">
              {FILTER_TYPES.map((filter) => {
                let count = 0
                if (filter.label === '전체') count = summary.total
                else if (filter.label === '냉장') count = summary.storage['냉장'] || 0
                else if (filter.label === '냉동') count = summary.storage['냉동'] || 0
                else if (filter.label === '소비 임박') count = summary.expiring_soon

                return (
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
                    {filter.label} ({count})
                  </button>
                )
              })}
            </div>

            <div className="fridge-view-controls">
              <button type="button" onClick={toggleSort} style={{ width: '130px' }}>
                {getSortLabel()}
              </button>
              <button className="is-active" type="button" aria-label="그리드 보기">
                <span />
              </button>
              <button type="button" aria-label="리스트 보기">
                <span />
              </button>
            </div>
          </div>

          <div className="fridge-card-grid">
            {ingredients.length === 0 ? (
              <div className="fridge-empty-state">
                <ImageSlot className="fridge-empty-state__image" src={imagePutting} />
                <h3>냉장고가 텅 비었어요!</h3>
                <p>첫 식재료를 등록하고 관리해보세요.</p>
                <button type="button" onClick={openAddModal}>+ 첫 재료 추가하기</button>
              </div>
            ) : filteredIngredients.length === 0 ? (
              <div className="fridge-empty-state">
                <h3>해당 조건의 재료가 없습니다.</h3>
              </div>
            ) : (
              <>
                {sortedIngredients.map((item) => {
                  let mappedIcon = null
                  const nameStr = item.name || ''
                  if (nameStr.includes('양파')) mappedIcon = iconOnion
                  else if (nameStr.includes('버섯')) mappedIcon = iconMushroom
                  else if (nameStr.includes('계란') || nameStr.includes('달걀')) mappedIcon = iconEgg

                  return (
                    <article className={`fridge-item ${item.is_expiring_soon ? 'is-urgent' : ''}`} key={item.id}>
                      <ImageSlot className="fridge-item__image" src={mappedIcon} />
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
                            {item.d_day !== null && item.d_day !== undefined 
                              ? (item.d_day > 0 ? `D-${item.d_day}` : item.d_day === 0 ? 'D-Day' : `D+${Math.abs(item.d_day)} 지남`) 
                              : '-'}
                            <small className="fridge-dday-date">({item.expiration_date})</small>
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
                  )
                })}

                <article className="fridge-add-card" onClick={openAddModal} style={{cursor: 'pointer'}}>
                  <ImageSlot className="fridge-add-card__image" src={imageAlarm} />
                  <strong>더 많은 재료를 추가해보세요!</strong>
                  <button type="button">+ 재료 추가</button>
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

      <StatsModal 
        isOpen={isStatsOpen}
        onClose={() => setIsStatsOpen(false)}
        summary={summary}
      />

      <section className="fridge-bottom-tip">
        <strong>알뜰 팁</strong>
        <span>소비 임박 재료로 맛있는 레시피를 추천받아 보세요!</span>
        <button type="button">레시피 추천 받기</button>
        <ImageSlot className="fridge-bottom-tip__image" src={imageAlarm} />
      </section>

      <button className="fridge-floating-add" type="button" aria-label="재료 추가" onClick={() => setIsModalOpen(true)}>
        +
      </button>
    </section>
  )
}

export default Fridge
