# 에이전트 평가 결과

평가일: 2026-07-26

## 최신 평가 결과 요약 (2026-07-26)

OpenAI API 키와 외부 연동 환경이 설정된 Backend 컨테이너에서 실제 응답을 다시 수집했습니다. 이전 로컬 실행에서 발생한 API 키 누락 오류는 이 결과에 포함하지 않습니다.

### LLM 심사 기반 실제 응답 품질

실제 사용자 관점의 답변 품질을 확인하기 위해 실제 응답 222건을 별도 LLM 심사로 평가했습니다. 관련성 4점, 유용성 4점, 완결성 2점으로 총 10점 만점이며, 실행 자체가 실패한 18건은 품질 점수에서 제외했습니다.

| 에이전트 | 실제 응답 품질 | 주요 확인 사항 |
| --- | ---: | --- |
| Inventory Agent | 6.03 / 10 (60.2점) | 보관 위치 변경, 보유 수량 기반 조회·삭제 문맥 |
| Guide Agent | 6.42 / 10 (64.2점) | 재료 오매칭, 후속 보관 위치 질문 |
| Recipe Agent | 6.61 / 10 (66.1점) | 조건 기반 추천 실패와 DB 검색 오류 |
| Shopping Agent | 6.33 / 10 (63.2점) | 수량 보존, `외 n개` 후속 문맥 |
| Alarm Agent | 6.83 / 10 (68.3점) | 일정 시간 수정, 기간 조건 조회 |
| General Food Agent | 8.97 / 10 (89.8점) | 특수한 계량·맛 조절 질문의 사실성 |
| 전체 | **6.87 / 10 (68.7점)** | 222건 평가, 인프라 오류 18건 제외 |

Recipe Agent의 일부 실행 실패는 PostgreSQL `similarity()` 함수가 없는 환경 문제이며, Alarm Agent의 제외 건은 캘린더 연동 환경이 없는 상태에서 발생했습니다. 두 항목은 답변 품질 실패와 분리해 담당 영역에서 조치합니다.
### 3회 반복 회귀 평가

실제 사용자 실패 사례 4건을 같은 평가 프로필로 3회 반복 실행했습니다. 이 결과는 전체 Agent 품질 점수가 아니라 **멀티턴·외부 데이터 의존 경로의 재현성 확인**입니다.

| Agent | 회귀 케이스 | 3회 평균 | 표준편차 | 해석 |
| --- | --- | ---: | ---: | --- |
| Guide Agent | 이전 재료 정정 후 보관법 조회 | 10.0 / 10 | 0.000 | 양파 보관법으로 일관되게 정정됨 |
| Alarm Agent | 구매 알림 등록 | 8.0 / 10 | 0.000 | 확인 액션을 일관되게 제공함 |
| Inventory Agent | 복수 재료 수량 누락 재입력 | 평가 보류 | - | 단일 Agent 실행에는 대기 슬롯이 복원되지 않아 Supervisor Graph 통합 평가가 필요함 |
| Shopping Agent | `외 n개` 후속 조회 | 평가 보류 | - | 전용 평가 사용자에 활성 장보기 목록 시드가 없어 실제 목록 문맥을 검증할 수 없음 |

`0점`으로 나온 Inventory·Shopping 결과는 Agent 자체의 최종 품질 점수로 사용하지 않습니다. 현재 평가 실행기가 이전 대화의 문구만 전달하고, 실제 Graph 상태의 `inventory_pending`·장보기 목록 데이터를 준비하지 않았기 때문입니다. 이 문제를 드러낸 것이 이번 회귀 평가의 핵심 결과입니다.

### 평가 데이터 고정 및 사람 검수

- `test/fixtures/agent_evaluation/evaluation_profile.json`에 평가 사용자와 필요한 초기 상태를 고정했습니다.
- 공유 개발 DB를 자동 초기화하지 않습니다. 평가 전용 사용자·재고·장보기·캘린더 시드가 준비된 뒤에만 전체 반복 점수를 비교합니다.
- LLM 심사 결과에서 Agent별 저점·중간점·고점 3건씩, 총 18건을 사람이 직접 확인할 수 있는 표본 문서를 생성합니다.

```powershell
# 이전 실패 회귀셋만 실제 실행합니다.
python scripts\agent_evaluation\collect_agent_quality_results.py --regression-only --output outputs\agent_evaluations\regression-results.jsonl

# LLM 심사 결과를 3회 집계합니다.
python scripts\agent_evaluation\summarize_agent_quality_runs.py --inputs outputs\agent_evaluations\regression-judge-1.json outputs\agent_evaluations\regression-judge-2.json outputs\agent_evaluations\regression-judge-3.json

# 사람 검수용 응답 표본을 생성합니다.
python scripts\agent_evaluation\export_agent_human_review_sample.py --judge outputs\agent_evaluations\domain-agent-llm-judge-20260726.json --responses outputs\agent_evaluations\domain-agent-results-20260726-container.jsonl
```

### 최신 실행 방법

```powershell
# 실제 Agent 응답을 수집합니다.
python scripts\agent_evaluation\collect_agent_quality_results.py --user-id 1

# OpenAI API 키가 설정된 Backend 컨테이너에서 실제 답변 품질을 심사합니다.
docker compose exec -T backend sh -lc "cd /tmp/agent-evaluation && PYTHONPATH=/project python scripts/judge_agent_quality.py --results outputs/domain-agent-results-20260726-container.jsonl"
```

## 1. 자동 기능 검증 결과

아래 수치는 기능 회귀 테스트 통과 건수입니다. 에이전트 답변 품질 점수와 혼동하지 않기 위해 점수로 표시하지 않습니다.

| 에이전트 | 검증 범위 | 결과 |
| --- | --- | --- |
| Inventory Agent | 추가, 소비, 폐기, 수량 차감 DB 상태 | 13건 통과 |
| Alarm Agent | 일정 및 알림 분류, 미리보기, 인자 추출 | 47건 통과 |
| Recipe Agent | 레시피 검색 서비스 | 13건 통과 |
| Shopping Agent | 상품 보정, 목록 삭제 | 8건 통과 |
| Guide Agent | 공통 응답 계약, 빈 질문 처리 | 2건 통과 |
| General Food Agent | 일반 음식 응답 계약 | 1건 통과 |

## 2. 고난도 실제 응답 품질 평가 기준

도메인별로 40건씩 총 240건의 고난도 케이스를 사용합니다. 각 Agent는 개발용 30건과 최종 확인용 holdout 10건으로 나뉘며, 단순 키워드 포함만으로 통과하지 않습니다.

| 검증 항목 | 실패 기준 |
| --- | --- |
| 핵심 정보 | 질문의 핵심 재료, 수량, 보관 위치, 날짜 또는 요청 목적이 누락됨 |
| 도메인 일치 | 냉장고 질문을 장보기로 답하거나, 보관법 질문을 재료 등록으로 답함 |
| 금지 표현 | 전부 삭제, 잘못된 재료명, 엉뚱한 목록 등 케이스별 금지 문구가 포함됨 |
| 답변 완결성 | 답변이 20자 미만이거나 질문을 다시 반복할 뿐 해결 정보를 주지 못함 |
| 실행 안전성 | 추가, 소비, 삭제, 등록 요청에서 확인 또는 취소 액션이 누락됨 |
| 출처·구조화 결과 | 출처가 필요한 응답에서 출처가 없거나, 기대한 액션·슬롯이 누락됨 |

## 3. 최신 결과 기준 개선 우선순위

| 우선순위 | 대상 | 현재 확인된 문제 | 개선 방향 |
| --- | --- | --- | --- |
| 1 | Recipe Agent | 로컬 DB의 `pg_trgm` 확장 적용 후 검색 실행 오류는 해소됐지만, 일부 응답에 출처 필드가 비어 있음 | 배포 DB에서도 기존 마이그레이션을 적용하고, Recipe Agent가 레시피 출처를 공통 응답에 포함하는지 담당 영역에서 확인 |
| 2 | Inventory Agent | 보유 수량·보관 위치 변경·취소 후 정정 같은 멀티턴 요청의 문맥 정확도가 낮음 | 전용 평가 재고를 고정하고 수량·전체/일부 처리·취소 후 재입력 시나리오를 DB 상태로 검증 |
| 3 | Shopping Agent | 수량 보존과 `외 n개`, `더 싼 곳` 같은 후속 질문 처리 부족 | 이전 목록과 비교 결과를 대화 문맥에 유지하고 후속 표현 평가셋을 보강 |
| 4 | Guide Agent | 재료 오매칭과 후속 보관 위치 질문에서 이전 가이드 목적이 사라질 수 있음 | 후보 선택 시 원래 가이드 유형을 유지하고 재료명 오매칭 회귀 케이스 추가 |
| 5 | Alarm Agent | 일정 시간 수정·기간 조건 조회가 캘린더 연동 상태에 따라 불안정 | 전용 캘린더 샌드박스에서 등록·조회·수정·삭제를 같은 사용자 기준으로 검증 |
| 6 | General Food Agent | 특수 계량·맛 조절처럼 전제가 부정확한 질문에서 일반론 답변 가능 | 사실성 경계 질문을 별도 평가셋으로 유지하고 근거 없는 단정을 감점 |

### 재평가 원칙

1. 에이전트별 실제 응답을 최소 3회 실행해 평균 점수와 변동 폭을 함께 기록합니다.
2. DB를 바꾸는 기능은 답변 문구가 아니라 실행 전후 DB 상태로 성공 여부를 판정합니다.
3. 외부 API·캘린더 연결 오류는 별도 인프라 지표로 집계하고 답변 품질 점수에 섞지 않습니다.

## 4. 실행 방법

```powershell
# Docker DB와 필요한 API 환경 변수를 준비한 뒤 실행합니다.
python scripts\agent_evaluation\collect_agent_quality_results.py --user-id 1
```

특정 에이전트만 확인할 때는 `--agent guide`처럼 실행합니다. 평가 결과에는 실제 응답, LLM 심사 점수, 사람 검수 표본, 인프라 오류 원인이 함께 기록됩니다.
