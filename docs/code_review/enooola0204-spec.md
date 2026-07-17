# `enooola0204-spec` 코드 리뷰

## 리뷰 기준

- 기준 커밋: `origin/dev` / `ed128a972a2fe69936efd191333689bba63019b2`
- 담당 영역: GraphDB, 영양 데이터, 식재료 가이드 Agent와 화면
- 확인 항목: 모듈화, 주석, 기능 응집도, 정확성·안전성·운영 안정성

## 요약

| 항목 | 평가 | 핵심 의견 |
| --- | --- | --- |
| 모듈화 | 개선 필요 | Guide Agent가 query parsing, DB, 웹 검색, 응답 표시를 모두 담당한다. |
| 주석 | 좋음 | 섹션과 안전 fallback 의도가 명확하다. 예외 로그는 보완이 필요하다. |
| 기능 응집도 | 개선 필요 | Agent가 repository와 presenter 역할까지 맡고 화면도 여러 API를 직접 조합한다. |
| 코드 품질 | 양호 | 식품 안전과 출처 검증이 좋으며 파일 크기와 관측성을 개선하면 된다. |

## 잘된 점

- 안전 민감 질문은 신뢰할 수 있는 domain 결과만 사용하고 근거가 없으면 보수적으로 응답한다.
- URL host를 단순 문자열 포함이 아닌 domain 규칙으로 검사한다.
- PostgreSQL session을 `finally`에서 닫고 SQL bind parameter를 사용한다.
- `build_guide_response()`로 Agent 응답 계약을 중앙화했다.
- 가이드 설계·품질·응답 관련 문서가 비교적 풍부하다.

## 리뷰 발견사항

### P2. Guide Agent의 책임이 과도함

- 위치: `ai/agents/guide_agent/guide_agent.py`
- 약 1,900줄에 query 정규화·fuzzy match·의도 판별, Neo4j, PostgreSQL raw SQL, Tavily, OpenAI 요약, 응답 구성이 함께 있다.
- Agent는 orchestration만 남기고 parser, repository, fallback, presenter를 분리한다.

### P2. 영양 조회가 Agent에서 DB에 직접 접근함

- 위치: `guide_agent.py:806-973`
- Agent가 `SessionLocal`을 만들고 여러 raw SQL query와 대표 영양 선택 규칙을 실행한다.
- `nutrition_repository.py`로 이동하고 부분 일치·대표값 선택 규칙을 단위 테스트한다.

### P2. 외부 fallback 예외가 관측되지 않음

- 위치: `guide_agent.py:1017-1045,1093-1117`
- OpenAI 요약 오류는 조용히 원문으로 대체되고 Tavily 흐름 오류는 `print`만 한다.
- 사용자 fallback은 유지하되 provider, ingredient, guide type, 오류 코드를 warning log로 남긴다.

### P2. Guide 화면의 책임이 과도함

- 위치: `app/frontend/pages/guide/Guide.jsx`
- 약 1,200줄의 페이지가 inventory, guide 목록·분류·상세, recipe, suggestion API를 직접 호출한다.
- 직접 `fetch()`가 `218,261,298,337,370,414,586,657`에 존재한다.
- `guideApi`, query hook, catalog/detail/suggestion 컴포넌트로 나눈다.

## 주석 개선

현재 주석 수준은 좋은 편이다. 추가한다면 다음 정책에 집중한다.

- 안전 민감 guide type의 목록과 일반 웹 fallback을 금지하는 이유
- fuzzy match 자동 확정과 사용자 재확인의 기준
- 대표 영양 정보 선택 우선순위
- 외부 검색 결과의 출처 등급과 응답 표시 규칙

DB query와 UI 단계를 설명하는 장문 주석은 repository와 컴포넌트 분리로 대체한다.

## 권장 작업 순서

- [ ] `nutrition_repository.py` 추출
- [ ] `guide_fallback.py`에 Tavily/OpenAI 정책 이동
- [ ] broad exception을 provider·DB 오류로 구분
- [ ] 구조화 warning log 적용
- [ ] `guideApi`와 query hook 추출
- [ ] fuzzy match와 안전 fallback 표 기반 테스트 추가

## 완료 기준

- Guide Agent가 DB session과 외부 SDK client를 직접 생성하지 않는다.
- nutrition repository의 대표값·부분 일치 규칙에 단위 테스트가 있다.
- 외부 fallback 실패가 사용자에게 안전하게 처리되면서 운영 로그에서 추적된다.
- Guide 페이지의 API 호출과 표시 컴포넌트가 분리된다.
