# SKN27-FINAL-1Team

### 폴더별 담당 및 내용

```
ai       : AI/OCR/추천 실험 공간
app      : 실제 서비스 프론트·백엔드 코드 공간
docs     : 기획서, WBS, API, ERD, 그래프 설계 문서 공간
etl      : 데이터 수집, 전처리, Neo4j 적재 스크립트 공간
storage  : 원본/가공 데이터, mock 데이터, Neo4j import 파일 보관 공간
test     : 단위/통합/E2E 테스트와 테스트 샘플 데이터 공간
```

### 폴더 구조

```
root/
├─ ai/                              (AI, OCR, 추천 모델/Agent 실험 코드 공간)
│  ├─ agents/                       (서비스 내부 Agent 로직을 분리해 관리)
│  │  ├─ normalize_agent/           (식재료명 정규화 Agent 작업 공간)
│  │  ├─ inventory_agent/           (냉장고 재고 분석 Agent 작업 공간)
│  │  └─ recipe_agent/              (레시피 추천 Agent 작업 공간)
│  ├─ ocr/                          (박준희 담당 / 영수증 OCR 모델·파싱 실험 공간)
│  ├─ recommendation/               (김경수 담당 / 레시피 추천 로직·ML 실험 공간)
│  ├─ experiments/                  (공용 / 임시 실험, PoC 코드 보관 공간)
│  └─ requirements.txt              (AI/OCR용 의존성)
│
├─ app/                             (실제 서비스 애플리케이션 코드 공간)
│  ├─ backend/                      (백엔드 API, DB, 서비스 로직 작업 공간)
│  │  ├─ api/                       (기능별 API 라우터 관리)
│  │  │  ├─ auth/                   (김재묵 담당 / 로그인·인증 API)
│  │  │  ├─ inventory/              (김재묵 담당 / 냉장고 재고 관리 API)
│  │  │  ├─ receipts/               (박준희 담당 / 영수증 OCR 업로드·결과 API)
│  │  │  ├─ guide/                  (김주영 담당 / 보관·손질·신선도 API)
│  │  │  └─ recipes/                (김경수 담당 / 레시피 조회·추천 API)
│  │  ├─ core/                      (공용 / 환경설정, 보안, 공통 설정)
│  │  ├─ db/                        (공용 / RDB 연결, 세션, 마이그레이션)
│  │  ├─ schemas/                   (공용 / 요청·응답 DTO, 데이터 스키마)
│  │  ├─ services/                  (기능별 비즈니스 로직)
│  │  │  ├─ auth_service/           (김재묵 담당 / 인증 처리 로직)
│  │  │  ├─ inventory_service/      (김재묵 담당 / 냉장고 재고 처리 로직)
│  │  │  ├─ receipt_ocr_service/    (박준희 담당 / OCR 결과 처리 로직)
│  │  │  ├─ guide_service/          (김주영 담당 / 가이드 조회 로직)
│  │  │  └─ recommendation_service/ (김경수 담당 / 추천 계산 로직)
│  │  ├─ requirements.txt           (백엔드 Web용 의존성)
│  │  └─ Dockerfile                 (백엔드 전용 빌드 명세서)
│  │
│  └─ frontend/                     (프론트엔드 화면과 UI 작업 공간)
│     ├─ pages/                     (페이지 단위 화면 관리)
│     │  ├─ home/                   (이재희 담당 / 홈 대시보드 화면)
│     │  ├─ fridge/                 (김재묵 담당 / 냉장고 관리 화면)
│     │  ├─ fridge_recipe/          (김재묵 담당 / 냉장고파먹기 추천 화면)
│     │  ├─ receipt_ocr/            (박준희 담당 / 영수증 업로드·결과 확인 화면)
│     │  ├─ guide/                  (김주영 담당 / 식재료 가이드 화면)
│     │  ├─ info/                   (공용 / 서비스 안내 화면)
│     │  ├─ login/                  (공용 / 로그인 화면)
│     │  ├─ menu_recommend/         (김경수 담당 / 메뉴 추천 화면)
│     │  ├─ mypage/                 (공용 / 마이페이지 화면)
│     │  ├─ recipe_recommend/       (김경수 담당 / 레시피 추천 화면)
│     │  ├─ recipe_list/            (김경수 담당 / 레시피 목록 조회 화면)
│     │  ├─ recipe_detail/          (김경수 담당 / 레시피 상세 화면)
│     │  └─ shopping_list/          (공용 / 장보기 목록 화면)
│     ├─ components/                (공용 / Header, Breadcrumbs, Dialog 등 재사용 UI 컴포넌트)
│     │  └─ modals/                 (공용 / 확인, 재료 수정, 통계 모달)
│     ├─ mock/                      (공용 / 프론트 화면용 mock 데이터)
│     ├─ data/                      (공용 / 화면에서 사용하는 정적 데이터)
│     ├─ services/                  (공용 / 프론트 API 호출 함수)
│     ├─ stores/                    (공용 / 상태관리)
│     ├─ assets/                    (공용 / 로고, 마스코트, 추출 이미지 등 정적 리소스)
│     │  ├─ extracted/              (공용 / 추출 이미지 리소스)
│     │  └─ fonts/                  (공용 / 웹폰트)
│     ├─ public/                    (공용 / 빌드 시 그대로 제공되는 정적 파일)
│     └─ .env.sample                (공용 / 환경 변수 파일)
│
├─ docs/                            (기획, 설계, 회의 문서 관리 공간)
│  ├─ planning/                     (공용 / 프로젝트 주제, 기능 정의, 기획서)
│  ├─ wbs/                          (공용 / WBS, 일정표, 역할 분담표)
│  ├─ api/                          (공용 / API 명세서)
│  ├─ erd/                          (공용 / RDB 테이블 설계)
│  ├─ graph_schema/                 (김경수·김주영 담당 / Neo4j 그래프 구조 설계)
│  ├─ data_dictionary/              (공용 / 컬럼 정의, 데이터 사전)
│  └─ meeting_notes/                (공용 / 회의록, 피드백 기록)
│
├─ etl/                             (데이터 수집·전처리·적재 스크립트 공간)
│  ├─ recipe/                       (김경수 담당 / 레시피 데이터 처리)
│  │  ├─ profiling/                 (김경수 담당 / 원본 컬럼 분석)
│  │  ├─ preprocessing/             (김경수 담당 / 레시피 데이터 전처리)
│  │  └─ load_to_neo4j/             (김경수 담당 / 레시피 데이터 Neo4j 적재)
│  ├─ food_guide/                   (김주영 담당 / 가이드 데이터 수집·검수)
│  │  ├─ collection/                (김주영 담당 / 보관·손질·세척 정보 수집)
│  │  ├─ validation/                (김주영 담당 / 수집 데이터 검수)
│  │  └─ load_to_neo4j/             (김주영 담당 / 가이드 데이터 Neo4j 적재)
│  ├─ receipt_samples/              (박준희 담당 / OCR 테스트용 영수증 샘플 관리)
│  └─ requirements.txt              (데이터 수집/적재용 의존성)
│
├─ storage/                         (원본·가공 데이터와 Neo4j 파일 보관 공간)
│  ├─ raw/                          (원본 데이터 보관)
│  │  ├─ recipe/                    (김경수 담당 / 원본 레시피 데이터)
│  │  ├─ food_guide/                (김주영 담당 / 원본 가이드 수집 데이터)
│  │  └─ receipts/                  (박준희 담당 / 원본 영수증 이미지·텍스트)
│  ├─ processed/                    (전처리 완료 데이터 보관)
│  │  ├─ recipe/                    (김경수 담당 / 전처리된 레시피 데이터)
│  │  ├─ food_guide/                (김주영 담당 / 검수된 가이드 데이터)
│  │  └─ receipts/                  (박준희 담당 / 구조화된 OCR 결과)
│  ├─ neo4j/                        (Neo4j 적재/백업 관련 파일)
│  │  ├─ import/                    (김경수·김주영 담당 / Neo4j import CSV)
│  │  ├─ cypher/                    (김경수·김주영 담당 / Cypher 쿼리)
│  │  └─ backups/                   (공용 / Neo4j 백업 파일)
│  └─ mock/                         (공용 / API 개발용 mock 데이터)
│
├─ test/                            (테스트 코드와 테스트 데이터 공간)
│  ├─ unit/                         (각 담당자 / 함수 단위 테스트)
│  ├─ integration/                  (공용 / API·DB 연동 테스트)
│  ├─ e2e/                          (공용 / 사용자 흐름 기반 통합 테스트)
│  ├─ fixtures/                     (테스트용 샘플 데이터)
│  │  ├─ receipts/                  (박준희 담당 / OCR 테스트 샘플)
│  │  ├─ recipe/                    (김경수 담당 / 추천 테스트 샘플)
│  │  └─ food_guide/                (김주영 담당 / 가이드 테스트 샘플)
│  └─ api/                          (공용 / API 요청·응답 테스트)
│
├─ .env.sample
├─ .gitignore
├─ docker-compose.yml
└─ README.md                        (공용 / 프로젝트 소개, 실행 방법, 폴더 설명)
```
