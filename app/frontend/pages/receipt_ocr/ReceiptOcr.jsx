import React from 'react'
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

const summary = [
  { label: '인식 품목', value: '6개' },
  { label: '자동 매핑', value: '5개' },
  { label: '검토 필요', value: '1개' },
]

function ImageSlot({ src, alt = '', className = '' }) {
  return (
    <span className={`receipt-image-slot ${src ? 'is-filled' : ''} ${className}`}>
      {src ? <img src={src} alt={alt} /> : null}
    </span>
  )
}

function ReceiptOcr() {
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
          {summary.map((item) => (
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
            <button className={index === 1 ? 'is-active' : ''} type="button">
              <span>{step}</span>
            </button>
            {index < steps.length - 1 ? <i aria-hidden="true" /> : null}
          </React.Fragment>
        ))}
      </div>

      <div className="receipt-layout">
        <section className="receipt-panel receipt-upload" aria-labelledby="upload-title">
          <h2 id="upload-title">영수증 업로드</h2>
          <div className="receipt-dropzone">
            <ImageSlot className="receipt-dropzone__icon" />
            <p>영수증 사진을 드래그하거나 업로드/촬영 버튼을 눌러주세요.</p>
            <div>
              <button className="receipt-primary-button" type="button">
                이미지 업로드
              </button>
              <button className="receipt-soft-button" type="button">
                카메라 촬영
              </button>
            </div>
          </div>

          <div className="receipt-preview">
            <div className="receipt-preview__title">
              <h3>영수증 미리보기</h3>
              <button type="button">다시 촬영</button>
            </div>
            <article className="receipt-paper">
              <strong>BABBEORI MART</strong>
              <span>2025-05-22 15:42:18</span>
              <dl>
                {rows.map((row) => (
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
            {rows.map((row, index) => (
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
          <button className="receipt-add-row" type="button">
            + 행 추가
          </button>
          <p className="receipt-success">모든 항목이 정상적으로 추출되었어요!</p>
          <div className="receipt-result-actions">
            <button className="receipt-soft-button" type="button">
              재분석
            </button>
            <button className="receipt-primary-button" type="button">
              결과 저장
            </button>
          </div>
        </section>

        <section className="receipt-panel receipt-candidates" aria-labelledby="candidate-title">
          <h2 id="candidate-title">식재료 후보 확인</h2>
          <div className="receipt-candidate-list">
            {rows.map((row) => (
              <article key={row.raw}>
                <span>{row.raw}</span>
                <b aria-hidden="true">→</b>
                <ImageSlot className="receipt-candidate__image" src={row.image} />
                <strong>{row.name}</strong>
                <button type="button" aria-label={`${row.name} 후보 변경`} />
              </article>
            ))}
          </div>

          <h2>표준 재료명 매핑</h2>
          <div className="receipt-mapping-table">
            {rows.map((row) => (
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

          <button className="receipt-stock-button" type="button">
            <ImageSlot className="receipt-stock-button__icon" src={iconRefrigerator} />
            냉장고에 입고하기
            <small>총 6개 재료가 등록돼요!</small>
          </button>
        </section>
      </div>
    </section>
  )
}

export default ReceiptOcr
