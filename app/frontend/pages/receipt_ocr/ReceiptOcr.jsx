import React, { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import './ReceiptOcr.css'

import iconEgg from '../../assets/extracted/icons/icon_egg.png'
import iconMushroom from '../../assets/extracted/icons/icon_mushroom.png'
import iconOnion from '../../assets/extracted/icons/icon_onion.png'
import iconReceipt from '../../assets/extracted/icons/icon_receipt.png'
import iconRefrigerator from '../../assets/extracted/icons/icon_refrigerator.png'
import imageReceipt from '../../assets/extracted/images/image_receipt registration.png'

const steps = ['업로드/촬영', 'OCR 분석', '품목 추출', '후보 확인', '표준명 매칭', '냉장고 입고']

const rows = [
  { raw: '국산 대파', name: '대파', quantity: '1단', price: '2,000원' },
  { raw: '특란 계란', name: '계란', quantity: '10개', price: '1,980원', image: iconEgg },
  { raw: '부침두부', name: '두부', quantity: '1모', price: '2,300원' },
  { raw: '양파', name: '양파', quantity: '2개', price: '1,280원', image: iconOnion },
  { raw: '버섯 모둠', name: '버섯', quantity: '1팩', price: '1,600원', image: iconMushroom },
  { raw: '맛김치', name: '김치', quantity: '1통', price: '3,400원', review: true },
]

function ImageSlot({ src, alt = '', className = '' }) {
  return (
    <span className={`receipt-image-slot ${src ? 'is-filled' : ''} ${className}`}>
      {src ? <img src={src} alt={alt} /> : null}
    </span>
  )
}

function ReceiptOcr() {
  const navigate = useNavigate()
  const flowTimersRef = useRef([])
  const [activeStep, setActiveStep] = useState(1)
  const [detectedRows, setDetectedRows] = useState(rows)
  const [receiptSource, setReceiptSource] = useState('샘플 영수증')
  const [isProcessing, setIsProcessing] = useState(false)

  const mappedCount = detectedRows.filter((row) => !row.review).length
  const reviewCount = detectedRows.length - mappedCount
  const currentSummary = [
    { label: '인식 품목', value: `${detectedRows.length}개` },
    { label: '자동 매핑', value: `${mappedCount}개` },
    { label: '검토 필요', value: `${reviewCount}개` },
  ]
  const progressPercent = Math.round(((activeStep + 1) / steps.length) * 100)
  const currentStepLabel = steps[activeStep]
  const isReadyToStock = activeStep >= steps.length - 1

  const progressDescriptions = [
    '영수증을 올리거나 촬영하면 분석을 시작할 수 있어요.',
    isProcessing ? `${receiptSource} 기준으로 품목과 가격을 읽는 중이에요.` : `${receiptSource} 기준으로 품목과 가격을 읽었어요.`,
    `${detectedRows.length}개 품목을 장보기 재료 후보로 추출했어요.`,
    reviewCount ? `${reviewCount}개 후보는 이름 확인이 필요해요.` : '모든 후보가 자동으로 확인됐어요.',
    reviewCount ? '검토 필요 품목을 확인하면 입고할 수 있어요.' : '표준 재료명 매칭이 끝났어요.',
    `총 ${detectedRows.length}개 재료를 냉장고에 입고할 준비가 끝났어요.`,
  ]

  const clearFlowTimers = () => {
    flowTimersRef.current.forEach((timerId) => window.clearTimeout(timerId))
    flowTimersRef.current = []
  }

  const moveToStep = (nextStep) => {
    clearFlowTimers()
    setIsProcessing(false)
    setActiveStep(Math.max(0, Math.min(nextStep, steps.length - 1)))
  }

  const startUpload = (source) => {
    clearFlowTimers()
    setReceiptSource(source)
    setIsProcessing(true)
    setActiveStep(0)

    const autoSteps = [1, 2, 3]
    flowTimersRef.current = autoSteps.map((step, index) =>
      window.setTimeout(() => {
        setActiveStep(step)

        if (step === 3) {
          setIsProcessing(false)
        }
      }, (index + 1) * 650),
    )
  }

  const proceedNextStep = () => {
    clearFlowTimers()
    setIsProcessing(false)

    if (isReadyToStock) {
      stockIngredients()
      return
    }

    if (activeStep === 4 && reviewCount > 0) {
      window.alert('검토 필요 품목이 있어요. 후보 변경 버튼으로 표준 재료명을 먼저 확인해주세요.')
      moveToStep(3)
      return
    }

    moveToStep(activeStep + 1)
  }

  const addRow = () => {
    clearFlowTimers()
    setIsProcessing(false)
    const name = window.prompt('추가할 품목명을 입력해주세요.')

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
        review: true,
      },
    ])
    setActiveStep(2)
  }

  const changeCandidate = (raw) => {
    clearFlowTimers()
    setIsProcessing(false)
    const nextName = window.prompt('변경할 표준 재료명을 입력해주세요.')

    if (!nextName?.trim()) {
      return
    }

    setDetectedRows((prev) =>
      prev.map((row) =>
        row.raw === raw ? { ...row, name: nextName.trim(), review: false } : row,
      ),
    )
    const remainingReviewCount = detectedRows.filter((row) => row.raw !== raw && row.review).length
    setActiveStep(remainingReviewCount === 0 ? 5 : 4)
  }

  const resetAnalysis = () => {
    clearFlowTimers()
    setIsProcessing(false)
    setDetectedRows(rows)
    setReceiptSource('샘플 영수증')
    setActiveStep(1)
  }

  const stockIngredients = () => {
    clearFlowTimers()
    setIsProcessing(false)

    if (reviewCount > 0 && !window.confirm('검토 필요 품목이 남아 있어요. 그래도 냉장고에 입고할까요?')) {
      moveToStep(3)
      return
    }

    window.localStorage.setItem('bobbeori-last-stocked-count', String(detectedRows.length))
    navigate('/fridge')
  }

  useEffect(() => clearFlowTimers, [])

  return (
    <section className="receipt-page" aria-labelledby="receipt-title">
      <div className="receipt-hero">
        <div className="receipt-hero__copy">
          <h1 id="receipt-title">영수증 OCR 입고</h1>
          <p>영수증 한 장으로 재료를 똑똑하게 등록해요!</p>
        </div>
        <ImageSlot className="receipt-hero__image" src={imageReceipt} />
        <aside className="receipt-summary" aria-label="입고 요약">
          <h2>입고 요약</h2>
          {currentSummary.map((item) => (
            <div key={item.label}>
              <span>{item.label}</span>
              <strong>{item.value}</strong>
            </div>
          ))}
        </aside>
      </div>

      <div className="receipt-stepper" aria-label="OCR 진행 단계">
        {steps.map((step, index) => (
          <React.Fragment key={step}>
            <button
              className={[
                index === activeStep ? 'is-active' : '',
                index < activeStep ? 'is-done' : '',
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

      <div className="receipt-layout">
        <section className="receipt-panel receipt-upload" aria-labelledby="upload-title">
          <h2 id="upload-title">영수증 업로드</h2>
          <div className="receipt-dropzone">
            <ImageSlot className="receipt-dropzone__icon" />
            <p>영수증 사진을 드래그하거나 업로드/촬영 버튼을 눌러주세요.</p>
            <div>
              <button className="receipt-primary-button" type="button" onClick={() => startUpload('업로드 이미지')}>
                이미지 업로드
              </button>
              <button className="receipt-soft-button" type="button" onClick={() => startUpload('카메라 촬영본')}>
                카메라 촬영
              </button>
            </div>
          </div>

          <div className="receipt-preview">
            <div className="receipt-preview__title">
              <h3>영수증 미리보기</h3>
              <button type="button" onClick={() => moveToStep(0)}>다시 촬영</button>
            </div>
            <article className="receipt-paper">
              <strong>BABBEORI MART</strong>
              <span>2025-05-22 15:42:18</span>
              <dl>
                {detectedRows.map((row) => (
                  <div key={row.raw}>
                    <dt>{row.raw}</dt>
                    <dd>{row.quantity}</dd>
                    <dd>{row.price}</dd>
                  </div>
                ))}
              </dl>
              <b>합계 12,560원</b>
            </article>
          </div>

          <p className="receipt-tip">사진은 정면에서 밝게 촬영하면 인식률이 올라가요.</p>
        </section>

        <section className="receipt-panel receipt-result" aria-labelledby="result-title">
          <div className="receipt-panel__title">
            <h2 id="result-title">OCR 분석 결과</h2>
            <span>분석 완료</span>
          </div>
          <div className="receipt-result-table" role="table" aria-label="OCR 분석 결과">
            <div className="receipt-result-row receipt-result-row--head" role="row">
              <span role="columnheader">품목명</span>
              <span role="columnheader">수량</span>
              <span role="columnheader">가격</span>
            </div>
            {detectedRows.map((row, index) => (
              <div className="receipt-result-row" role="row" key={row.raw}>
                <span role="cell">
                  <b>{index + 1}</b>
                  {row.name}
                </span>
                <span role="cell">{row.quantity}</span>
                <span role="cell">{row.price}</span>
              </div>
            ))}
          </div>
          <button className="receipt-add-row" type="button" onClick={addRow}>
            + 행 추가
          </button>
          <p className="receipt-success">
            {reviewCount ? `${reviewCount}개 항목은 검토가 필요해요.` : '모든 항목이 정상적으로 추출되었어요!'}
          </p>
          <div className="receipt-result-actions">
            <button className="receipt-soft-button" type="button" onClick={resetAnalysis}>
              재분석
            </button>
            <button className="receipt-primary-button" type="button" onClick={() => moveToStep(4)}>
              결과 저장
            </button>
          </div>
        </section>

        <section className="receipt-panel receipt-candidates" aria-labelledby="candidate-title">
          <h2 id="candidate-title">식재료 후보 확인</h2>
          <div className="receipt-candidate-list">
            {detectedRows.map((row) => (
              <article key={row.raw}>
                <span>{row.raw}</span>
                <b aria-hidden="true">→</b>
                <ImageSlot className="receipt-candidate__image" src={row.image} />
                <strong>{row.name}</strong>
                <button type="button" aria-label={`${row.name} 후보 변경`} onClick={() => changeCandidate(row.raw)} />
              </article>
            ))}
          </div>

          <h2>표준 재료명 매핑</h2>
          <div className="receipt-mapping-table">
            {detectedRows.map((row) => (
              <article key={row.name}>
                <strong>{row.name}</strong>
                <span className={row.review ? 'is-review' : ''}>{row.review ? '검토 필요' : '자동 매핑'}</span>
                <span>냉장</span>
                <span>{row.review ? '반찬' : '채소'}</span>
                <em>{row.review ? '검토' : '자동'}</em>
              </article>
            ))}
          </div>

          <div className="receipt-normalize">
            <span>수량 단위 정규화</span>
            <span>기본 유통기한 설정</span>
          </div>

          <button className="receipt-stock-button" type="button" onClick={stockIngredients}>
            <ImageSlot className="receipt-stock-button__icon" src={iconRefrigerator} />
            냉장고에 입고하기
            <small>총 {detectedRows.length}개 재료가 등록돼요!</small>
          </button>
        </section>
      </div>
    </section>
  )
}

export default ReceiptOcr
