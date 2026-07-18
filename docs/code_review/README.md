# 밥벌이 코드 리뷰

## 1. 리뷰 기준

- 리뷰 일자: 2026-07-17
- 기준 브랜치/커밋: `origin/dev` / `ed128a972a2fe69936efd191333689bba63019b2`
- 담당자 기준: 루트 `README.md`의 역할표를 우선 적용하고, `git log`, `git blame`의 작성자 정보를 보조 근거로 사용했다.
- 확인 항목: 모듈화, 주석의 품질, 기능 응집도, 정확성·보안·운영 안정성
- 범위: 애플리케이션과 AI Agent의 운영 코드 중심 정적 리뷰다. 외부 API, DB, RunPod를 연결한 통합 실행 결과까지 보증하는 문서는 아니다.

Git 작성자 표기에는 동일인의 별칭이 섞여 있다. 이 문서에서는 다음과 같이 GitHub ID로 합쳤다.

| GitHub ID | Git 작성자 표기 | 주 담당 영역 |
| --- | --- | --- |
| `EJ-pro` | `EJ-pro` | PM, MCP, Calendar, 홈 통합 |
| `enblav262` | `enblav262` | 영수증 OCR, 장보기 Agent |
| `jaemukkim` | `jaemukkim` | Backend, 인증, 챗봇, 재고 Agent |
| `enooola0204-spec` | `enooola0204-spec` | GraphDB, 식재료 가이드 Agent |
| `wynn3312` | `wynn3312`, `KimKyeongsu`, `김경수` | 추천 모델·데이터, 레시피 Agent |

담당자에게 바로 전달할 수 있는 개별 리뷰 파일:

- [`EJ-pro`](./EJ-pro.md)
- [`enblav262`](./enblav262.md)
- [`jaemukkim`](./jaemukkim.md)
- [`enooola0204-spec`](./enooola0204-spec.md)
- [`wynn3312`](./wynn3312.md)

> 작성자 표시는 책임을 추궁하기 위한 것이 아니라 수정 작업의 최초 배정 기준이다. 여러 담당자의 서비스가 만나는 문제는 공동 작업으로 분류했다.

## 2. 결론

전체 구조는 `API → service → agent/provider` 방향이 잡혀 있고, 기능별 테스트와 스키마도 존재한다. 특히 이미지 검증, 캘린더 이벤트 멱등성, 가이드의 안전 민감 응답, 레시피 Agent 분리는 좋은 기반이다.

다만 지금 바로 배포한다면 아래 세 가지가 가장 큰 위험이다.

1. 인증 없이 실제 JWT를 발급하는 `/dev-login`이 운영 라우터에 포함돼 있다.
2. 장보기 구매 완료가 재고 서비스의 항목별 `commit()`을 호출해, 중간 실패 시 일부 재고만 저장될 수 있다.
3. 캘린더 일일 작업이 FastAPI 프로세스 안에서 시작돼, worker나 replica 수만큼 중복 실행될 수 있다.

큰 파일 자체가 문제의 전부는 아니지만, 변경 이유가 서로 다른 기능이 한 파일에 함께 있는 곳이 많다. 우선 보안·트랜잭션·운영 문제를 해결한 뒤, 아래 순서로 분리하는 것이 효율적이다.

1. `ReceiptOcr.jsx`와 `Guide.jsx`의 API·상태·표시 컴포넌트 분리
2. `guide_agent.py`와 `supervisor_utils.py`의 저장소·라우팅·표시 계층 분리
3. `calendar_api.py`의 OAuth·Google Gateway·동기화 서비스 분리
4. `receipt_ocr_service.py`의 업로드 보안·OCR 공급자·품질 정책 분리

## 3. 릴리스 전 공통 조치

### P0 — 배포 차단

#### CR-001. 인증 없는 개발용 로그인 제거 또는 완전 차단

- 담당: `jaemukkim`
- 위치: `app/backend/api/auth/auth_api.py:66-81`
- 근거: `/dev-login`은 인증이나 환경 검사 없이 고정된 개발 사용자로 실제 access token을 발급한다.
- 영향: 인터넷에 노출되면 누구나 유효한 사용자 토큰을 받을 수 있다.
- 조치: 운영 환경에서는 라우터 등록 자체를 하지 않는다. 단순히 UI에서 버튼을 숨기거나 문서에서 제외하는 것으로는 부족하다. 개발 환경에서도 명시적인 feature flag와 별도 개발 secret을 함께 요구하는 편이 안전하다.

#### CR-002. JWT 기본 secret 금지

- 담당: `jaemukkim`
- 위치: `app/backend/core/config.py:31`, `app/backend/core/security.py:20,29,52,60`
- 근거: 환경변수가 없으면 `YOUR_JWT_SECRET_KEY_HERE`를 서명 키로 사용한다.
- 영향: 배포 설정 누락 한 번으로 모든 JWT를 예측 가능한 키로 위조할 수 있다.
- 조치: 기본값을 제거하고 애플리케이션 시작 시 길이와 환경별 설정을 검증한다. 개발·테스트 secret도 운영 secret과 분리한다.

### P1 — 높은 우선순위

#### CR-003. 장보기 완료와 냉장고 입고를 하나의 트랜잭션으로 묶기

- 공동 담당: `enblav262`, `jaemukkim`
- 위치: `app/backend/services/shopping_service/shopping_service.py:130-165`, `app/backend/services/inventory_service/inventory_service.py:327-348`
- 근거: `complete_purchase()`가 목록 항목마다 `inventory_service.add_ingredient()`를 호출하고, `add_ingredient()`는 매 호출마다 `db.commit()`한다.
- 영향: 두 번째 이후 항목에서 오류가 나면 앞선 재고는 이미 저장된다. 장보기 항목의 구매 상태도 다음 반복의 commit에 섞여 반영될 수 있어 목록과 재고가 부분적으로 어긋난다.
- 조치: 하위 서비스는 `flush()`까지만 수행할 수 있는 transaction-aware 메서드를 제공하고, `complete_purchase()`의 최상위 경계에서 한 번만 commit한다. 실패 시 전체 rollback되는 테스트를 추가한다.

#### CR-004. 캘린더 스케줄러를 웹 프로세스에서 분리

- 담당: `EJ-pro`, 배포 구성은 Backend 공동
- 위치: `app/backend/main.py:66-75`, `app/backend/services/calendar_job.py:40-49`
- 근거: FastAPI startup마다 무한 루프 task를 생성한다.
- 영향: Uvicorn worker가 2개이거나 컨테이너 replica가 2개면 동일한 작업도 2개 실행된다. 이벤트 자체는 `event_key`로 중복을 줄이지만 외부 호출, 로그, 갱신 충돌은 남는다.
- 조치: 별도 scheduler/worker 컨테이너로 옮기거나 DB·Redis 기반 distributed lock을 둔다. 종료 시 task 취소와 예외 관측도 명시한다.

#### CR-005. OCR 공급자 오류 내용을 사용자 응답에서 숨기기

- 담당: `enblav262`
- 위치: `app/backend/services/receipt_ocr_service/receipt_ocr_service.py:148-158,561-571`
- 근거: provider 예외를 `HTTPException.detail` 또는 `str(exc)`로 만든 뒤 SSE 응답에 전달한다.
- 영향: SDK 메시지, 요청 정보, 내부 구성 정보가 클라이언트에 노출될 수 있다.
- 조치: 외부에는 고정된 오류 코드와 일반 문구만 반환하고, 상세 예외는 correlation ID와 함께 서버 로그에 남긴다.

#### CR-006. 운영 CORS 목록을 환경별 allowlist로 제한

- 담당: Backend 공동, 최초 작업 제안 `jaemukkim`
- 위치: `app/backend/main.py:29-35`
- 근거: `allow_origins=["*"]`와 `allow_credentials=True`가 전역 설정이다.
- 영향: 브라우저 인증 정책이 의도와 다르게 작동하거나, 향후 cookie 인증을 추가할 때 공격 표면이 커진다.
- 조치: 프론트 도메인을 환경변수 목록으로 받고 개발 환경에서만 localhost를 허용한다.

## 4. 담당자별 리뷰

### `EJ-pro`

#### 담당 코드

- Google Calendar OAuth, 이벤트 동기화, MCP/RunPod 연결
- 홈·마이페이지·캘린더 등 프론트 통합 영역

#### 모듈화

평가: **분리 필요**

`app/backend/api/calendar/calendar_api.py`는 라우터 파일이지만 다음 책임을 모두 가진다.

- 암복호화와 토큰 갱신: `25-84`
- 이벤트 키·로그·Google API 생성/삭제: `87-288`
- 일일 동기화와 도메인 이벤트 생성: `291-401`
- HTTP 라우터: `404-626`

또한 `app/backend/services/calendar_job.py:7`이 API 모듈의 private 함수 `_get_access_token`, `_sync_daily_events`를 역으로 import한다. service가 API 구현에 의존해 계층 방향이 뒤집혀 있다.

권장 구조는 다음 정도면 충분하다.

```text
calendar/
├─ calendar_api.py          # 요청 검증과 응답만
├─ calendar_service.py      # connect, sync use case
├─ google_calendar_gateway.py
├─ calendar_token_store.py  # 암복호화·refresh
└─ calendar_events.py       # event_key와 payload 생성
```

#### 주석

평가: **보통**

`_create_event_once()`와 `_delete_event_once()`의 멱등성 설명은 정확하고 유용하다. 반면 JWT secret 회전이 토큰 복호화에 미치는 영향, RunPod에 access token을 전달하는 신뢰 경계, 스케줄러가 단일 실행이어야 한다는 운영 전제는 주석이나 문서에 없다. 코드가 무엇을 하는지보다 이 세 가지 제약을 기록하는 것이 더 중요하다.

#### 기능 응집도

- `calendar_job.py`가 `calendar_api.py`의 private 구현을 사용한다.
- MCP 실패 시 직접 Google API를 부르는 fallback이 API 파일에 함께 있어 gateway 정책이 흩어져 있다.
- `calendar_mcp_client.py:56-86`과 `ai/calendar/runpod_server.py:100-136` 사이로 Google access token이 전달된다. RunPod가 완전히 신뢰되는 내부 경계인지 운영 문서와 secret masking 정책을 명시해야 한다.
- `ai/calendar/runpod_server.py:94`의 DNS rebinding 보호 비활성화는 공개 네트워크 배포 전에 재검토해야 한다.

#### 잘된 점

- `event_key`와 Google private extended property를 이용해 생성 작업을 멱등하게 만들었다.
- 사용자 ID가 포함된 이벤트 키를 검증해 다른 사용자의 이벤트를 삭제하지 못하게 한다.
- 토큰을 DB에 평문으로 저장하지 않고 refresh 흐름도 구현했다.

#### 제안 작업

1. CR-004를 먼저 처리한다.
2. JWT secret이 아닌 별도 버전형 암호화 키로 캘린더 token을 암호화한다. 키 회전 전략도 함께 둔다.
3. API의 private 함수를 service/gateway의 public 계약으로 이동한다.
4. RunPod 전달 payload와 로그에서 token이 남지 않는지 테스트한다.

### `enblav262`

#### 담당 코드

- 영수증 OCR 업로드·분석·확정·이력
- 장보기 목록, 가격 검색, 구매 완료와 재고 연결

#### 모듈화

평가: **Backend는 기반 양호, OCR 화면과 서비스는 분리 필요**

`receipt_ocr_service.py` 한 클래스가 업로드 제한, 이미지 포맷 검사, 파일 저장, OpenAI 호출, LangGraph, OCR 정규화, 품질 평가, DB 저장을 모두 맡는다. 변경 이유가 다른 기능이므로 다음 네 부분으로 나누는 편이 좋다.

- `receipt_image_service.py`: 검증, sanitize, 저장·삭제
- `receipt_ocr_provider.py`: OpenAI 요청, prompt, 응답 parsing
- `receipt_quality_policy.py`: 문서 판별, 점수, retry 정책
- `receipt_workflow.py`: graph와 persistence orchestration

`app/frontend/pages/receipt_ocr/ReceiptOcr.jsx`는 약 3천 줄이고, SSE parser·이미지 crop·업로드 상태·확정 폼·이력 삭제·구매 흐름 차트를 한 파일에 둔다. `fetch()`도 `40,821,1144,1350,2676,2730,2797`에 직접 흩어져 있다. API client, `useReceiptUpload`, crop panel, confirmation table, history, chart로 분리할 가치가 크다.

장보기 Backend는 API/service/provider/schema/agent handler가 분리되어 있어 OCR보다 응집도가 좋다.

#### 주석

평가: **Backend 양호, Frontend 부족**

이미지 검증 코드는 이름과 흐름이 명확하고 일부 보안 의도도 드러난다. `ReceiptOcr.jsx`는 SSE state machine과 많은 상태 전이를 다루는데 핵심 계약 설명이 거의 없다. 다만 주석을 늘리는 것만으로 해결하기보다 hook과 작은 컴포넌트로 이름을 부여하는 것이 우선이다. 주석은 SSE event 종류, 재시도·취소 조건, object URL 해제 조건처럼 코드만으로 드러나지 않는 제약에 집중한다.

#### 기능 응집도

- Receipt API 호출이 별도 frontend service 없이 페이지 곳곳에 있다.
- 쇼핑 완료 상태는 Backend와 Agent가 이력을 보존하지만, Frontend는 모든 항목 구매 후 목록을 자동 삭제한다(`ShoppingList.jsx:803-821`). 제품 정책을 한쪽으로 통일해야 한다.
- `compare_products()`는 `coupang`, `kurly`를 항상 `None`, `delivery_saving`을 항상 `0`, 추천 마켓을 항상 네이버 쇼핑으로 반환한다(`shopping_service.py:173-201`). 현재 구현은 다중 마켓 “가격 비교”가 아니라 네이버 최저가 검색에 가깝다.

#### 코드 리뷰 발견사항

- CR-003: 구매 완료의 부분 commit 가능성
- CR-005: OCR provider 예외 노출
- P2: 업로드 rate limit이 프로세스 메모리의 `defaultdict`에 있어 worker·replica별로 따로 계산된다(`receipt_ocr_service.py:67-71,400-423`). 보안/비용 제한이라면 Redis나 DB로 옮긴다.
- P2: `compare_products`의 이름·응답 스키마와 실제 기능을 일치시킨다. 실제 비교를 구현하지 않을 계획이면 `search_naver_products`처럼 정직하게 이름을 바꾼다.

#### 잘된 점

- 확장자, MIME, magic bytes, Pillow parsing을 함께 검사하고 sanitize 후 저장한다.
- 저장 파일 삭제 시 업로드 루트 아래인지 확인해 경로 이탈을 막는다.
- sync OpenAI SDK 호출을 `run_in_threadpool`로 감싸 async event loop를 막지 않는다.
- 영수증 확정·이력·개인정보 서비스가 OCR 분석 본체와 별도 모듈로 존재한다.

#### 제안 작업

1. CR-003과 CR-005를 우선 처리한다.
2. `ReceiptOcr.jsx`에서 API client와 upload hook부터 추출한다.
3. 가격 비교의 제품 범위를 “네이버 쇼핑 검색”으로 정정하거나 실제 provider를 추가한다.
4. 완료 목록 보존 여부를 하나의 제품 정책으로 정하고 UI·REST·Agent에 동일하게 적용한다.

### `jaemukkim`

#### 담당 코드

- FastAPI 기반, OAuth/JWT 인증, 채팅 Supervisor 연결
- 냉장고 재고 CRUD와 자연어 재고 처리

#### 모듈화

평가: **서비스 경계는 있으나 Supervisor utility와 트랜잭션 경계 개선 필요**

API, schema, service, DB model이 분리된 기본 구조는 좋다. 그러나 `ai/agents/supervisor_agent/supervisor_utils.py`는 약 850줄에 다음 책임을 함께 둔다.

- keyword 기반 intent 판별
- guide/calendar 응답 표시
- 대화 history와 pending action 상속
- LLM route payload parsing
- alarm 요청 parsing
- agent retry와 결과 병합

`routing_rules.py`, `conversation_context.py`, `response_mapper.py`, `agent_execution.py` 정도로 나누면 supervisor graph와 service가 필요한 부분만 의존할 수 있다.

`inventory_service.py`는 한 서비스로 읽을 수 있는 범위지만 public 메서드가 직접 commit해 다른 use case가 원자적으로 조합하기 어렵다. CR-003처럼 장보기와 연결할 때 실제 데이터 무결성 문제로 이어진다.

#### 주석

평가: **양호**

재고 서비스의 docstring, Supervisor의 섹션 구분, 테스트의 의도 설명은 전반적으로 읽기 쉽다. 다만 `/dev-login`의 주석은 위험한 동작을 명확히 설명하면서도 운영 차단 장치가 없다. 보안 제약은 주석이 아니라 실행 가능한 환경 검사와 테스트로 보장해야 한다.

#### 기능 응집도

- Supervisor routing 규칙과 응답 formatting이 같은 utility에 있어 Agent 추가 시 충돌 가능성이 높다.
- inventory public 메서드가 commit까지 소유해 shopping 같은 상위 workflow가 transaction을 통제하지 못한다.
- 애플리케이션 startup, CORS, scheduler가 `main.py`에 모여 있다. router 조립은 유지하되 lifespan과 운영 설정을 별도 bootstrap 모듈로 분리할 수 있다.

#### 코드 리뷰 발견사항

- CR-001: 공개 개발용 token 발급 endpoint
- CR-002: 예측 가능한 JWT 기본 키
- CR-003: 재고 서비스의 내부 commit 때문에 발생하는 부분 저장
- CR-006: 운영 CORS wildcard

#### 잘된 점

- inventory service가 이름 정규화, 저장 규칙, 응답 mapping을 private helper로 분리했다.
- 식재료 master 생성 시 nested transaction과 `IntegrityError` 재조회를 사용해 동시 생성 충돌을 고려했다.
- Supervisor의 세션 metadata 전달, Agent 오류 변환 등 계약 테스트가 있다.

#### 제안 작업

1. CR-001과 CR-002는 배포 전에 반드시 닫는다.
2. service 메서드에 `commit` 책임을 두지 않는 transaction 정책을 정하고 장보기부터 적용한다.
3. `supervisor_utils.py`를 네 역할로 나누되 공개 함수 시그니처는 먼저 유지해 큰 일괄 수정은 피한다.
4. `print` 대신 구조화 logger와 request/session correlation ID를 사용한다.

### `enooola0204-spec`

#### 담당 코드

- Neo4j 식재료 그래프, 영양 데이터 조회
- 식재료 가이드 Agent와 가이드 화면

#### 모듈화

평가: **도메인 로직은 탄탄하지만 Agent 파일 분리 필요**

`ai/agents/guide_agent/guide_agent.py`는 약 1,900줄이고 다음 경계를 모두 가진다.

- query 정규화, fuzzy matching, 의도 판별
- Neo4j guide service 호출
- PostgreSQL `SessionLocal` 직접 생성과 raw SQL 영양 조회(`806-973`)
- Tavily 검색과 OpenAI 요약(`1017-1090`)
- 사용자 응답·source·action 구성
- 최상위 query routing(`1635-1810`)

Agent는 orchestration만 맡기고 아래처럼 분리하는 것이 좋다.

```text
guide_agent/
├─ guide_agent.py             # orchestration/public contract
├─ guide_query_parser.py      # intent, keyword, fuzzy match
├─ nutrition_repository.py    # PostgreSQL query
├─ guide_fallback.py          # Tavily/OpenAI 정책
└─ guide_presenter.py         # message, action, source
```

`app/frontend/pages/guide/Guide.jsx`도 약 1,200줄의 한 페이지가 냉장고 조회, 목록·카테고리·상세·레시피·제안 제출을 모두 직접 `fetch()`한다(`218,261,298,337,370,414,586,657`). `guideApi`, query hook, catalog/detail/suggestion component로 나누는 것이 적절하다.

#### 주석

평가: **좋음**

파일 섹션, 응답 계약, 안전한 fallback 의도가 잘 드러난다. DB session도 `finally`에서 닫고, 안전 민감 가이드는 신뢰 도메인 결과만 사용한다. 개선할 점은 broad `except Exception`에서 원인을 버리거나 `print`만 하는 부분이다. 예상 가능한 provider/DB 오류를 분리하고 logger에 `ingredient`, `guide_type`, 오류 코드를 구조화해 남긴다.

#### 기능 응집도

- guide agent가 repository, 외부 검색 client, presenter 역할을 모두 수행한다.
- 영양 조회가 `guide_service`나 repository 계층을 거치지 않고 Agent에서 직접 DB session을 생성한다.
- 화면이 guide와 inventory, recipe API를 직접 조합하므로 페이지가 Backend-for-Frontend 역할까지 떠안는다.

#### 코드 리뷰 발견사항

- P2: `_summarize_web_content()`가 모든 예외를 삼키고 원문 일부로 조용히 대체한다(`1044-1045`). 사용자 fallback은 유지하되 관측 가능한 warning log를 남긴다.
- P2: `_fallback_guide_response()`는 예외를 `print`한다(`1115-1117`). 운영 로그 표준으로 바꾼다.
- P2: raw SQL과 query 조합이 여러 함수에 반복된다. repository로 이동하고 대표 영양 선택·부분 일치 규칙을 단위 테스트한다.

#### 잘된 점

- 식품 안전 관련 질문은 공신력 있는 도메인만 사용하고, 근거가 없으면 보수적으로 응답한다.
- URL host를 문자열 포함이 아니라 domain 규칙으로 검사한다.
- 영양 DB session을 `finally`에서 닫고 bind parameter를 사용한다.
- `build_guide_response()`로 Agent 응답 계약을 중앙화했다.
- 가이드 관련 설계·품질·응답 문서가 비교적 풍부하다.

#### 제안 작업

1. `nutrition_repository.py`와 `guide_fallback.py`부터 추출한다. 외부 계약을 바꾸지 않아 회귀 위험이 낮다.
2. broad exception을 provider/DB 오류로 좁히고 구조화 logger를 적용한다.
3. `Guide.jsx`의 API 호출을 `guideApi`로 모은 뒤 query hook과 표시 컴포넌트를 나눈다.
4. fuzzy match와 안전 민감 fallback에 표 기반 회귀 테스트를 추가한다.

### `wynn3312`

#### 담당 코드

- 레시피·영양 데이터 파이프라인과 추천 모델
- 추천 API, 레시피 Agent와 planner/tool 계층

#### 모듈화

평가: **Agent 분리는 좋고 데이터·배포 산출물 정리가 필요**

레시피 Agent는 `recipe_agent.py`, `recipe_planner.py`, `recipe_tools.py`, `recipe_config.py`, `recipe_utils.py`로 나뉘어 있다. plan → execute → render → quality review 흐름도 명확하다. 이번 리뷰 대상 중 모듈 분리가 가장 진전된 영역이다.

다만 `recipe_agent.py:39`에서 테스트와 하위 호환을 위해 내부 함수를 re-export한다. 임시 migration layer로는 괜찮지만 장기간 두면 planner/tools의 경계가 다시 흐려진다. 호출처를 새 모듈로 옮긴 뒤 제거 시점을 이슈로 남긴다.

데이터는 같은 대형 CSV가 운영·실험 경로에 중복된다. 예를 들어 `recipe_ingredient_alias.csv`와 `recipe_fix.csv`가 `ai/recommendation/data`와 `storage/processed/recipe`에 각각 같은 크기로 존재한다. 원본·가공·운영 artifact의 단일 기준 위치를 정할 필요가 있다.

#### 주석

평가: **설정·prompt는 좋음, 실행 정책은 보강 필요**

`recipe_config.py`는 상수와 tool schema 설명이 비교적 충실하다. Agent의 함수명과 dataclass도 흐름을 이해하기 쉽다. 반면 planner fallback의 broad exception, tool별 실패 처리, quality review 결과가 사용자 응답에 어떻게 영향을 주는지는 짧은 정책 docstring이 있으면 좋다. 예외를 전부 주석으로 설명하기보다 오류 code와 로그를 표준화한다.

#### 기능 응집도

- Agent orchestration, planner, tool adapter, 설정 분리는 잘 되어 있다.
- 대형 데이터와 학습 artifact가 Git 및 여러 디렉터리에 중복돼 코드 배포 이미지와 실험 재현 경계가 흐려진다.
- planner shadow test는 있지만 `execute_plan()`과 `review_recipe_quality()`를 직접 검증하는 단위 테스트는 검색되지 않았다.

#### 코드 리뷰 발견사항

- P1: `app/backend/Dockerfile:8`의 `lightfm>=1.17`은 shell form에서 `>`가 redirection으로 해석될 수 있다. 실제로는 버전 제약 없이 `lightfm`을 설치하고 `=1.17` 파일로 출력을 보낼 수 있어 재현성이 깨진다. 요구사항 파일에 `lightfm>=1.17`을 넣고 Dockerfile에서는 `pip install -r requirements.txt`만 실행한다.
- P2: 15MB `storage/raw/recipe/recipe.csv`, 11MB `cooking_steps.csv`, 1.4MB model pickle 등 대형 artifact가 Git에 포함돼 있다. 배포 이미지에 필요한 파일만 별도 artifact/version 저장소에서 받거나 Git LFS를 검토한다.
- P2: 동일한 가공 CSV의 중복 사본을 제거하고 생성 script와 checksum으로 재현한다.
- P2: planner는 예외 시 규칙 기반으로 잘 fallback하지만 예외가 관측되지 않는다(`recipe_planner.py:178-187`). warning log와 planner source metric을 남긴다.

#### 잘된 점

- planner, tool, config, utility 분리로 변경 이유가 명확하다.
- 규칙 planner fallback과 shadow 비교가 있어 LLM planner 장애·전환을 고려했다.
- 추천 API와 feature contract, matrix, planner shadow 테스트가 존재한다.
- 응답 생성 후 quality review 단계를 별도로 둬 결과 품질을 점검한다.

#### 제안 작업

1. Dockerfile의 LightFM 설치 표현을 즉시 수정한다.
2. `execute_plan()`과 `review_recipe_quality()`의 성공·빈 결과·tool 오류 테스트를 추가한다.
3. re-export 사용처를 제거한 뒤 compatibility layer 삭제 일정을 정한다.
4. 데이터·모델 artifact의 source of truth와 이미지 포함 규칙을 문서화한다.

## 5. 주석에 대한 팀 공통 기준

현재 코드에는 “무엇을 하는지” 설명하는 주석이 많지만, 파일별 편차가 크다. 앞으로는 주석 개수보다 다음 기준을 사용한다.

주석이 필요한 경우:

- 보안 경계와 신뢰 가정: token 전달, 허용 domain, 개인정보 보존 기간
- 트랜잭션 경계: 누가 commit/rollback을 소유하는지
- fallback 정책: 어떤 오류에서 무엇으로 대체하며 품질 저하를 어떻게 알리는지
- 멱등성·재시도 조건: event key, 중복 요청, provider retry
- 외부 계약: SSE event 종류, Agent response schema, tool input/output

주석보다 코드로 표현할 경우:

- 긴 함수의 단계 설명 → 작은 이름 있는 함수로 추출
- 반복되는 API URL → API client로 이동
- 숫자·문자열의 의미 → 상수나 enum 사용
- “운영에서는 쓰면 안 됨” → 환경 검사로 실행 자체를 차단

## 6. 권장 작업 순서

### 1단계 — 배포 안전성

- [ ] `jaemukkim`: `/dev-login` 운영 제외
- [ ] `jaemukkim`: JWT secret 시작 검증
- [ ] `enblav262` + `jaemukkim`: 장보기 입고 단일 transaction
- [ ] `EJ-pro`: 캘린더 scheduler 단일 실행 보장
- [ ] Backend 공동: CORS allowlist, 구조화 로그
- [ ] `enblav262`: OCR 상세 예외 비공개화

### 2단계 — 계약 정리

- [ ] `enblav262`: 네이버 상품 검색과 다중 마켓 가격 비교 중 제품 범위 확정
- [ ] `enblav262`: 장보기 완료 목록의 보존/자동 삭제 정책 통일
- [ ] `EJ-pro`: Calendar service/gateway 공개 계약 정의
- [ ] `wynn3312`: recipe compatibility re-export 제거 계획 수립

### 3단계 — 점진적 모듈 분리

- [ ] `enblav262`: Receipt API client와 upload hook 추출
- [ ] `enooola0204-spec`: nutrition repository와 web fallback 추출
- [ ] `jaemukkim`: Supervisor routing/context/response/execution 분리
- [ ] `EJ-pro`: Calendar token/event/gateway 분리
- [ ] `wynn3312`: 데이터와 model artifact 단일 기준 위치 확정

## 7. 완료 기준

다음 조건을 만족하면 이번 리뷰의 핵심 위험이 해소된 것으로 본다.

- 운영 환경에서 `/dev-login`이 404이거나 라우터에 등록되지 않는다.
- JWT secret 누락 시 애플리케이션이 즉시 시작 실패한다.
- 장보기 3개 입고 중 2번째에서 강제 오류를 내도 재고와 구매 상태가 모두 저장되지 않는다.
- worker/replica를 2개로 실행해도 캘린더 일일 동기화가 한 번만 수행된다.
- OCR provider 원문 예외가 API/SSE 응답에 포함되지 않는다.
- 운영 CORS가 승인된 프론트 origin만 허용한다.
- Docker build에서 설치된 LightFM 버전이 요구사항을 만족한다.
- 큰 파일 분리 후 기존 Agent/API 계약 테스트가 통과한다.
