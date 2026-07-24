# 밥벌이 에이전트 평가 지표

## 1. 평가 목적

밥벌이의 평가는 **각 에이전트가 자신의 담당 요청을 정확하게 처리하는지 측정하고, 같은 기준으로 품질을 비교해 개선 우선순위를 정하는 것**이 목적이다.

- **Agent Evaluation**: Inventory·Guide·Recipe·Shopping·Alarm·General Food Agent와 Supervisor의 라우팅·응답·실행 품질을 각각 측정한다.
- **Agent Benchmarking**: 에이전트별 평가셋, 성공률, 지연 시간, 오류 유형을 같은 형식으로 기록해 취약한 영역을 비교한다.
- **Agent QA**: 멀티턴 문맥, 출처, 정보 없음 응답, 비음식 질문 차단 등 사용자 관점의 동작 품질을 검증한다.
- **Tool-use / Task Success Evaluation**: 냉장고·장보기·일정처럼 도구나 DB를 사용하는 요청은 도구 선택·인자·확인 절차와 최종 DB 상태까지 검증한다.
- Supervisor는 독립 Agent이면서 요청을 적절한 담당 Agent로 전달하는 공통 진입점으로 평가한다.

아래 목표치는 초기 품질 기준선이다. 실제 측정이 끝난 Supervisor 라우팅 결과는 13절에만 기록하며, 각 도메인 에이전트의 답변 품질·도구 실행 성능은 아직 별도 실행 평가가 필요하다.

## 2. 공통 평가셋

초기 평가셋은 각 문장을 기대 `intent`, `slots`, `도구 호출 여부`, `기대 응답 조건`과 함께 JSONL 또는 테스트 파라미터로 관리한다.

- 실행 데이터셋: `test/fixtures/agent_evaluation/agent_eval_cases.jsonl`
- 데이터셋 계약 검증: `test/features/test_agent_evaluation_dataset.py`
- 분할: 개발용 260건, 홀드아웃 100건

| 구분 | 초기 권장 수 | 대표 문장 |
| --- | ---: | --- |
| 단일 의도 | 120개 | `감자 보관법 알려줘`, `장보기 목록 보여줘` |
| 멀티턴 문맥 | 80개 | `양파 추가해줘 → 2개 → 냉장 → 확인` |
| 데이터 변경 | 60개 | `두부 1개 먹었어`, `호박 3개 폐기해줘` |
| 복합 요청 | 40개 | `소비 임박 재료와 그 재료로 만들 레시피 알려줘` |
| 예외·안전 요청 | 60개 | `간달프 냉장고에 넣어줘`, `취소`, `전체 삭제` |
| 합계 | **360개** | 배포 전 회귀 테스트 및 에이전트 비교 기준 |

## 3. Supervisor 평가

| 지표 | 산식 | 목표 | 실패 예시 |
| --- | --- | ---: | --- |
| Intent Accuracy | 올바른 intent 수 / 전체 요청 수 | 95% 이상 | `간장 보관법`을 `shopping.*`으로 라우팅 |
| Multi-intent Decomposition Accuracy | 올바른 작업 분해 수 / 복합 요청 수 | 90% 이상 | 임박 재료와 레시피 요청 중 하나만 처리 |
| Context Resolution Accuracy | 이전 문맥을 올바르게 이어간 수 / 멀티턴 요청 수 | 90% 이상 | `나머지 2개 보여줘`를 새 장보기 검색으로 처리 |
| Slot Extraction Accuracy | 이름·수량·보관 위치·날짜가 모두 일치한 수 / 슬롯 요청 수 | 95% 이상 | `양파 2개 냉장에 추가`에서 수량 또는 위치 누락 |
| Response Contract Compliance | 공통 응답 형식 준수 수 / 전체 에이전트 응답 수 | 100% | `response_text`, `actions`, `sources` 형식 누락 |

### Supervisor 성능 개선 후보

1. LLM JSON 분류 실패, JSON 파싱 실패, 신뢰도 낮음 케이스를 Langfuse에서 별도 집계한다.
2. `나머지`, `그거`, `취소`, `냉동으로` 같은 후속 문장을 멀티턴 회귀 평가셋에 고정한다.
3. 독립적인 복합 조회만 병렬화 후보로 둔다. 단, `임박 재료 → 레시피 추천`처럼 앞 결과가 필요한 흐름은 순차 실행을 유지한다.

## 4. 도구 호출 및 쓰기 작업 평가

| 지표 | 산식 | 목표 | 적용 범위 |
| --- | --- | ---: | --- |
| Tool Selection Accuracy | 올바른 도구 선택 수 / 도구 필요 요청 수 | 95% 이상 | MCP, 냉장고, 장보기, 알림 |
| Tool Argument Accuracy | 필수 인자가 정확한 호출 수 / 도구 호출 수 | 98% 이상 | `ingredient`, `quantity`, `storage`, `event_key` |
| Confirmation Safety Rate | 확인 전 DB 변경이 없는 요청 수 / 쓰기 요청 수 | 100% | 추가·소비·폐기·일정 등록·삭제 |
| Task Success Rate | 사용자가 의도한 최종 상태가 된 수 / 완료 요청 수 | 95% 이상 | 냉장고 수량, 장보기 항목, 일정 |
| Cancellation Integrity | 취소 후 변경이 없는 요청 수 / 취소 요청 수 | 100% | 모든 쓰기 작업 |

### 확인 방법

- 쓰기 전후 PostgreSQL 데이터를 비교한다.
- `확인` 전에는 preview/action만 반환되는지 확인한다.
- `취소` 뒤에는 동일 요청의 대기 슬롯과 pending action이 제거되는지 확인한다.
- MCP는 OAuth scope가 없거나 확인 토큰이 없을 때 실행되지 않는지 확인한다.

## 5. 도메인 에이전트별 품질 지표

| 에이전트 | Agent Evaluation | Agent QA | Tool-use / Task Success | 현재 평가 상태 |
| --- | --- | --- | --- | --- |
| Inventory Agent | 식재료명 검증, 수량·보관 위치 추출 정확도 | 추가·소비·폐기 확인 흐름 | 확인 전 실행 차단, DB 수량 변경 정확도 | 확인 전 저장 차단 테스트 완료, 실제 테스트 DB 상태 평가는 필요 |
| Guide Agent | 보관·세척·신선도·영양·제철 질의 분류 정확도 | 출처 포함, `not_found`·후보 선택 응답 | 외부 검색 fallback 선택 정확도 | 공통 응답 계약 테스트 완료, 실제 답변 품질 평가는 필요 |
| Recipe Agent | 보유 재료 일치율, 소비 임박 재료 우선 반영률 | 레시피 버튼·출처·중복 노출 방지 | 레시피 검색·추천 도구 선택 정확도 | Supervisor 응답 변환 테스트 완료, 추천 품질 평가는 필요 |
| Shopping Agent | 목록 문맥 유지, 가격 조회 의도 정확도 | `외 n개`, 가격 비교 후속 질문 처리 | 목록 추가·삭제·입고 작업 성공률 | 삭제 계약 테스트 완료, 실제 입고 트랜잭션 평가는 필요 |
| Alarm Agent | 제목·날짜·시간 추출, 일정·알림 구분 | 상대 날짜, 추가 입력, 확인·취소 흐름 | 캘린더·알림 도구 인자와 실행 정확도 | 단독 자동 테스트로 검증 완료, 실제 연동 평가는 필요 |
| General Food Agent | 음식 도메인 적합률, 비음식 질문 차단률 | 답변 관련성·사실성·표현 품질 | 외부 LLM 호출 성공·오류 처리 | 공통 응답 계약 테스트 완료, 사람 평가 표본이 필요 |
| Supervisor Agent | intent·담당 Agent 라우팅, 복합 요청 분해 정확도 | 멀티턴 문맥, 재시도, fallback 전환 | 확인 토큰 검증, Agent 호출 순서 | 홀드아웃 100건 Intent 95.0%, Agent Routing 97.0% |

### 공통 목표 기준

| 평가 항목 | 초기 목표 |
| --- | ---: |
| Agent Evaluation / 담당 Agent 라우팅 정확도 | 95% 이상 |
| Agent QA / 사용자 흐름 회귀 테스트 | 핵심 시나리오 100% 통과 |
| Tool-use Evaluation / 도구 선택 정확도 | 95% 이상 |
| Tool Argument Accuracy / 필수 인자 정확도 | 98% 이상 |
| Task Success Evaluation / 최종 DB 상태 성공률 | 95% 이상 |
| Confirmation Safety / 확인 전 쓰기 작업 차단 | 100% |

## 6. 응답 품질 평가

자동 지표만으로 답변 품질을 판단하기 어려운 가이드·레시피·일반 음식 질의는 표본을 사람 평가로 함께 확인한다.

| 항목 | 0점 | 1점 | 2점 |
| --- | --- | --- | --- |
| 관련성 | 질문과 무관 | 일부 관련 | 질문과 직접 관련 |
| 사실성 | 명백히 틀림 또는 근거 없음 | 불명확 | 내부 데이터 또는 신뢰 가능한 출처 기반 |
| 실행 가능성 | 다음 행동을 알 수 없음 | 일부 안내 | 사용자가 바로 이해·실행 가능 |
| 표현 품질 | 장황하거나 부자연스러움 | 보통 | 짧고 자연스럽고 읽기 쉬움 |

- 표본당 만점은 8점이다.
- 초기 배포 기준은 평균 **6.5점 이상**으로 둔다.
- `not_found`는 오류가 아니라 정상적인 안내로 평가한다.

## 7. 운영 지표

| 지표 | 기준 | 수집 위치 |
| --- | --- | --- |
| End-to-End Latency | p95 8초 이하, 도구 미사용 조회 p95 4초 이하 | Langfuse Trace / API 로그 |
| Agent Error Rate | 전체 요청 중 error 상태 2% 이하 | Langfuse / 서버 로그 |
| Retry Rate | 품질 재시도 발생 비율 추적 | Supervisor 결과 |
| LLM Cost per Session | 세션당 토큰·비용 추이 확인 | Langfuse Usage |
| Fallback Rate | General Food Agent 또는 웹 검색 이동 비율 추적 | intent / agent 결과 |

## 8. 우선 성능 개선 순서

1. **안전성 회귀 테스트**: 확인 전 실행, 취소 후 잔여 슬롯, 과수량 소비·폐기부터 100%를 유지한다.
2. **멀티턴 문맥 평가셋**: 후속 질문·정정·수량 입력·전체 보기·취소를 고정 테스트로 추가한다.
3. **라우팅 오분류 분석**: Langfuse에서 intent와 실제 선택 에이전트를 비교해 상위 오분류 표현을 분류한다.
4. **도구 인자 검증 강화**: 수량, 보관 위치, 일정 날짜·시간처럼 DB 상태를 바꾸는 슬롯 오류를 우선 수정한다.
5. **응답 품질 샘플링**: Guide/Recipe/General Food Agent 응답을 주기적으로 20건씩 점수화한다.

## 9. 배포 전 최소 통과 기준

- 360개 평가셋 중 Intent Accuracy 95% 이상
- 쓰기 작업 Confirmation Safety Rate 및 Cancellation Integrity 100%
- 핵심 도구 Tool Argument Accuracy 98% 이상
- 멀티턴 문맥 Context Resolution Accuracy 90% 이상
- 최근 변경 기능의 기존 `pytest` 회귀 테스트 통과

## 10. 현재 자동 검증 범위 (2026-07-24)

| 구분 | 측정 여부 | 현재 확인 범위 |
| --- | --- | --- |
| 평가셋 계약 검증 | 완료 | JSONL 360건의 스키마·분할·영역 분포 확인 |
| Supervisor 라우팅 | 완료 | 홀드아웃 100건의 intent·담당 Agent 라우팅 측정 |
| Supervisor 안전 라우팅 | 기존 테스트 보유 | 확인·취소·추가·소비·폐기 등 쓰기 작업의 회귀 테스트 |
| 도메인 Agent 답변 품질 | 미측정 | Guide·Recipe·Shopping·General Food 실제 응답 품질 평가 필요 |
| Tool-use·Task Success | 미측정 | 테스트 DB에서 도구 인자와 실행 전후 상태를 평가해야 함 |

### 주의 사항

- 전체 프로젝트 `pytest` 통과 건수는 실행 환경과 브랜치에 따라 달라질 수 있으므로, 문서에는 고정 수치로 기록하지 않는다.
- 실행한 테스트 명령과 결과는 배포·PR 시점에 별도 결과로 남긴다.
- Python 3.14에서는 LangChain Core의 Pydantic V1 호환성 경고가 나타날 수 있으므로, 운영 Python 3.11 환경과 같은 버전으로 평가하는 편이 안전하다.

## 12. 평가 체계 보완 사항

### 데이터셋 구성 보완

- 평가셋을 **개발용 260건 / 홀드아웃 100건**으로 분리한다. 개발용은 수정 후 반복 실행하고, 홀드아웃은 점수 확인용으로만 사용한다.
- 전체 데이터의 최소 20%는 오타·띄어쓰기·동의어·후속 표현으로 구성한다. 예: `먹엇어`, `외2개`, `냉동실에`, `그거 취소`.
- 각 케이스에 `로그인 여부`, `초기 DB 상태`, `이전 대화`, `외부 API 모킹 여부`를 명시한다. 같은 질문도 냉장고 보유 재료나 로그인 상태에 따라 기대 결과가 달라진다.
- LLM 응답은 정답 문장 완전 일치가 아니라 `intent`, `필수 슬롯`, `금지 행동`, `출처 여부`, `핵심 키워드` 같은 조건으로 채점한다.

### 측정 방식 보완

- **Task Success**: DB 변경 요청은 응답 문구가 아니라 실행 전후 DB 상태로 판정한다.
- **Tool-use**: 선택한 도구, 인자, 실행 순서, 확인 전 실행 금지를 각각 분리해 기록한다.
- **답변 품질**: Guide·Recipe·General Food는 자동 조건 검사 후, 홀드아웃 20건을 사람이 0~2점 척도로 검수한다.
- **재시도 품질**: Agent가 품질 부족으로 최대 1회 재시도했을 때, 최초 응답 대비 성공률·지연 시간·토큰 비용 변화를 별도 기록한다.
- **운영 표본**: Langfuse에서 주 1회 실제 trace 20건을 무작위 추출해 라우팅 오류·도구 오류·환각·불필요한 fallback을 분류한다.

### 지금 우선 보완할 코드·운영 항목

1. Guide Agent와 General Food Agent의 단독 자동 평가가 없다. 각각 60건, 40건 평가셋부터 만든다.
2. Inventory Agent는 정상 처리뿐 아니라 **과수량, 전체 삭제, 취소 후 재입력, 동일 식재료 다건 보유** 시나리오를 DB 상태 검증으로 추가한다.
3. Recipe Agent는 레시피 제목 일치보다 **보유 재료 포함률**과 **소비 임박 재료 우선 반영률**을 계산한다.
4. Shopping Agent는 `외 n개`, `더 싼 곳`, `그거 삭제` 같은 후속 문맥을 별도 그룹으로 관리한다.
5. LLM JSON 분류에는 `confidence`, 원본 모델 응답, fallback 여부를 Langfuse metadata로 남겨 저신뢰 라우팅을 바로 찾을 수 있게 한다.
## 13. Supervisor 라우팅 홀드아웃 결과 (2026-07-24)

- 실행 명령: `python scripts/evaluate_supervisor_routing.py --split holdout`
- 범위: 홀드아웃 100건, **DB 변경 없이 Supervisor 라우팅만 평가**
- Intent Accuracy: **95 / 100 (95.0%)**
- Agent Routing Accuracy: **97 / 100 (97.0%)**

| 담당 영역 | 건수 | Intent Accuracy | Agent Routing Accuracy |
| --- | ---: | ---: | ---: |
| Inventory | 17 | 100.0% | 100.0% |
| Guide | 17 | 88.2% | 88.2% |
| Recipe | 14 | 100.0% | 100.0% |
| Shopping | 14 | 85.7% | 100.0% |
| Alarm | 17 | 100.0% | 100.0% |
| General Food | 11 | 90.9% | 90.9% |
| Supervisor 복합·문맥 | 10 | 100.0% | 100.0% |

### 실패 유형 분석

| 실패 유형 | 건수 | 사례 | 개선 방향 |
| --- | ---: | --- | --- |
| 담당 Agent 오분류 | 3 | `채소에 뭐가 있어?`, `먹다 남은 치킨 보관법`, `케이크 크림 대체 재료` | 분류·보관법은 Guide 우선, 대체 재료는 General Food 우선 규칙을 LLM 결과 보정 후보로 관리 |
| 세부 intent 오분류 | 2 | `더 싼 곳 없어?`, `가격 비교 결과 해석해줘` | 둘 다 Shopping Agent로 전달되므로 기능 영향은 없지만, `shopping.price_help`와 `shopping.compare`의 설명을 구분 |

- 이 평가는 **Supervisor의 분류 성능**이다. 각 Agent의 답변 사실성, Tool 인자 정확도, DB 변경 성공률은 별도 테스트 DB와 Agent별 실행기로 이어서 측정한다.
- LLM 기반 분류는 실행 시점에 결과가 조금 달라질 수 있으므로, 홀드아웃 결과 JSON과 모델·프롬프트 버전을 함께 보관한다.
## 14. 에이전트 공통 계약 QA 실행 결과 (2026-07-24)

- 실행 명령: `python -m pytest -q test/features/test_agent_evaluation_dataset.py test/features/test_supervisor_routing_regression.py test/features/test_agent_evaluation_contracts.py test/features/test_inventory_agent_task_success.py test/test_alarm_agent.py test/test_shopping_item_delete.py`
- 결과: **73 passed**
- 범위: 외부 OpenAI·DB·검색 API는 테스트 대역으로 분리한 공통 응답 계약, 확인 절차, 도구 호출 경로 검증

| Agent/영역 | 이번 확인 내용 | 판정 |
| --- | --- | --- |
| Supervisor | 평가셋 구조, 안전 라우팅, 라우팅 회귀 | 통과 |
| Inventory | 재료 추가 미리보기 후 확인 시에만 저장 도구 호출 | 통과 |
| Guide | 빈 질문·월 미지정 질문의 공통 응답 형식 | 통과 |
| Recipe | 레시피 버튼·출처·표시 이력의 Supervisor 응답 변환 | 통과 |
| Shopping | 장보기 항목 삭제와 레시피 항목 tombstone 처리 | 통과 |
| Alarm | 일정·알림 의도, 상대 날짜, 확인 플로우 | 통과 |
| General Food | 모델 응답의 공통 `response_text` 변환 | 통과 |

### 평가에서 확인한 실제 개선 후보

- `제철음식`처럼 월을 생략한 Guide 질의는 현재 `needs_input` 대신 `error`로 반환될 수 있다. 공통 응답 형식은 유지되지만, 사용자 경험상 월 입력 요청으로 개선이 필요하다.
- 이 결과는 **Agent QA/계약 검증**이며, 실제 외부 데이터 기반 답변의 관련성·사실성·출처 품질과 DB 최종 상태는 아직 측정하지 않았다.
- 다음 실행 평가는 테스트 DB를 초기화한 뒤 Inventory·Shopping·Alarm의 Tool-use/Task Success를 측정하고, Guide·Recipe·General Food는 홀드아웃 표본 20건을 사람 평가로 채점한다.
## 15. 2차 Agent QA 및 Tool-use / Task Success 결과 (2026-07-24)

### 평가 데이터 보강

- 공통 JSONL 평가셋은 **360건**으로 구성했으며, Inventory 60건, Guide 60건, Recipe 50건, Shopping 50건, Alarm 60건, General Food 40건, Supervisor 40건을 포함합니다.
- 각 도메인 에이전트는 최소 40건 이상의 독립 문장을 포함하므로, 특정 표현 하나에만 맞춘 평가가 되지 않도록 구성했습니다.
- 개발용 260건과 최종 확인용 holdout 100건을 분리해, 라우팅 규칙 수정 후 동일 문장에만 과적합되는 것을 줄였습니다.

### Inventory Tool-use / Task Success

`test/features/test_inventory_agent_task_success.py`는 운영 PostgreSQL 대신 테스트마다 새로 만드는 SQLite 메모리 DB를 사용합니다. 운영 데이터나 다른 에이전트 구현 파일은 변경하지 않습니다.

| 검증 항목 | 케이스 수 | 확인 기준 |
| --- | ---: | --- |
| 소비 도구 실행 | 6건 | 요청 수량만큼 활성 재고가 차감되고, 초과 요청은 보유 수량까지만 처리 |
| 폐기 도구 실행 | 3건 | 요청 수량만큼 활성 재고가 차감 또는 소비 완료 상태로 변경 |
| 등록 도구 실행 | 3건 | 확인된 식재료명, 수량, 보관 위치로 냉장고 행 생성 |
| 잘못된 수량 차단 | 1건 | 0 이하 수량은 DB 상태를 변경하지 않음 |
| 합계 | **13건** | 도구 반환 문구가 아니라 실행 전후 DB 상태 비교 |

### 실행 결과

```powershell
python -m pytest -q test\features\test_agent_evaluation_dataset.py test\features\test_supervisor_routing_regression.py test\features\test_agent_evaluation_contracts.py test\features\test_inventory_agent_task_success.py test\test_alarm_agent.py test\test_shopping_item_delete.py --basetemp=outputs\pytest-agent-evaluation -p no:cacheprovider
```

- 결과: **73 passed**
- 경고: Python 3.14 환경의 LangChain Pydantic V1 호환성 경고와 Pydantic/SQLAlchemy deprecation 경고 9건. 테스트 실패는 없습니다.

### 현재 범위와 다음 단계

- 이번 단계에서는 사용자 담당 범위인 Inventory Agent의 실제 DB 상태 검증을 우선 추가했습니다.
- Guide, Recipe, Shopping, Alarm, General Food Agent는 공통 계약·라우팅·기존 단위 테스트로 검증합니다. 실제 외부 DB/API 결과까지 포함한 Task Success 평가는 각 담당 에이전트의 테스트 DB 또는 모의 API 환경이 준비된 뒤 같은 표에 추가합니다.