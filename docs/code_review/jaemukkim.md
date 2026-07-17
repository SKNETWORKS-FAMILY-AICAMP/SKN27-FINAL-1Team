# `jaemukkim` 코드 리뷰

## 리뷰 기준

- 기준 커밋: `origin/dev` / `ed128a972a2fe69936efd191333689bba63019b2`
- 담당 영역: FastAPI Backend, 인증, 채팅 Supervisor, 냉장고 재고
- 확인 항목: 모듈화, 주석, 기능 응집도, 정확성·보안·운영 안정성

## 요약

| 항목 | 평가 | 핵심 의견 |
| --- | --- | --- |
| 모듈화 | 기반 양호, 일부 분리 필요 | API·schema·service 구조는 좋지만 Supervisor utility가 너무 많은 역할을 가진다. |
| 주석 | 양호 | 함수 의도가 잘 드러나지만 보안 제약은 주석이 아닌 실행 검사로 강제해야 한다. |
| 기능 응집도 | 개선 필요 | inventory의 commit 책임과 Supervisor routing·formatting이 상위 흐름 조합을 어렵게 한다. |
| 코드 품질 | 배포 전 보안 수정 필수 | 공개 개발 로그인과 기본 JWT key는 릴리스 차단 항목이다. |

## 잘된 점

- Backend가 API, schema, service, DB model로 나뉘어 있다.
- inventory service가 이름 정규화, 저장 규칙, 응답 mapping을 private helper로 분리했다.
- 식재료 master 생성 시 nested transaction과 `IntegrityError` 재조회를 사용한다.
- Supervisor 세션 metadata, Agent 오류 변환 등 계약 테스트가 존재한다.
- 재고 service와 Supervisor의 docstring·섹션 구분이 읽기 쉽다.

## 리뷰 발견사항

### P0. 인증 없는 개발용 로그인

- 위치: `app/backend/api/auth/auth_api.py:66-81`
- `/dev-login`은 환경 검사나 인증 없이 고정 개발 사용자로 실제 JWT를 발급한다.
- 운영에서는 route 등록 자체를 제외한다. UI에서 숨기는 것만으로는 부족하다.

### P0. 예측 가능한 JWT 기본 key

- 위치: `app/backend/core/config.py:31`, `app/backend/core/security.py:20,29,52,60`
- 환경변수가 없으면 `YOUR_JWT_SECRET_KEY_HERE`를 사용한다.
- 기본값을 제거하고 시작 시 secret 누락·길이를 검증한다.

### P1. 재고 service의 commit 때문에 상위 transaction이 깨짐

- 공동 담당: `enblav262`
- 위치: `app/backend/services/inventory_service/inventory_service.py:327-348`
- public service 메서드가 직접 commit해 장보기 같은 상위 use case가 transaction을 통제하지 못한다.
- transaction-aware 내부 메서드는 `flush()`만 하고 API/use case 경계가 commit하도록 정책을 통일한다.

### P1. 운영 CORS가 wildcard임

- 위치: `app/backend/main.py:29-35`
- `allow_origins=["*"]`와 `allow_credentials=True`가 전역 설정이다.
- 환경별 frontend origin allowlist를 사용하고 localhost는 개발 환경에서만 허용한다.

### P2. Supervisor utility의 책임이 과도함

- 위치: `ai/agents/supervisor_agent/supervisor_utils.py`
- intent 판별, 응답 formatting, history 상속, LLM payload parsing, alarm parsing, retry와 결과 병합이 약 850줄에 함께 있다.
- `routing_rules.py`, `conversation_context.py`, `response_mapper.py`, `agent_execution.py`로 점진적으로 나눈다.

### P2. 운영 관측성이 낮음

- broad exception과 `print` 사용이 있어 request/session 단위 추적이 어렵다.
- 구조화 logger와 correlation ID를 사용하고 client 응답과 내부 오류를 분리한다.

## 주석 개선

현재 설명 주석은 충분한 편이다. 다음은 주석 대신 코드로 강제해야 한다.

- “개발 환경 전용” → 운영에서 route 미등록
- “secret 필수” → startup validation
- “한 transaction” → commit 소유 정책과 rollback test
- Agent fallback → 오류 코드와 구조화 log

Supervisor를 분리할 때는 각 모듈 상단에 입력·출력 계약과 context 상속 규칙만 짧게 남긴다.

## 권장 작업 순서

- [ ] 운영에서 `/dev-login` route 제외
- [ ] JWT secret 기본값 제거와 startup validation
- [ ] CORS 환경별 allowlist 적용
- [ ] inventory transaction 정책 정리
- [ ] 장보기 부분 실패 rollback test 공동 작성
- [ ] Supervisor utility를 네 역할로 점진 분리
- [ ] `print`를 구조화 logger로 교체

## 완료 기준

- 운영 환경에서 `/dev-login`이 404이거나 route에 등록되지 않는다.
- JWT secret이 없으면 애플리케이션이 즉시 시작 실패한다.
- 장보기 다건 입고 실패 시 재고와 목록이 모두 rollback된다.
- 운영 CORS는 승인된 frontend origin만 허용한다.
- Supervisor 모듈이 routing, context, response, execution 경계로 나뉜다.
