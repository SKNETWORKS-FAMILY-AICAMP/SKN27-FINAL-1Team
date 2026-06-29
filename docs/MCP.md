# MCP 정리

## 공식 문서 기준

- 현재 의존성은 `mcp>=1.27.0,<2.0.0`으로 v1 SDK를 고정한다. 공식 Python SDK README도 v2 안정화 전에는 `<2` 상한을 두라고 안내한다.
- 운영 배포용 transport는 Streamable HTTP가 권장된다. FastMCP 서버는 `stateless_http=True, json_response=True` 조합이 권장값이다.
- 서버 도구는 `FastMCP` 인스턴스에 `@mcp.tool()`로 등록한다. 반환 타입이 `dict[str, Any]`처럼 타입 힌트가 있으면 structured output으로 내려간다.
- Streamable HTTP 클라이언트는 `streamable_http_client(url, http_client=...)`로 연결하고, headers/timeout은 `httpx.AsyncClient`에 설정한다. 이후 `ClientSession(read, write)` 생성, `await session.initialize()`, `session.call_tool(...)` 순서로 사용한다.
- Streamable HTTP 기본 endpoint는 `/mcp`다. 브라우저 MCP 클라이언트가 직접 붙는 경우에만 CORS와 `Mcp-Session-Id` 노출 설정이 추가로 필요하다.

공식 근거:

- https://github.com/modelcontextprotocol/python-sdk
- https://modelcontextprotocol.io/docs/develop/build-client

## 우리 코드 구조

- MCP 서버: `ai/calendar/runpod_server.py`
  - Runpod에서 `uvicorn ai.calendar.runpod_server:app --host 0.0.0.0 --port 8000`로 실행한다.
  - `FastMCP("bobbeori-calendar", stateless_http=True, json_response=True)` 기반 Streamable HTTP 서버다.
  - `/mcp` 요청은 `RUNPOD_INTERNAL_TOKEN`과 `X-Internal-Token` 헤더가 일치해야 통과한다.
  - 제공 도구는 `create_calendar_event`, `delete_calendar_event`다.
  - 도구 내부에서 Google Calendar API를 호출해 `bobbeoriKey` 기준으로 기존 일정을 조회하고, 있으면 변경분만 patch/delete, 없으면 post 한다.
- MCP 클라이언트: `app/backend/services/calendar_mcp_client.py`
  - `RUNPOD_CALENDAR_MCP_URL`이 없으면 MCP를 건너뛰고 기존 백엔드 Google Calendar 직접 호출 경로로 fallback 한다.
  - headers/timeout을 넣은 `httpx.AsyncClient`를 `streamable_http_client`에 전달해 Runpod `/mcp` endpoint에 붙고 `ClientSession.initialize()` 후 `create_calendar_event` 도구를 호출한다.
  - `structuredContent`를 우선 읽고, 없으면 텍스트 JSON fallback을 파싱한다.
- 호출 흐름: `app/backend/api/calendar/calendar_api.py`
  - `_create_event_once()`가 먼저 MCP를 호출한다.
  - MCP 성공 시 DB 로그를 남기고 반환한다.
  - MCP URL 미설정, SDK 미설치, 네트워크 실패, 도구 실패 시 기존 HTTP 직접 호출 로직으로 처리한다.
  - `_sync_daily_events()`는 일일 이벤트 3종을 다시 계산하고, 이번 계산에서 빠진 `bobbeoriKey`는 삭제한다.

## 체크 결과

- 맞는 부분: FastMCP 사용, `@mcp.tool()` 도구 등록, Streamable HTTP `/mcp`, `ClientSession.initialize()`, `call_tool()`, structured output 파싱은 공식 SDK 흐름과 맞다.
- 수정한 부분: 클라이언트를 공식 문서명인 `streamable_http_client`로 바꾸고, headers/timeout은 `httpx.AsyncClient`에 넣어 전달하도록 변경했다.
- 수정한 부분: 서버에 공식 권장값 `json_response=True`를 추가했다.
- 수정한 부분: `TransportSecuritySettings` import를 SDK 공개 모듈 경로로 바꿨다.

## 캘린더 이벤트 수정/삭제 기준

공통 기준:

- 같은 `bobbeoriKey` 이벤트가 다시 계산됐을 때 생성 조건이 유지되면 수정한다.
- 같은 `bobbeoriKey` 이벤트가 다시 계산됐을 때 생성 조건이 사라졌으면 삭제한다.
- 삭제/수정 대상은 우리가 만든 `bobbeoriKey`가 있는 일정으로 제한한다.
- 과거 일정은 자동 삭제하지 않고, 오늘 이후 일정만 정리한다.

| event_key | 메시지 | 수정 기준 | 삭제 기준 |
| --- | --- | --- | --- |
| `ingredient-expiry-{user_id}-{date}` | `{재료명} 오늘까지/며칠 안에 사용 추천` | 임박 재료 목록, 가장 빠른 소비기한, 표시명이 바뀐 경우 | 해당 날짜 기준 오늘부터 3일 안 소비기한 임박 재료가 0개가 된 경우. 예: 재료 삭제, `used` 처리, 소비기한 변경, 냉장고에서 빠짐 |
| `today-menu-{user_id}-{date}` | `저녁 추천: {레시피명}` | 최신 추천 레시피가 다른 레시피로 바뀐 경우 | 추천 결과가 없거나 추천 레시피가 삭제된 경우 |
| `recipe-delete-{user_id}-{date}` | `{레시피명} 삭제 예정` | 삭제 예정 레시피 목록 또는 대표 레시피명이 바뀐 경우 | 해당 날짜에 삭제 예정인 저장 레시피가 0개가 된 경우. 예: 이미 삭제됨, 보관 정책 변경, 추천 결과 row 삭제 |
| `receipt-cost-{user_id}-{receipt_id}` | `식재료 사용비용 {금액}원` | 영수증 총액, 구매 시간, 확정 품목 수가 바뀐 경우 | 영수증/입고 기록이 삭제됐거나, 총액이 0원이 됐거나, 사용자가 캘린더 비용 기록을 끈 상태로 해당 영수증을 다시 확정한 경우 |

## 의도적으로 안 한 것

- MCP OAuth 리소스 서버 구현은 안 했다. 지금 구조는 백엔드가 이미 Google access token을 보유하고 내부 토큰으로 Runpod MCP를 보호하므로 중복이다.
- MCP resources/prompts는 안 만들었다. 현재 기능은 캘린더 쓰기 하나라 tool 하나가 맞다.
- 커스텀 MCP 저수준 서버 구현은 안 했다. FastMCP가 표준 보일러플레이트를 대신 처리한다.
