# `EJ-pro` 코드 리뷰

## 리뷰 기준

- 기준 커밋: `origin/dev` / `ed128a972a2fe69936efd191333689bba63019b2`
- 담당 영역: PM, MCP, Google Calendar, 홈·캘린더 통합
- 확인 항목: 모듈화, 주석, 기능 응집도, 정확성·보안·운영 안정성

## 요약

| 항목 | 평가 | 핵심 의견 |
| --- | --- | --- |
| 모듈화 | 개선 필요 | Calendar API가 OAuth, 암호화, Google API, 동기화, 라우터를 모두 담당한다. |
| 주석 | 보통 | 멱등성 설명은 좋지만 token과 scheduler의 운영 전제가 빠져 있다. |
| 기능 응집도 | 개선 필요 | service가 API의 private 함수를 import하고 fallback 정책도 API에 섞여 있다. |
| 코드 품질 | 양호하나 운영 위험 존재 | 이벤트 중복 방지는 좋지만 멀티 worker와 secret 경계를 보완해야 한다. |

## 잘된 점

- `event_key`와 Google private extended property를 사용해 이벤트 생성·수정을 멱등하게 처리했다.
- 이벤트 키의 사용자 ID를 검증해 다른 사용자의 이벤트를 조작하지 못하게 한다.
- Calendar access/refresh token을 DB에 평문으로 저장하지 않는다.
- MCP 실패 시 직접 Google API를 사용하는 fallback이 있어 기능 가용성을 고려했다.

## 리뷰 발견사항

### P1. 캘린더 일일 작업이 worker마다 실행될 수 있음

- 위치: `app/backend/main.py:66-75`, `app/backend/services/calendar_job.py:40-49`
- FastAPI startup마다 무한 루프 task를 만든다.
- Uvicorn worker나 container replica가 늘어나면 같은 동기화가 동시에 실행될 수 있다.
- 별도 scheduler/worker로 옮기거나 DB·Redis distributed lock을 적용한다.

### P1. Calendar API의 책임이 과도함

- 위치: `app/backend/api/calendar/calendar_api.py:25-626`
- 한 파일이 암복호화, token refresh, event payload, Google HTTP 호출, DB 기록, route를 담당한다.
- `calendar_job.py:7`은 API의 `_get_access_token`, `_sync_daily_events`를 직접 import해 계층 방향도 뒤집혀 있다.
- 우선 private 함수를 `calendar_service.py`와 `google_calendar_gateway.py`로 옮기고 기존 route signature는 유지한다.

### P1. Google access token의 외부 실행 경계 전달

- 위치: `app/backend/services/calendar_mcp_client.py:56-86`, `ai/calendar/runpod_server.py:100-136`
- Google access token이 RunPod tool argument로 전달된다.
- RunPod가 신뢰되는 내부 경계인지, 요청·오류 로그에서 token이 제거되는지 명시하고 검증해야 한다.

### P2. 암호화 키가 JWT secret에 결합됨

- 위치: `app/backend/api/calendar/calendar_api.py:25-27`
- JWT secret을 바꾸면 기존 Calendar token을 복호화하지 못한다.
- 별도의 버전형 암호화 키와 회전 정책을 사용한다.

### P2. DNS rebinding 보호 비활성화

- 위치: `ai/calendar/runpod_server.py:94`
- 공개 네트워크에 노출되는 구성이라면 `enable_dns_rebinding_protection=False`를 재검토한다.

## 주석 개선

다음 내용은 코드 주석 또는 운영 문서에 명시하는 것이 좋다.

- scheduler는 전역에서 한 번만 실행돼야 한다는 전제
- MCP로 token을 전달하는 신뢰 경계와 masking 정책
- 암호화 키 회전 시 기존 token 처리 방법
- MCP fallback이 실행되는 오류 조건과 재시도 정책

긴 함수의 각 단계를 주석으로 늘리기보다 작은 service/gateway 함수로 분리하는 것이 우선이다.

## 권장 작업 순서

- [ ] Calendar scheduler 단일 실행 보장
- [ ] `calendar_service.py`로 OAuth·동기화 use case 이동
- [ ] `google_calendar_gateway.py`로 Google HTTP 호출 이동
- [ ] Calendar 암호화 키를 JWT secret과 분리
- [ ] RunPod token masking·권한·네트워크 설정 검증
- [ ] 멀티 worker에서 동기화가 한 번만 실행되는 테스트 추가

## 완료 기준

- worker/replica를 2개로 실행해도 일일 동기화가 한 번만 수행된다.
- API module이 service의 private 구현을 제공하지 않는다.
- JWT secret 회전 후에도 기존 Calendar token 처리 전략이 명확하다.
- RunPod와 애플리케이션 로그에 Google access token이 남지 않는다.
