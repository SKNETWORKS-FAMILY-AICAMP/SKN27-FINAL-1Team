# 테스트 코드 발표자료 정리

## 1. 한 장 요약

밥벌이는 기능별 핵심 흐름을 pytest 기반 테스트로 검증했다. 테스트는 단순 API 호출 성공 여부보다, 실제 서비스에서 문제가 생기기 쉬운 경계 조건을 중심으로 구성했다.

| 구분 | 테스트 수 | 주요 검증 내용 |
|---|---:|---|
| 챗봇 / 라우팅 / MCP | 40 | 의도 분류, 로그인 필요 기능 분리, 냉장고·캘린더 MCP 라우팅, 대화 상태 유지 |
| 캘린더 / RunPod / MCP | 18 | bobbeoriKey 기반 필터링, Google Calendar 생성·삭제, RunPod runsync 요청, 내부 토큰 검증 |
| 영수증 / OCR | 15 | 영수증 업로드, SSE 진행 이벤트, OCR 품질 재시도, 비영수증 거절, 냉장고 입고 |
| 냉장고 / 재고 | 11 | 재료 CRUD, 소비기한 상태 계산, 표시명 검색, MCP Tool 응답 형식 |
| 전체 기능 Smoke | 1 | 챗봇, 냉장고 Tool, 캘린더, OCR의 주요 계약 동시 확인 |

총 pytest 테스트 함수는 85개다. `test_ai_expiration.py`는 pytest 테스트가 아니라 수동 실행용 AI 소비기한 점검 스크립트다.

## 2. 기능별 테스트 구성

### 냉장고 / 재고 관리

| 파일 | 개수 | 발표용 설명 |
|---|---:|---|
| `test/api/test_inventory_api.py` | 5 | 재료 목록 요약, 추가, 수정, 단건 삭제, 다건 삭제 API가 기대 상태코드를 반환하는지 확인 |
| `test/test_inventory_service.py` | 2 | 카테고리 기본값, 한국어 조사 처리 등 응답 표시 품질 확인 |
| `test/test_inventory_name_match.py` | 1 | 사용자가 입력한 재료명과 DB 표시명이 띄어쓰기 차이에도 매칭되는지 확인 |
| `test/features/test_inventory_feature_contract.py` | 1 | 소비기한 임박 재료와 안전 재료가 서로 다른 상태로 분류되는지 A/B 형태로 확인 |
| `test/features/test_fridge_feature_contract.py` | 2 | 냉장고 MCP Tool의 공통 응답 형식과 임박 재료 필터링 확인 |

핵심 메시지:

> 냉장고 기능은 단순 CRUD뿐 아니라, 소비기한 상태 계산과 사용자가 자연어로 부르는 재료명 매칭까지 테스트했다.

### 영수증 / OCR

| 파일 | 개수 | 발표용 설명 |
|---|---:|---|
| `test/api/test_receipts_api.py` | 5 | 영수증 업로드, 스트리밍 업로드, 확인 저장, 내역 조회, 내역 삭제 API 검증 |
| `test/fixtures/ocr/test_receipt_ocr_flow.py` | 9 | OCR 결과 정규화, Neo4j 표준 재료명 매칭, 저품질 OCR 재시도, 비영수증 거절, 냉장고 입고 검증 |
| `test/features/test_receipt_feature_contract.py` | 1 | 영수증 이미지는 통과하고 비영수증 문서는 재업로드 대상으로 분리되는지 확인 |

핵심 메시지:

> 영수증 기능은 파일 업로드 이후 OCR, 재료명 정규화, DB 저장까지 이어지는 파이프라인을 테스트했다. 특히 비영수증과 저품질 OCR은 저장하지 않고 재업로드를 요청하도록 검증했다.

### 챗봇 / 멀티 에이전트 라우팅

| 파일 | 개수 | 발표용 설명 |
|---|---:|---|
| `test/api/test_chat_api.py` | 1 | 기존 챗봇 API 응답 계약 유지 확인 |
| `test/test_chat_service.py` | 8 | 질문 의도 분류, 레시피 재료 추출, 로그인 경계, 가이드 결과 필터링, 외부 검색 분기 확인 |
| `test/test_chat_empty_inventory.py` | 1 | 냉장고가 비어 있을 때 사용자에게 도움이 되는 안내 문구 반환 |
| `test/test_chat_graph.py` | 25 | 냉장고 등록·소비·삭제, 캘린더 등록, 확인·취소, pending 대화 상태, 날짜 파싱, 로그인 필요 처리 검증 |
| `test/features/test_chat_feature_contract.py` | 3 | 챗봇 응답 형식, 라우팅 테이블, 냉장고/캘린더 요청 분기 확인 |
| `test/test_fridge_mcp_tools.py` | 2 | 냉장고 MCP Tool 응답 형식과 쓰기 실패 시 rollback 확인 |

핵심 메시지:

> 챗봇 테스트는 멀티 에이전트 구조의 핵심인 의도 분류와 Tool 호출 조건을 검증한다. 사용자가 짧게 답하거나 이전 질문에 이어서 답하는 pending 상태까지 테스트했다.

### 캘린더 / MCP / RunPod

| 파일 | 개수 | 발표용 설명 |
|---|---:|---|
| `test/fixtures/calendar/test_calendar_events.py` | 15 | 일일 알림 event_key 생성, bobbeoriKey 필터링, 캘린더 생성·삭제 fallback, RunPod 요청 형식, 내부 토큰, MCP 서버 동작 확인 |
| `test/features/test_calendar_feature_contract.py` | 3 | 밥벌이 이벤트만 조회·삭제 가능하도록 event_key 계약 검증, Serverless 완료 응답만 성공으로 처리 |

핵심 메시지:

> 캘린더 테스트는 사용자의 개인 캘린더를 건드리지 않기 위해 bobbeoriKey가 있는 밥벌이 이벤트만 조회·삭제하도록 검증했다. RunPod MCP 경로가 실패해도 백엔드 fallback으로 생성되도록 안정성도 확인했다.

## 3. 발표에 넣기 좋은 검증 시나리오

| 시나리오 | 검증 목적 | 관련 테스트 |
|---|---|---|
| 영수증 사진 업로드 후 재료 후보 추출 | OCR 파이프라인 정상 동작 | `test_upload_receipt_api_returns_ocr_candidates` |
| 영수증이 아닌 이미지 업로드 | 잘못된 파일 저장 방지 | `test_analyze_upload_requests_reupload_for_non_receipt_document` |
| OCR 품질이 낮은 경우 재시도 | 인식 정확도 보완 | `test_analyze_upload_retries_low_quality_ocr_result` |
| 확인된 영수증 품목 냉장고 입고 | OCR 결과와 재고 DB 연결 | `test_confirm_receipt_saves_neo4j_standard_name_to_receipt_and_fridge_items` |
| 소비기한 임박 재료 분류 | 알림·추천 기준 데이터 생성 | `test_inventory_feature_ab_expiring_vs_safe_item_status` |
| 냉장고 자연어 등록 | 챗봇에서 Tool 호출까지 연결 | `test_inventory_add_sentence_asks_storage_without_llm` |
| 캘린더 일정 등록 요청 | 챗봇 → 캘린더 MCP 라우팅 | `test_calendar_action_routes_to_mcp` |
| 밥벌이 이벤트만 캘린더 조회 | 개인 일정 노출 방지 | `test_list_google_calendar_events_only_returns_our_visible_events` |
| RunPod Serverless 호출 | 백엔드 → RunPod MCP 요청 계약 | `test_call_calendar_tool_posts_runpod_runsync_request` |
| RunPod 내부 토큰 검증 | 외부 임의 호출 차단 | `test_runpod_handler_checks_token_and_dispatches_tool` |

## 4. 발표용 문장

테스트 전략:

> 전체 기능을 모두 E2E로 무겁게 돌리기보다, 장애가 나기 쉬운 경계 조건을 기능별 단위 테스트와 계약 테스트로 쪼개 검증했습니다.

영수증/OCR:

> 영수증 이미지는 OCR 결과가 낮은 품질이면 재시도하고, 영수증이 아닌 문서는 DB에 저장하지 않도록 테스트했습니다.

챗봇/MCP:

> 챗봇은 자연어 요청을 냉장고, 레시피, 캘린더 등 필요한 기능으로 라우팅해야 하므로, 의도 분류와 pending 대화 상태를 집중적으로 테스트했습니다.

캘린더/보안:

> Google Calendar에는 개인 일정도 함께 존재하므로, 밥벌이가 만든 이벤트만 bobbeoriKey로 식별해 조회·수정·삭제하도록 검증했습니다.

RunPod:

> 캘린더 MCP는 RunPod Serverless로 분리했고, 요청 본문과 내부 토큰 검증을 테스트해 백엔드에서만 호출되도록 했습니다.

## 5. 실행 명령

전체 테스트:

```powershell
.\.venv\Scripts\python.exe -m pytest test -q
```

기능별 테스트:

```powershell
.\.venv\Scripts\python.exe -m pytest test\api -q
.\.venv\Scripts\python.exe -m pytest test\fixtures\ocr -q
.\.venv\Scripts\python.exe -m pytest test\fixtures\calendar -q
.\.venv\Scripts\python.exe -m pytest test\test_chat_service.py test\test_chat_graph.py -q
```

현재 로컬 가상환경에서 챗봇 graph 계열 테스트를 돌리려면 `langchain_openai`가 설치되어 있어야 한다. 의존성이 빠져 있으면 pytest 수집 단계에서 `ModuleNotFoundError: langchain_openai`가 난다.

## 6. 발표 슬라이드 추천 구성

| 슬라이드 | 제목 | 넣을 내용 |
|---|---|---|
| 1 | 테스트 전략 | 총 85개 테스트, 기능별 단위/계약 테스트 중심, 외부 API는 mock/fake client로 대체 |
| 2 | 기능별 검증 범위 | 냉장고, OCR, 챗봇, 캘린더/RunPod 표 |
| 3 | 핵심 트러블슈팅 검증 | 비영수증 차단, bobbeoriKey 보호, RunPod fallback, pending 대화 상태 |
| 4 | 테스트 결과와 의미 | 캘린더 15개 통과, 주요 기능별 경계 조건 검증, 발표 시 실제 시연 흐름과 연결 |

