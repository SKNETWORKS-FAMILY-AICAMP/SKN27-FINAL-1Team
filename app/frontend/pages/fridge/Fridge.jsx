import React, { useState, useEffect } from 'react'
import './Fridge.css'

import iconEgg from '../../assets/extracted/icons/icon_egg.png'
import iconMushroom from '../../assets/extracted/icons/icon_mushroom.png'
import iconOnion from '../../assets/extracted/icons/icon_onion.png'
import iconReceipt from '../../assets/extracted/icons/icon_receipt.png'
import iconRefrigerator from '../../assets/extracted/icons/icon_refrigerator.png'
import imageAlarm from '../../assets/extracted/images/image_alarm.png'
import imagePutting from '../../assets/extracted/images/image_putting.png'

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
  const [formData, setFormData] = useState(initialFormData)
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

  // 재료 등록 API 호출
  const handleAddIngredient = async () => {
    if (!formData.name.trim()) {
      alert('재료 이름을 입력해주세요.')
      return
    }

    // 빈 값이면 백엔드로 굳이 빈 문자열 전송하지 않고 undefined 또는 null 처리하거나
    // 백엔드가 빈 문자열을 허용한다면 그대로 전송 (Pydantic이 None 변환 처리 가능성)
    const payload = {
      ...formData,
      quantity: Math.round(Number(formData.quantity) * 10) / 10
    }
    if (!payload.expiration_date) {
      payload.expiration_date = null // null 처리
    }

    try {
      const token = localStorage.getItem('bobbeori-token')
      const response = await fetch(`${apiUrl}/api/v1/inventory`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify(payload)
      })

      if (response.ok) {
        setFormData(initialFormData) // 폼 초기화
        setIsModalOpen(false) // 모달 닫기
        fetchFridgeData() // 데이터 리로드
      } else {
        const errData = await response.json()
        alert(`재료 등록에 실패했습니다: ${errData.detail || '알 수 없는 에러'}`)
      }
    } catch (err) {
      console.error(err)
      alert('서버 통신 중 오류가 발생했습니다.')
    }
  }

  const closeModal = () => {
    setIsModalOpen(false)
    setFormData(initialFormData)
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
            <button className="fridge-soft-button" type="button">
              통계 보기
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
                <button type="button" onClick={() => setIsModalOpen(true)}>+ 첫 재료 추가하기</button>
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
                      <button type="button">수정</button>
                      <button type="button">소비</button>
                      <button type="button">삭제</button>
                    </div>
                  </article>
                  )
                })}

                <article className="fridge-add-card" onClick={() => setIsModalOpen(true)} style={{cursor: 'pointer'}}>
                  <ImageSlot className="fridge-add-card__image" src={imageAlarm} />
                  <strong>더 많은 재료를 추가해보세요!</strong>
                  <button type="button">+ 재료 추가</button>
                </article>
              </>
            )}
          </div>
        </main>
      </div>

      <section className="fridge-bottom-tip">
        <strong>알뜰 팁</strong>
        <span>소비 임박 재료로 맛있는 레시피를 추천받아 보세요!</span>
        <button type="button">레시피 추천 받기</button>
        <ImageSlot className="fridge-bottom-tip__image" src={imageAlarm} />
      </section>

      <button className="fridge-floating-add" type="button" aria-label="재료 추가" onClick={() => setIsModalOpen(true)}>
        +
      </button>

      {/* 재료 추가 모달 뼈대 및 폼 */}
      {isModalOpen && (
        <div className="fridge-modal-overlay">
          <div className="fridge-modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="fridge-modal-header">
              <h3>재료 직접 추가</h3>
              <button onClick={closeModal}>✕</button>
            </div>
            <div className="fridge-modal-body">
              <div className="fridge-form-group">
                <label>재료명 <span style={{color:'red'}}>*</span></label>
                <input type="text" name="name" placeholder="예) 양파, 대파, 우유" value={formData.name} onChange={handleFormChange} />
              </div>
              <div className="fridge-form-row">
                <div className="fridge-form-group">
                  <label>카테고리</label>
                  <select name="category" value={formData.category} onChange={handleFormChange}>
                    <option value="채소">채소</option>
                    <option value="과일">과일</option>
                    <option value="육류">육류</option>
                    <option value="수산물">수산물</option>
                    <option value="유제품">유제품</option>
                    <option value="가공식품">가공식품</option>
                    <option value="기타">기타</option>
                  </select>
                </div>
                <div className="fridge-form-group">
                  <label>보관 위치</label>
                  <select name="storage_method" value={formData.storage_method} onChange={handleFormChange}>
                    <option value="냉장">냉장</option>
                    <option value="냉동">냉동</option>
                    <option value="실온">실온</option>
                  </select>
                </div>
              </div>
              <div className="fridge-form-row">
                <div className="fridge-form-group">
                  <label>수량 <small style={{color:'#8b673e', fontWeight: 'normal'}}>(반 개는 0.5)</small></label>
                  <input type="number" name="quantity" min="0.5" step="0.5" value={formData.quantity} onChange={handleFormChange} />
                </div>
                <div className="fridge-form-group">
                  <label>단위</label>
                  <select name="unit" value={formData.unit} onChange={handleFormChange}>
                    <option value="개">개</option>
                    <option value="g">g (그램)</option>
                    <option value="ml">ml (미리리터)</option>
                    <option value="봉">봉</option>
                    <option value="단">단</option>
                  </select>
                </div>
              </div>
              <div className="fridge-form-group">
                <label>유통기한(소비기한) <small style={{color:'#8b673e', fontWeight: 'normal'}}>(미입력시 자동 계산)</small></label>
                <input type="date" name="expiration_date" value={formData.expiration_date} onChange={handleFormChange} />
              </div>
            </div>
            <div className="fridge-modal-footer">
              <button className="btn-cancel" onClick={closeModal}>취소</button>
              <button className="btn-submit" onClick={handleAddIngredient}>등록하기</button>
            </div>
          </div>
        </div>
      )}
    </section>
  )
}

export default Fridge
