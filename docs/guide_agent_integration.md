# Guide Agent 연동 가이드

식재료 가이드는 내부 로직 결과를 공통 JSON 응답으로 감싸서 반환합니다.

## 호출 함수

```python
from ai.agents.guide_agent import answer_guide_query

result = answer_guide_query(user_message)
```

## 지원 흐름

- 식재료 가이드 관련 조회: Neo4j 식재료 가이드 DB를 1순위로 조회
- Neo4j에 식재료 데이터가 없으면 PostgreSQL 영양DB에서 명칭/분류/영양성분 조회
- 월별 제철: Neo4j `seasonal_months` 조회
- 영양성분: PostgreSQL `food_nutrition_facts` 조회
- Web RAG fallback: 내부 가이드가 없을 때 공신력 도메인만 검색
- 별칭/원재료명/분류: Neo4j 조회 결과의 `data.ingredient`에 포함

## 조회 우선순위

```text
사용자 질문
↓
Neo4j 가이드 DB 조회
↓
[Neo4j 식재료 데이터 없음]
PostgreSQL 영양DB에서 명칭/분류/영양성분 조회
  - 1순위: 전국통합식품영양성분정보_원재료성식품
  - 2순위: 식품의약품안전처_식품영양성분DB정보
↓
[가이드 정보 필요]
Tavily 검색 실행
↓
공신력 도메인 우선 검색
↓
[결과 있음]
출처 포함 응답
↓
[결과 없음]
일반 웹 검색
↓
[결과 있음]
후순위 출처임을 표시하고 응답
↓
[결과 없음]
실패 응답
```

## 공통 응답 형식

```json
{
  "ok": true,
  "agent": "guide",
  "action": "lookup_nutrition",
  "intent": "ingredient.guide",
  "message": "양파 영양성분을 조회했어요.",
  "data": {},
  "error": null,
  "requires_confirmation": false,
  "ui": {
    "actions": [],
    "cards": [],
    "sources": []
  },
  "meta": {}
}
```

## 주요 action

| action | 설명 |
|---|---|
| `lookup_ingredient` | 식재료 보관/손질/세척/신선도/제철/분류 전체 상세 조회 |
| `lookup_nutrition` | PostgreSQL 영양성분 조회 |
| `list_seasonal_ingredients` | 특정 월 제철 식재료 목록 조회 |
| `list_ingredients` | 식재료 가이드 목록 조회 |
| `list_categories` | 가이드 분류 옵션 조회 |

## Web RAG fallback

내부 Neo4j 가이드에 보관/손질/세척/신선도 정보가 없을 때만 fallback을 사용합니다.

1순위 공신력 도메인:

- `foodsafetykorea.go.kr`
- `mfds.go.kr`
- `rda.go.kr`
- `nongsaro.go.kr`
- `nics.go.kr`
- `mafra.go.kr`
- `data.go.kr`

2순위 후순위 웹 자료:

- 1순위 공신력 도메인에서 찾지 못했을 때만 사용
- 지식인/쇼핑/소셜/영상 도메인은 제외
- 응답에는 `meta.data_source: "general_web"`으로 표시

fallback 응답은 `meta.fallback_used: true`로 표시됩니다.

Tavily API 키가 없거나 웹 검색 결과가 없으면 추측하지 않고 `WEB_GUIDE_NOT_FOUND`를 반환합니다.

## supervisor 연결 포인트

supervisor 담당 파일에서는 아래처럼 호출하면 됩니다.

```python
from ai.agents.guide_agent import answer_guide_query

agent_result = answer_guide_query(text)
```

기존 `/api/v1/chat` 응답 형식을 유지한다면 `agent_result["message"]`, `agent_result["data"]`, `agent_result["ui"]["sources"]`를 기존 `reply/sources` 형식으로 변환하면 됩니다.

최종 챗봇 응답도 공통 JSON으로 통일한다면 `agent_result`를 그대로 반환하면 됩니다.

## 테스트 명령

```powershell
docker exec -w /project bobbeori_backend python -c "from ai.agents.guide_agent import answer_guide_query; import json; print(json.dumps(answer_guide_query('양파 영양성분 알려줘'), ensure_ascii=False, indent=2, default=str))"
```

```powershell
docker exec -w /project bobbeori_backend python -c "from ai.agents.guide_agent import answer_guide_query; import json; print(json.dumps(answer_guide_query('6월 제철 식재료 알려줘'), ensure_ascii=False, indent=2, default=str))"
```

```powershell
docker exec -w /project bobbeori_backend python -c "from ai.agents.guide_agent import answer_guide_query; import json; print(json.dumps(answer_guide_query('양파 보관법 알려줘'), ensure_ascii=False, indent=2, default=str))"
```

## 영양DB

- 정제 CSV: `storage/processed/nutrition/food_nutrition_facts.csv`
- PostgreSQL 테이블: `food_nutrition_facts`
- 생성 SQL: `app/backend/schemas/migrations/20260708_create_food_nutrition_facts.sql`
- 적재 스크립트: `etl/nutrition/load_to_postgres.py`

실제 306,332행 CSV는 용량 문제로 Git에 포함하지 않습니다. 드라이브 링크에서 파일을 받은 뒤 아래 경로에 저장하고 적재합니다.

```text
storage/processed/nutrition/food_nutrition_facts.csv
```

현재 적재 기준:

- 1순위: 전국통합식품영양성분정보_원재료성식품 3,704행
- 2순위: 식품의약품안전처_식품영양성분DB정보 302,628행
- 총 306,332행

우선순위는 `source_priority` 컬럼으로 관리합니다.

- `source_priority = 1`: 전국통합식품영양성분정보_원재료성식품
- `source_priority = 2`: 식품의약품안전처_식품영양성분DB정보

적재 명령:

```powershell
python -m etl.nutrition.load_to_postgres
```

기존 데이터를 유지하고 추가 적재하려면:

```powershell
python -m etl.nutrition.load_to_postgres --append
```

## 없는 데이터 처리 원칙

- 식재료 자체가 없으면 `ok: false`, `error.code: GUIDE_NOT_FOUND`
- 식재료는 있지만 영양성분이 없으면 `ok: false`, `error.code: NUTRITION_NOT_FOUND`
- 식재료는 있지만 특정 가이드가 비어 있으면 `data.guides.<type>.status: "missing"`
- 내부 가이드가 비어 있고 외부 검색도 실패하면 `error.code: WEB_GUIDE_NOT_FOUND`
- 없는 내용은 추측해서 생성하지 않습니다.
