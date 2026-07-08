# 폴더별 파일 분석

작성일: 2026-07-07

목적: 현재 코드베이스를 PM 관점에서 폴더별/파일별로 나눠 역할과 수정 필요 지점을 정리한다. 코드 변경 없이 분석만 기록한다.

분석 기준:
- `node_modules`, `dist`, `__pycache__`, 폰트/이미지 빌드 산출물은 개별 분석에서 제외했다.
- `assets/extracted/ingredients/*.png`처럼 수백 개의 정적 재료 이미지는 파일 묶음으로 분석했다.
- 우선순위는 `P0` 즉시 정리, `P1` 발표/베타 전 정리, `P2` 후속 개선으로 구분했다.

## 전체 구조 요약

| 폴더 | 확인 파일 수 | 소스/문서성 파일 수 | PM 관점 |
|---|---:|---:|---|
| `app/backend` | 79 | 69 | API, DB, 서비스 로직의 중심. 운영 보안과 스케줄러 정책 정리가 필요하다. |
| `app/frontend` | 566 | 73 | 실제 사용자 경험의 중심. 장보기 노출 수준과 홈 메시지 정리가 필요하다. |
| `ai` | 27 | 20 | Agent, MCP, RunPod 코드. 알림/캘린더는 작동 흐름이 있으나 빈 agent 폴더가 남아 있다. |
| `test` | 43 | 36 | 기능/API/fixture 테스트가 많다. 일부 테스트 파일명과 실제 내용이 안 맞는다. |
| `docs` | 13 | 13 | 발표/설계 문서가 모여 있다. 최신화 기준을 하나로 묶을 필요가 있다. |
| `.github` | 1 | 1 | pytest CI만 있다. 프론트 빌드 검증이 빠져 있다. |

## `app/backend`

### 루트

| 파일 | 역할 | PM 피드백 |
|---|---|---|
| `app/backend/main.py` | FastAPI 앱 생성, 라우터 등록, CORS, 시작/종료 이벤트, 헬스 체크. | `P0` CORS `*`, Swagger 상시 공개, 오전 7시 캘린더 잡 자동 실행 정책을 운영 기준으로 분리해야 한다. worker 여러 개면 캘린더 동기화가 중복될 수 있다. |
| `app/backend/requirements.txt` | 백엔드 Python 의존성. | `P1` 발표/배포 문서와 실제 설치 기준을 맞춰야 한다. pytest도 여기 기준으로 설치된다. |
| `app/backend/Dockerfile` | 백엔드 컨테이너 빌드 설정. | `P1` 운영 배포 시 env 필수값 검증과 실행 명령을 문서화해야 한다. |
| `app/backend/__init__.py` | 패키지 인식용. | 별도 수정 필요 없음. |

### `core`

| 파일 | 역할 | PM 피드백 |
|---|---|---|
| `app/backend/core/config.py` | DB, OAuth, OpenAI, RunPod, OCR 등 환경변수 관리. | `P0` `DEV_MODE=True`, 기본 JWT secret은 운영 리스크다. 운영에서는 기본값이면 서버 시작 실패하도록 정책을 잡는 게 좋다. |
| `app/backend/core/security.py` | JWT access/refresh token 생성과 검증. | `P1` 토큰 만료/회전 정책을 발표 자료에 명확히 적어야 한다. 현재는 로그인 JWT와 내부 MCP 토큰 역할이 다르다. |

### `db`

| 파일 | 역할 | PM 피드백 |
|---|---|---|
| `app/backend/db/models.py` | 사용자, OAuth, 캘린더, 재료, 영수증, 레시피, 장보기, 추천, 알림 테이블 모델. | `P1` ERD/DB 문서와 맞춰야 한다. 장보기 테이블이 있으므로 "개발 중/Beta"로 표시할지 기능 완료로 볼지 결정 필요. |
| `app/backend/db/session.py` | PostgreSQL 세션 생성/주입. | 별도 PM 이슈는 적다. DB 연결 실패 시 운영 안내 문서만 필요. |
| `app/backend/db/neo4j_session.py` | Neo4j 드라이버 싱글턴과 세션 주입. | `P1` Neo4j가 필수인지 선택인지 명확히 해야 한다. 로컬/운영 장애 시 fallback 정책 필요. |
| `app/backend/db/base.py` | SQLAlchemy Base 공유. | 수정 필요 없음. |

### `api`

| 파일/폴더 | 역할 | PM 피드백 |
|---|---|---|
| `app/backend/api/deps.py` | 인증 의존성. optional/required 사용자 구분. | `P1` optional auth는 챗봇/공개 조회에만 써야 한다. 토큰이 틀렸는데 guest로 처리되는 UX/보안 정책을 명확히 해야 한다. |
| `app/backend/api/auth/auth_api.py` | 소셜 로그인, 내 정보 조회, dev-login. | `P0` `/auth/dev-login`은 운영 노출 금지. `DEV_MODE`에서만 등록하거나 제거해야 한다. |
| `app/backend/api/auth/auth_mock.py` | Mock auth API. | `P1` 현재 `main.py`에 연결되어 있지 않다면 유지 이유를 문서화하거나 제거 후보로 둔다. |
| `app/backend/api/calendar/calendar_api.py` | Google Calendar 연결, 조회, 삭제, 테스트 이벤트, bobbeoriKey 필터. | `P0` 사용자의 개인 캘린더 전체를 건드리지 않는 정책이 중요하다. bobbeoriKey 필터/삭제 제한을 발표 핵심으로 잡으면 좋다. |
| `app/backend/api/chat/chat_api.py` | 챗봇 메시지 API. | `P1` optional auth 사용 중이라 로그인 사용자/게스트 응답 차이를 테스트와 UX 문구로 분리해야 한다. |
| `app/backend/api/guide/guide_api.py` | 식재료 가이드 목록/상세/카테고리/제안. | `P1` 공개 조회와 로그인 필요 제안 API 구분이 잘 보이도록 API 정책표에 넣기 좋다. |
| `app/backend/api/inventory/inventory_api.py` | 냉장고 재료 CRUD, 예측, 요약. | 핵심 기능으로 발표 가능. 다만 프론트와 API 용어를 "냉장고 재료"로 통일하면 좋다. |
| `app/backend/api/notifications/notifications_api.py` | 알림 목록, 읽음 처리, 디바이스 토큰 등록. | `P1` 실제 푸시 발송까지 되는지, 캘린더 알림과 앱 알림의 차이를 문서화해야 한다. |
| `app/backend/api/onboarding/onboarding_api.py` | 선호/비선호/알레르기/알림 설정 저장. | 핵심 개인화 설정. 발표에서는 추천 품질과 연결해서 설명하면 좋다. |
| `app/backend/api/receipts/receipts_api.py` | 영수증 OCR 업로드, 스트림, 확정, 이력 수정/삭제. | `P1` 파일 업로드 보안 정책이 잘 드러나는 API다. 트러블슈팅 슬라이드 근거로 좋다. |
| `app/backend/api/recipes/recipes_api.py` | 레시피 검색, 추천, 상세. | 공개 검색/로그인 추천/선택 인증 상세가 잘 나뉜다. API 인증 정책 예시로 쓰기 좋다. |
| `app/backend/api/recommendations/recommendations_api.py` | 추천 레시피 저장/조회/삭제. | 로그인 필수 기능. "추천은 볼 수 있지만 저장은 로그인 필요" 정책으로 설명 가능. |
| `app/backend/api/shopping/shopping_api.py` | 장보기 목록 생성/조회/수정/구매완료/가격비교/mock. | `P0` 아직 개발 완료가 아니라면 홈/네비게이션에서 핵심 기능처럼 노출하지 않는 게 안전하다. API가 있으니 "Beta"로 분리하는 선택지도 있다. |
| `app/backend/api/admin/` | 현재 소스 파일 없음. | `P2` 빈 폴더면 제거하거나 관리자 기능 예정 문서에만 남긴다. |

### `services`

| 파일/폴더 | 역할 | PM 피드백 |
|---|---|---|
| `app/backend/services/calendar_job.py` | 매일 오전 7시 Google Calendar 동기화 루프. | `P0` 운영에서 단일 실행 보장 필요. cron/worker/env flag 중 하나를 선택해야 한다. |
| `app/backend/services/calendar_mcp_client.py` | RunPod Serverless calendar tool 호출. | `P1` RunPod 실패와 실제 캘린더 성공을 사용자 메시지에서 분리해야 한다. |
| `app/backend/services/ingredient_match_service.py` | OCR/입력 재료명을 Neo4j 기준명과 매칭. | `P1` 재료명 정규화 품질은 OCR-냉장고 연결의 핵심이다. 실패율/대표 예시를 발표 자료에 넣으면 좋다. |
| `auth_service/oauth.py` | Kakao/Naver/Google OAuth 프로필 조회. | `P1` Google Play 프로덕션 심사와 OAuth redirect URI 환경별 관리 필요. |
| `auth_service/auth_service.py` | 소셜 사용자 가입/로그인, JWT 발급. | `P1` 계정 통합 정책(provider별 중복 이메일 처리)을 결정하면 좋다. |
| `inventory_service/inventory_service.py` | 냉장고 CRUD, 보관방식, 유통기한 계산, 이름 기반 조작. | 핵심 서비스. 다만 함수가 커져 유지보수 리스크가 있으니 추후 상태 계산/CRUD 분리를 고려. |
| `inventory_service/expiration_ai_service.py` | 재료 보관/소비기한 예측. | `P1` AI 예측인지 룰 기반인지 사용자에게 설명해야 한다. 틀릴 수 있는 예측에는 "추천값" 표현이 안전하다. |
| `inventory_service/inventory_seed.py` | 기본 재료/보관 기준 seed. | `P1` 서버 시작 때 seed가 도는 구조라 운영 DB에서 반복 실행 영향이 없는지 확인 필요. |
| `onboarding_service/onboarding_service.py` | 사용자 온보딩 설정 저장/조회. | 발표에서는 개인화 추천의 입력값으로 연결. |
| `receipt_ocr_service/receipt_ocr_service.py` | 파일 검증, 이미지 정제, OCR, 품질 검증, 재시도, 저장 응답 생성. | `P1` 가장 좋은 트러블슈팅 소재다. 파일 보안, MIME/시그니처, 크기 제한, 비영수증 거절을 슬라이드에 정리. |
| `receipt_ocr_service/receipt_confirm_service.py` | OCR 후보 확정 후 영수증/냉장고 저장. | `P1` 개인 정보 마스킹과 저장 범위가 중요하다. |
| `receipt_ocr_service/receipt_history_service.py` | 영수증 이력 조회/수정/삭제. | `P1` 업로드 파일 삭제 범위가 안전한지 계속 테스트로 묶어야 한다. |
| `receipt_ocr_service/privacy_masking.py` | 민감값 마스킹. | `P1` 발표에서 "저장 전 마스킹" 근거로 사용 가능. |
| `recommendation_service/*` | 레시피 검색, 상세, 추천 랭킹, 냉장고 매칭, 리뷰 점수, 필터링. | 핵심 기술 파트. 추천 점수 산식과 fallback을 한 장으로 요약하면 좋다. |
| `shopping_service/*` | 장보기 목록, 네이버 쇼핑 검색 provider. | `P0` 기능 완료 전이면 테스트/노출/문서에서 Beta로 다뤄야 한다. |
| `guide_service/guide_service.py` | 식재료 가이드 조회. | Neo4j/식재료 가이드 파트와 연결해 발표 가능. |

### `schemas`

| 파일/폴더 | 역할 | PM 피드백 |
|---|---|---|
| `app/backend/schemas/*.py` | API request/response 계약. | `P1` 멀티 에이전트 공통 JSON과 API 응답 계약을 문서로 맞춰야 한다. |
| `app/backend/schemas/schema.sql` | 실제 DB 스키마 기준. | `P1` DB 설계 문서/ERD와 현재 테이블이 일치하는지 발표 전 재확인. |
| `app/backend/schemas/migrations/20260707_add_shopping_tables.sql` | 장보기 테이블 migration. | `P1` 장보기 Beta 여부와 함께 migration 적용 절차를 문서화해야 한다. |

## `app/frontend`

### 루트

| 파일 | 역할 | PM 피드백 |
|---|---|---|
| `app/frontend/App.jsx` | 라우팅, 약관/개인정보 모달, 온보딩 표시. | `P0` 서비스 설명에 장보기 목록이 핵심 기능처럼 포함된다. 장보기 완료 전이면 문구 조정 필요. |
| `app/frontend/main.jsx` | React 앱 진입점. | 수정 필요 낮음. |
| `app/frontend/index.css` | 전역 스타일. | `P2` 디자인 톤 정리 시 공통 토큰화 여지 있음. |
| `app/frontend/package.json` | 프론트 의존성/스크립트. | `P1` CI에서 `npm run build`를 실행하도록 연결 필요. |
| `app/frontend/vite.config.js` | Vite 설정. | 운영 API URL/env 기준 문서화 필요. |
| `app/frontend/.env.sample` | 프론트 환경변수 샘플. | `P1` 로컬/배포 환경변수 예시 최신화 필요. |
| `app/frontend/Dockerfile` | 프론트 컨테이너 빌드. | 배포 시 nginx/static serving 방식과 API URL 주입 방식을 정리해야 한다. |

### `components`

| 파일/폴더 | 역할 | PM 피드백 |
|---|---|---|
| `Header.jsx`, `MobileBottomNav.jsx`, `Footer.jsx` | 전역 네비게이션/푸터. | `P0` 장보기 링크가 상시 노출된다. 완성 전이면 숨기거나 Beta 표기. |
| `FloatingChatbot.jsx` | 플로팅 챗봇 UI, `/api/v1/chat` 호출. | `P1` 로그인/게스트 응답 차이와 agent action UI를 더 명확히 보여줄 필요가 있다. |
| `ChatWelcome.jsx` | 챗봇 초기 안내/추천 질문. | `P1` 실제 처리 가능한 질문만 노출해야 한다. |
| `OnboardingModal.jsx` | 최초 선호/알레르기/알림 설정. | 개인화 추천의 시작점. 발표 흐름에 포함하면 좋다. |
| `AppDialog.jsx` | alert/confirm/prompt 공통 모달. | UX 일관성에 좋다. 과한 라이브러리 없이 잘 묶여 있다. |
| `Breadcrumbs.jsx` | 페이지 경로 표시. | 장보기 노출 정책과 함께 정리. |
| `modals/IngredientModal.jsx` | 재료 추가/수정 모달, 예측/추천 검색. | 핵심 UX. 자동 예측값이 틀릴 수 있음을 사용자에게 너무 확정적으로 보이지 않게 해야 한다. |
| `modals/ConfirmModal.jsx`, `StatsModal.jsx` | 확인/통계 모달. | 수정 필요 낮음. |

### `pages`

| 파일/폴더 | 역할 | PM 피드백 |
|---|---|---|
| `home/Home.jsx` | 홈 섹션 조립. | 발표 첫 화면. 핵심 메시지와 실제 구현 범위가 맞아야 한다. |
| `home/sections/HeroSection.jsx` | 메인 히어로/빠른 액션. | `P0` 장보기와 최저가 연결 문구가 강하다. 개발 완료 전이면 삭제/Beta 처리. |
| `home/sections/CoreFeatureSection.jsx` | 핵심 기능 카드. | `P0` "장보기 가격 비교"를 핵심 기능으로 보여준다. 완성도와 맞춰야 한다. |
| `home/sections/SolutionSection.jsx` | 전체 서비스 흐름과 기능 설명. | `P0` 등록-추천-장보기-알림 흐름에서 장보기를 확정 기능처럼 보여준다. |
| `home/sections/ReviewSection.jsx` | 사용자 후기 섹션. | `P1` 실제 리뷰가 아니면 "시나리오 예시"로 바꾸는 게 안전하다. |
| `home/sections/ProblemSection.jsx` | 사용자 문제 정의. | 발표 자료의 문제 인식과 잘 연결된다. |
| `home/sections/ReceiptAgentSection.jsx` | OCR 처리 강조 섹션. | OCR 트러블슈팅과 연결하면 좋다. |
| `home/sections/AgentPreviewSection.jsx` | Agent/화면 preview. | 실제 멀티 에이전트 구현 범위와 맞춰 표현해야 한다. |
| `home/sections/FaqSection.jsx` | FAQ. | 장보기 가능 범위 문구 확인 필요. |
| `fridge/Fridge.jsx` | 냉장고 목록/추가/수정/삭제/소비 처리. | 핵심 기능. 테스트와 발표 데모 우선순위 높음. |
| `receipt_ocr/ReceiptOcr.jsx` | 영수증 업로드/OCR/후보 확인/입고. | 핵심 데모. 파일 보안과 재시도 UX를 함께 보여주면 좋다. |
| `recipe_list/RecipeList.jsx` | 레시피 검색/필터/목록. | 공개 검색 기능으로 사용 가능. |
| `recipe_detail/RecipeDetail.jsx` | 상세, 보유/부족 재료, 저장, 장보기 연결. | `P0` 부족 재료 장보기 연결이 있으므로 장보기 Beta 정책과 맞춰야 한다. |
| `menu_recommend/MenuRecommend.jsx` | 메뉴 추천 화면. | 추천 시스템 발표에 적합. |
| `fridge_recipe/FridgeRecipe.jsx` | 냉장고파먹기 추천. | 서비스 핵심 흐름. |
| `guide/Guide.jsx` | 식재료 가이드 화면. | Neo4j/가이드 파트와 연결. |
| `shopping_list/ShoppingList.jsx` | 장보기 목록 UI, fallback 목록, 구매완료 입고. | `P0` 실제 개발 완료 전이면 사용자에게 "임시/Beta"임을 더 명확히 보여야 한다. |
| `mypage/Mypage.jsx` | 사용자 정보, 캘린더 연결, 설정. | 캘린더/알림 발표 데모 위치. |
| `login/Login.jsx`, `login/Callback.jsx` | 로그인 화면과 OAuth callback. | Google Play/OAuth 심사와 연결되는 파일. |
| `info/InfoPage.jsx`, `recipe_recommend/RecipeRecommend.jsx` | 보조 화면/추천 컴포넌트. | 발표 흐름에서 사용 여부 확인. |

### `services`, `utils`, `mock`, `assets`

| 파일/폴더 | 역할 | PM 피드백 |
|---|---|---|
| `services/shoppingApi.js` | 장보기 API client. | `P0` 장보기 Beta 정책과 맞춰 에러/임시 화면 문구를 정리해야 한다. |
| `utils/api.js` | API base URL. | 운영 URL 주입 방식 확인 필요. |
| `utils/savedRecipes.js` | 저장 레시피 localStorage/API 연동. | 서버 저장과 local fallback 정책이 사용자에게 혼란스럽지 않게 정리 필요. |
| `mock/*.js` | 데모/초기 화면용 mock 데이터. | `P1` 실제 API와 혼동되지 않도록 mock 사용 화면을 확인해야 한다. |
| `assets/extracted/icons`, `assets/extracted/images` | UI 아이콘/이미지. | 발표 화면 품질에 직접 영향. 미사용 자산 정리는 후순위. |
| `assets/extracted/ingredients/*.png` | 재료 이미지 자산 묶음. | 개별 분석 불필요. 재료명 매칭 실패 시 기본 이미지 fallback만 확인하면 된다. |
| `assets/fonts/*.woff2` | Pretendard 폰트. | 발표/배포 화면에서 폰트 로딩 확인. |
| `stores/` | 현재 분석 대상 파일 없음. | `P2` 빈 폴더면 제거하거나 상태관리 도입 시점에 다시 만들기. |

## `ai`

| 파일/폴더 | 역할 | PM 피드백 |
|---|---|---|
| `ai/README.md`, `ai/requirements.txt` | AI 모듈 설명/의존성. | 백엔드 requirements와 분리 기준을 문서화해야 한다. |
| `ai/calendar/runpod_server.py` | FastMCP 기반 Google Calendar create/delete tool 서버. | `P1` MCP 공식 SDK 기반 구현으로 설명 가능. `X-Internal-Token` 보안 이유를 발표에 넣기 좋다. |
| `ai/calendar/runpod_handler.py` | RunPod Serverless handler. 내부 토큰 검증 후 tool 실행. | `P1` "unknown tool", token 누락 실패가 사용자 성공/실패와 분리되도록 운영 로그 정책 필요. |
| `ai/calendar/Dockerfile`, `requirements.txt`, `README.md` | RunPod 배포 단위. | 배포 절차 문서와 실제 이미지 이름을 맞춰야 한다. |
| `ai/tools/fridge_mcp_tools.py` | 냉장고 조회/추가/소비/삭제/임박재료 tool. | Agent/Tool 분리 설명에 사용 가능. |
| `ai/tools/calendar_tools.py` | 단순 calendar tool 예시. | 실제 MCP/RunPod 경로와 겹치면 제거 후보. |
| `ai/agents/alarm_agent/alarm_agent.py` | 알림/캘린더 intent 분석, HITL 확인, 공통 JSON 응답. | `P1` 자연어 의도 애매함을 확인 단계로 넘기는 구조는 좋다. 다만 사용자 메시지/인코딩 렌더는 화면 기준 확인 필요. |
| `ai/agents/alarm_agent/tools.py` | alarm agent가 Google Calendar API를 호출하는 tool wrapper. | 캘린더 권한/토큰/삭제 제한 정책이 중요하다. |
| `ai/agents/alarm_agent/__init__.py` | alarm agent export. | 수정 필요 낮음. |
| `ai/agents/inventory_agent/inventory_agent.py` | 냉장고 agent 실행. | Supervisor에서 냉장고 기능 위임하는 근거. |
| `ai/agents/inventory_agent/inventory_utils.py` | 자연어 재료 추가/소비/보관 위치 파싱. | 규칙 기반 파싱의 한계를 테스트 케이스로 보완해야 한다. |
| `ai/agents/guide_agent/guide_agent.py` | 식재료 가이드 agent 응답 생성. | 가이드 기능을 agent로 확장하는 근거. |
| `ai/agents/supervisor_agent/supervisor_agent.py` | LangGraph 라우팅, intent별 agent node. | `P1` 멀티 에이전트라고 발표하려면 여기의 실제 라우팅 흐름을 기준으로 말해야 한다. |
| `ai/agents/supervisor_agent/supervisor_service.py` | ChatService, LLM/규칙 intent 분류, 응답 조립. | LLM key 없을 때 rule fallback이 있으므로 발표 데모 안정성에 좋다. |
| `ai/agents/supervisor_agent/supervisor_utils.py` | intent 보조 함수/키워드/응답 유틸. | 분류 기준이 흩어지지 않게 문서화 필요. |
| `ai/agents/recipe_agent/.gitkeep` | 자리만 있는 폴더. | `P2` 실제 agent가 없으면 발표에서 recipe agent라고 과하게 말하지 않기. |
| `ai/agents/normalize_agent/.gitkeep` | 자리만 있는 폴더. | `P2` 빈 폴더는 제거하거나 계획 기능으로 분리. |
| `ai/experiments/.gitkeep`, `ai/ocr/.gitkeep` | 빈 예정 폴더. | 발표/문서에서는 구현 완료로 언급하지 않기. |
| `ai/recommendation/__init__.py` | recommendation 패키지 자리. | 실제 추천 로직은 backend service 쪽에 있으므로 역할 혼동 주의. |

## `test`

| 파일/폴더 | 역할 | PM 피드백 |
|---|---|---|
| `test/README.md` | 테스트 안내. | 현재 실행 방법/분류와 맞는지 최신화 필요. |
| `test/test_alarm_agent.py` | alarm agent 단위 테스트. | 알림 intent/HITL 근거로 사용 가능. |
| `test/api/*` | FastAPI API 계약 테스트. | 발표에서 "API 단위 검증"으로 묶으면 좋다. |
| `test/features/*` | 기능 계약/A-B/매트릭스 테스트. | 기능 설명과 테스트 분류표를 최신화해야 한다. |
| `test/features/test_onboarding_shopping_feature_contract.py` | 실제 내용은 온보딩 선호/알림 동의 보존 테스트. | `P1` 파일명에 shopping이 남아 있어 혼란스럽다. 이름 정리 후보. |
| `test/fixtures/calendar/test_calendar_events.py` | 캘린더/MCP/bobbeoriKey/RunPod fixture 테스트. | 캘린더 발표 근거로 좋다. |
| `test/fixtures/ocr/test_receipt_ocr_flow.py` | OCR 보안/정규화/저장 흐름 테스트. | OCR 트러블슈팅 근거로 좋다. |
| `test/fixtures/chatbot/test_chatbot.py` | 챗봇 라우팅/응답 테스트. | 멀티 에이전트 발표 근거로 사용 가능. |
| `test/fixtures/fridge/*` | 냉장고 fixture 테스트. | 냉장고 핵심 기능 안정성 근거. |
| `test/unit`, `test/integration`, `test/e2e` | 현재 `.gitkeep`만 있음. | `P2` 비어 있으면 발표 자료에서 언급하지 않거나 향후 계획으로만 둔다. |

## `docs`

| 파일 | 역할 | PM 피드백 |
|---|---|---|
| `docs/pm_code_review_feedback.md` | PM 관점 우선순위 피드백. | 이번 분석의 요약본. |
| `docs/pm_folder_file_analysis.md` | 폴더/파일별 상세 분석. | 현재 문서. |
| `docs/MCP.md` | MCP 공식문서/코드 정리. | 캘린더/RunPod 발표 자료와 맞춰 최신화 유지. |
| `docs/backend_fastapi_guide.md` | 백엔드 구조 가이드. | 실제 장보기/알림 구현 상태와 다를 수 있어 재검토 필요. |
| `docs/test_presentation_summary.md` | 테스트 발표 정리. | `P1` 현재 테스트 수/분류 기준으로 재생성 필요. |
| `docs/chatbot_langgraph_mcp_plan.md` | 챗봇/LangGraph/MCP 계획. | 실제 구현된 supervisor/alarm agent와 맞춰 상태 업데이트 필요. |
| `docs/food_guide_*` | 식재료 가이드/Neo4j 작업 문서. | GraphDB 발표 파트의 근거. |
| `docs/food_guide_mcp_json_schema.md` | MCP JSON schema. | 공통 agent 응답 JSON과 맞춰야 한다. |
| `docs/inventory_ingredient_mapping.md` | 냉장고/재료 매핑. | OCR-냉장고 연결 설명에 사용 가능. |
| `docs/intent_router_benchmark.md` | intent router benchmark. | 챗봇 성능/라우팅 발표 자료로 사용 가능. |
| `docs/kickstarter.md`, `docs/README.md` | 실행/문서 인덱스. | 새 문서가 늘었으므로 나중에 인덱스 업데이트 권장. |

## `.github`

| 파일 | 역할 | PM 피드백 |
|---|---|---|
| `.github/workflows/pytest.yml` | PR/push 시 Python pytest 실행. | `P1` 백엔드 테스트만 돈다. 최소한 프론트 `npm run build`를 추가해야 화면 깨짐을 PR에서 잡을 수 있다. |

## 우선순위별 정리

### P0

1. 장보기 기능을 완성 기능처럼 보이는 홈/네비/상세 연결에서 숨김 또는 Beta 처리.
2. `/auth/dev-login` 운영 노출 방지.
3. 운영 환경에서 CORS, Swagger, JWT secret, `DEV_MODE` 기본값 정리.
4. 오전 7시 캘린더 동기화 잡의 중복 실행 방지.

### P1

1. 테스트 문서와 실제 테스트 파일 수/분류 최신화.
2. 프론트 빌드 CI 추가.
3. RunPod/MCP 실패 표기와 최종 사용자 성공 메시지 분리.
4. 실제 리뷰/예시 시나리오 문구 구분.
5. OAuth/Google Calendar 프로덕션 심사 문서와 env 정리.

### P2

1. 빈 폴더 정리: `ai/agents/recipe_agent`, `ai/agents/normalize_agent`, `ai/experiments`, `ai/ocr`, `test/unit`, `test/integration`, `test/e2e`.
2. mock 데이터와 실제 API 데이터 구분 문서화.
3. 발표용 문서 인덱스 정리.
