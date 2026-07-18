# `enblav262` 코드 리뷰

## 리뷰 기준

- 기준 커밋: `origin/dev` / `ed128a972a2fe69936efd191333689bba63019b2`
- 담당 영역: 영수증 OCR, 장보기 Agent와 화면
- 확인 항목: 모듈화, 주석, 기능 응집도, 정확성·보안·운영 안정성

## 요약

| 항목 | 평가 | 핵심 의견 |
| --- | --- | --- |
| 모듈화 | 일부 개선 필요 | 장보기 Backend는 잘 나뉘었지만 OCR service와 화면이 너무 많은 책임을 가진다. |
| 주석 | Backend 양호, Frontend 부족 | 보안 검증 흐름은 명확하지만 SSE와 화면 상태 전이 설명이 부족하다. |
| 기능 응집도 | 개선 필요 | Receipt API 호출과 화면 기능이 한 페이지에 흩어져 있고 장보기 완료 정책이 서로 다르다. |
| 코드 품질 | 기반 양호, 데이터 무결성 보완 필요 | 이미지 보안은 좋지만 구매 완료 transaction과 오류 노출을 먼저 수정해야 한다. |

## 잘된 점

- 이미지 확장자, MIME, magic bytes, Pillow parsing을 함께 검증한다.
- 이미지를 sanitize한 후 저장하고 삭제 대상이 upload root 안인지 확인한다.
- sync OpenAI SDK 호출을 `run_in_threadpool`로 감싸 event loop blocking을 피했다.
- 영수증 확정·이력·개인정보 서비스가 별도 모듈로 존재한다.
- 장보기 Backend는 API, service, provider, schema, Agent handler로 나뉘어 있다.

## 리뷰 발견사항

### P1. 장보기 완료가 부분 저장될 수 있음

- 공동 담당: `jaemukkim`
- 위치: `app/backend/services/shopping_service/shopping_service.py:130-165`, `app/backend/services/inventory_service/inventory_service.py:327-348`
- 구매 항목마다 `add_ingredient()`가 실행되고, 해당 메서드는 매번 `db.commit()`한다.
- 중간 항목에서 실패하면 앞선 재고와 구매 상태 일부가 이미 저장될 수 있다.
- 하위 재고 메서드는 `flush()`까지만 수행하고 `complete_purchase()`가 한 번만 commit하도록 바꾼다.

### P1. OCR 공급자 예외가 사용자에게 노출됨

- 위치: `app/backend/services/receipt_ocr_service/receipt_ocr_service.py:148-158,561-571`
- provider 예외가 `str(exc)` 또는 `HTTPException.detail`로 SSE 응답에 전달된다.
- 외부에는 고정 오류 코드와 일반 문구만 보내고 상세 예외는 correlation ID와 함께 서버에 기록한다.

### P2. OCR service의 책임이 과도함

- 위치: `app/backend/services/receipt_ocr_service/receipt_ocr_service.py`
- 업로드 제한, 이미지 검사·저장, OpenAI 호출, LangGraph, 품질 평가, DB 저장이 한 클래스에 있다.
- image service, OCR provider, quality policy, workflow 네 경계로 점진적으로 나눈다.

### P2. Receipt 화면이 약 3천 줄임

- 위치: `app/frontend/pages/receipt_ocr/ReceiptOcr.jsx`
- SSE parser, crop, upload, 확인 폼, 이력, 삭제, 구매 차트를 한 파일에서 처리한다.
- `fetch()`도 `40,821,1144,1350,2676,2730,2797`에 직접 존재한다.
- API client와 `useReceiptUpload` hook부터 추출한 뒤 화면 컴포넌트를 나눈다.

### P2. 업로드 제한이 process-local임

- 위치: `receipt_ocr_service.py:67-71,400-423`
- 메모리 `defaultdict`를 사용해 worker·replica마다 제한량이 따로 계산된다.
- 비용·보안을 위한 제한이면 Redis나 DB로 옮긴다.

### P2. 가격 비교 계약과 구현이 다름

- 위치: `shopping_service.py:173-201`
- `coupang`, `kurly`는 항상 `None`, `delivery_saving`은 항상 `0`, 추천 마켓은 항상 네이버다.
- 실제 다중 마켓 비교를 구현하거나 기능명을 “네이버 상품 검색”으로 정정한다.

### P2. 장보기 완료 정책이 서로 다름

- 위치: `app/frontend/pages/shopping_list/ShoppingList.jsx:803-821`
- Backend와 Agent는 완료 이력을 보존하지만 Frontend는 전부 구매하면 목록을 자동 삭제한다.
- 보존 또는 삭제 중 하나를 제품 정책으로 정해 UI·REST·Agent에 동일하게 적용한다.

## 주석 개선

- SSE event 종류와 각 event가 바꾸는 상태
- upload 취소·재시도 조건
- object URL과 임시 이미지 정리 시점
- 품질 점수와 재업로드 판정 이유
- 구매 완료 transaction의 commit 소유자

상태 전이를 설명하는 긴 주석보다 hook과 작은 컴포넌트로 이름을 부여하는 것이 우선이다.

## 권장 작업 순서

- [ ] 장보기 입고를 단일 transaction으로 변경
- [ ] OCR 상세 예외 비공개화
- [ ] `receiptApi`와 `useReceiptUpload` 추출
- [ ] OCR image/provider/quality/workflow 경계 분리
- [ ] 장보기 완료 목록 정책 통일
- [ ] 가격 비교 기능의 실제 범위 확정
- [ ] 다중 worker용 rate limit 저장소 결정

## 완료 기준

- 구매 중 오류가 발생하면 재고와 구매 상태가 모두 rollback된다.
- API와 SSE에 provider 원문 예외가 포함되지 않는다.
- Receipt 페이지가 API 호출과 업로드 상태를 직접 소유하지 않는다.
- 모든 화면과 Agent가 동일한 장보기 완료 정책을 따른다.
