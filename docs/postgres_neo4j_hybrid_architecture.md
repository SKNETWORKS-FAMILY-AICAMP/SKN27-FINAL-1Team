# PostgreSQL + Neo4j 혼합 저장 구조

## 1. 저장소 분리 기준

본 서비스는 PostgreSQL과 Neo4j를 함께 사용하는 혼합 구조를 채택하였다.

핵심 기준은 다음과 같다.

```text
사용자별로 자주 생성·수정·삭제되는 데이터는 PostgreSQL,
식재료를 중심으로 여러 관계를 확장 탐색하는 데이터는 Neo4j
```

| 기능 | 추천 저장소 | 이유 |
| --- | --- | --- |
| 냉장고 재료 등록·관리 | PostgreSQL | 사용자별 재고, 수량, 등록일, 소비기한 등 CRUD와 정합성 관리에 적합 |
| OCR 재료 등록·관리 | PostgreSQL | 영수증 원본, OCR 결과, 수정 이력, 구매 품목 저장에 적합 |
| 식재료 가이드 | Neo4j | 표준 식재료, 별칭, 분류, 가이드, 영양, 제철, 출처 관계 탐색에 적합 |
| 레시피 추천 | PostgreSQL + Neo4j | 사용자 재고는 PostgreSQL, 식재료-별칭-레시피 관계 탐색은 Neo4j |
| 챗봇 | PostgreSQL + Neo4j | 사용자 요청을 분석해 필요한 저장소를 호출하고 결과를 통합 |

## 2. 기능별 흐름

### 냉장고 재료 등록·관리

냉장고 재료는 PostgreSQL에 저장한다.

```text
사용자
-> 냉장고 재고 항목
-> 수량
-> 구매일
-> 소비기한
-> 재고 상태
```

PostgreSQL이 적합한 이유는 다음과 같다.

- 수정·삭제가 빈번하다.
- 사용자별 데이터 분리가 중요하다.
- 날짜, 수량, 상태값 관리가 필요하다.
- 트랜잭션과 FK 기반 정합성 관리가 필요하다.

주요 테이블:

```text
users
ingredients
fridge_items
notifications
user_preferences
```

### OCR 재료 등록·관리

영수증과 OCR 결과도 PostgreSQL에 저장한다.

```text
영수증
-> OCR 추출 품목
-> 사용자 검수
-> 최종 재고 등록
```

주요 테이블:

```text
receipts
receipt_items
fridge_items
```

OCR 원문, 추출 결과, 사용자가 수정한 최종값은 구분해서 관리하는 것이 좋다.

### 식재료 가이드

식재료 가이드는 Neo4j에 저장한다.

```text
대분류
-> 중분류
-> 표준 식재료
-> 별칭
-> 가이드
-> 영양성분
-> 제철 정보
-> 출처
```

대표 관계:

```cypher
(:MajorCategory)-[:HAS_MIDDLE]->(:MiddleCategory)
(:MiddleCategory)-[:HAS_INGREDIENT]->(:Ingredient)
(:Ingredient)-[:HAS_ALIAS]->(:Alias)
(:Ingredient)-[:HAS_GUIDE]->(:Guide)
(:Ingredient)-[:HAS_NUTRITION]->(:Nutrition)
(:Ingredient)-[:IN_SEASON]->(:SeasonMonth)
(:Guide)-[:SOURCED_FROM]->(:Source)
(:Nutrition)-[:SOURCED_FROM]->(:Source)
```

### 레시피 추천

레시피 추천은 PostgreSQL과 Neo4j를 함께 사용한다.

```text
PostgreSQL
사용자 냉장고 재고 조회
        ↓
Neo4j
재고명을 별칭에서 표준 식재료로 변환
        ↓
표준 식재료의 전체 별칭 확장
        ↓
관련 레시피 탐색
        ↓
PostgreSQL
사용자 선호도·저장 여부·추천 이력 반영
```

PostgreSQL은 사용자별 상태를 관리하고, Neo4j는 식재료 관계 탐색을 담당한다.

## 3. 챗봇의 역할

챗봇은 데이터를 저장하는 중심이 아니라, 사용자 요청을 분석해 PostgreSQL과 Neo4j 중 필요한 저장소를 호출하고 결과를 통합하는 인터페이스 역할을 한다.

| 챗봇 기능 | 활용 저장소 |
| --- | --- |
| 냉장고 재고 조회·수정 | PostgreSQL |
| 영수증/OCR 등록 내역 조회 | PostgreSQL |
| 식재료 별칭 정규화 | Neo4j |
| 식재료 가이드 조회 | Neo4j |
| 보유 재료 기반 레시피 탐색 | PostgreSQL + Neo4j |
| 대화 이력·사용자 설정 | PostgreSQL 또는 세션 메모리 |

예시 흐름:

```text
사용자: 냉장고에 있는 대파로 만들 수 있는 요리 알려줘
```

처리 순서:

```text
1. PostgreSQL에서 사용자 냉장고 재고 조회
2. Neo4j에서 대파를 표준 식재료와 연결
3. 표준 식재료의 전체 별칭으로 레시피 탐색
4. PostgreSQL의 사용자 선호·저장 레시피·알레르기 정보 반영
5. 챗봇이 추천 결과와 부족 재료를 응답
```

추천 구조:

```text
사용자 질문
-> Supervisor Agent
-> 재고·OCR 요청: PostgreSQL
-> 가이드·관계 탐색: Neo4j
-> 복합 요청: 두 DB 조회
-> 결과 통합
-> 챗봇 응답
```

대화 원문, 세션, 사용자별 선호처럼 다시 불러와야 하는 정보는 PostgreSQL에 저장하고, 현재 대화 중 필요한 임시 상태는 LangGraph State 같은 메모리 구조로 관리한다.

## 4. 최종 권장 구조

```text
PostgreSQL
- 사용자
- 냉장고
- 재고
- 영수증
- OCR 결과
- 사용자 선호
- 저장 레시피
- 추천 이력

Neo4j
- 대분류
- 중분류
- 표준 식재료
- 별칭
- 가이드
- 영양성분
- 제철
- 출처
- 레시피
- 식재료-레시피 관계
```

성능 비교 결과에서도 PK 기반 단순 조회와 별칭 정규화 조회는 PostgreSQL이 더 낮은 응답 시간을 기록했고, 다단계 관계 조회와 복수 식재료 공통 레시피 조회는 Neo4j가 더 낮은 평균 및 p95 응답 시간을 기록하였다. 따라서 본 프로젝트의 PostgreSQL + Neo4j 혼합 저장 구조는 기능 특성과 조회 패턴에 맞는 분리 방식이다.
