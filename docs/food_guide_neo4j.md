# Neo4j Graph DB 설계안 v3 - 식재료 가이드

## 1. 전체 구조

대분류 → 중분류 → 원재료명 구조를 유지한다.

```text
대분류
 → 중분류
 → 원재료명
    ├─ 가이드정보
    │   └─ 출처
    ├─ 별칭
    ├─ 제철 월
    └─ 영양성분
        └─ 출처
```

---

### 분류 체계

목표 분류 체계는 4개 대분류와 25개 중분류로 고정한다.

```text
가공식품
 ├─ 소스·양념류
 ├─ 장류·절임류
 ├─ 면·떡·빵류
 ├─ 음료·당류
 ├─ 유지류
 └─ 기타가공식품

농산물
 ├─ 곡류·두류·견과류
 ├─ 과일류
 ├─ 채소류
 ├─ 버섯류
 └─ 향신·허브·약재류

수산물
 ├─ 생선류
 ├─ 조개류
 ├─ 갑각류
 ├─ 오징어·문어류
 ├─ 해조류
 ├─ 수산가공품
 └─ 기타수산물

축산물
 ├─ 소고기
 ├─ 돼지고기
 ├─ 닭·오리고기
 ├─ 달걀·유제품
 ├─ 육가공품
 ├─ 부산물·뼈류
 └─ 기타축산물
```

- `nodes_major_category.csv`에는 위 4개 대분류만 저장한다.
- `nodes_middle_category.csv`에는 위 25개 중분류만 저장한다.
- 식재료는 하나의 중분류에만 연결한다.
- 가공 여부를 우선 적용해 육가공품과 수산가공품은 각각 `육가공품`, `수산가공품`으로 분류한다.

---

## 2. 노드 목록

```text
MajorCategory   대분류
MiddleCategory  중분류
Ingredient      원재료명
Guide           보관/손질/세척/신선도체크
Source          출처
Alias           원재료명이명/기존표시명
SeasonMonth     제철 월
Nutrition       영양성분
```

---

## 3. 관계 목록

```text
(:MajorCategory)-[:HAS_MIDDLE]->(:MiddleCategory)

(:MiddleCategory)-[:HAS_INGREDIENT]->(:Ingredient)

(:Ingredient)-[:HAS_GUIDE]->(:Guide)

(:Guide)-[:SOURCED_FROM]->(:Source)

(:Ingredient)-[:HAS_ALIAS]->(:Alias)

(:Ingredient)-[:IN_SEASON]->(:SeasonMonth)

(:Ingredient)-[:HAS_NUTRITION]->(:Nutrition)

(:Nutrition)-[:SOURCED_FROM]->(:Source)
```

### 분할 CSV 구성

노드는 다음 8개 파일에서 먼저 적재한다.

```text
nodes_major_category.csv
nodes_middle_category.csv
nodes_ingredient.csv
nodes_guide.csv
nodes_source.csv
nodes_alias.csv
nodes_season_month.csv
nodes_nutrition.csv
```

노드 적재 후 다음 8개 관계 파일을 ID로 연결한다.

```text
rel_major_has_middle.csv
rel_middle_has_ingredient.csv
rel_ingredient_has_guide.csv
rel_guide_sourced_from.csv
rel_ingredient_has_alias.csv
rel_ingredient_in_season.csv
rel_ingredient_has_nutrition.csv
rel_nutrition_sourced_from.csv
```

- 추천레시피 노드는 제외한다.
- LLM 생성 가이드를 삭제한 최신 분할 CSV를 사용한다.
- Guide는 보관·손질·세척·신선도체크 값이 있는 경우만 생성한다.
- Source는 출처명과 URL 조합을 기준으로 중복 제거한다.
- Nutrition은 식재료 1개당 최대 1개 노드로 구성한다.

---

## 4. 추천레시피 데이터 관리

추천레시피는 Neo4j에 중복 적재하지 않는다. 기존 PostgreSQL의 `recipes`,
`recipe_ingredients`, `ingredients` 테이블과 레시피 API를 사용한다.

식재료 가이드 웹페이지는 식재료명을 기준으로 다음 API를 호출한다.

```text
GET /api/v1/recipes/search?ingredient={식재료명}
```

Neo4j는 식재료 가이드, 별칭, 제철 월, 영양성분과 출처만 담당한다.

## 5. 가능한 조회 기능

```text
식재료별 보관·손질·세척·신선도 가이드 조회
식재료 별칭과 제철 월 조회
식재료 영양성분과 출처 조회
```

---

## 6. 최종 그래프 예시

```text
농산물
 → 채소류
 → 배추
    ├─ 보관법
    ├─ 세척법
    ├─ 별칭
    ├─ 제철 월
    └─ 영양성분
        └─ 출처
```

---

## 7. JY-3.1 범위 및 완료 기준

### 업무명

`JY-3.1 [Graph DB A] 그래프 DB 검증 및 추천 연동 범위 확정`

### 담당 범위

- Neo4j는 식재료 분류, 가이드, 별칭, 제철 월, 영양성분, 출처 데이터를 담당한다.
- 추천 레시피 데이터는 PostgreSQL의 `recipes`, `recipe_ingredients`, `ingredients`를 사용한다.
- 식재료 가이드 웹페이지는 `/api/v1/recipes/search` API로 추천 레시피를 조회한다.
- Recipe 노드를 Neo4j에 중복 적재하지 않는다.

### 완료 기준

- [x] Neo4j 노드 개수 검증
- [x] 필수 관계 누락 검증
- [x] 고아 노드 검증
- [x] `python -m etl.food_guide.validate_neo4j` 실행 결과 문제 0건
- [x] Neo4j와 PostgreSQL의 데이터 책임 범위 문서화

### 검증 결과

```text
MajorCategory: 4
MiddleCategory: 25
Ingredient: 389
Guide: 892
Source: 187
Alias: 913
SeasonMonth: 12
Nutrition: 388
누락 관계: 0
고아 노드: 0
```

---

## 8. Graph DB A/B 테스트 기준선

### 비교 원칙

- A와 B는 동일한 CSV 데이터, Neo4j 버전, 서버 자원, 인덱스, 제약조건 및 조회 쿼리로 측정한다.
- 각 조회 쿼리는 캐시 예열 후 최소 1,000회 반복하고 p50, p95, p99를 기록한다.
- 현재 A는 구조 무결성만 검증됐으며 적재·조회 성능 기준선은 아직 측정하지 않았다.

### 비교 지표

| 영역 | 비교 지표 |
| --- | --- |
| 적재 | 전체 적재 시간, 재적재 시간, 실패 건수 |
| 조회 성능 | 응답시간 p50·p95·p99, 초당 처리량 |
| 쿼리 비용 | `PROFILE`의 DB Hits, 메모리 사용량 |
| 데이터 품질 | 검색 결과 정확도, 누락·중복 데이터 |
| 그래프 품질 | 누락 관계, 고아 노드, 출처 추적 가능률 |
| 운영성 | 재실행 안전성, 코드 복잡도, 유지보수 난이도 |
| 저장 효율 | 노드·관계 수, Neo4j 저장 용량 |

### 대표 조회 시나리오

1. 전체 및 카테고리별 식재료 목록 조회
2. 식재료명 정확 검색 및 부분 검색
3. 별칭을 이용한 식재료 검색
4. 식재료별 Guide, Nutrition, Source 상세 조회
5. 제철 월 기준 식재료 조회

### 판정 기준

- B의 데이터 품질은 A보다 낮아지지 않아야 한다.
- 누락 관계와 고아 노드는 모두 0건이어야 한다.
- 동일 조건에서 B의 p95 응답시간 또는 적재 시간이 A보다 15% 이상 개선되면 성능 개선으로 판정한다.
- A와 B의 원시 측정값, 실행 환경 및 실행 일시는 별도 결과표에 함께 기록한다.

### 현재 A 기준선 상태

| 항목 | 상태 |
| --- | --- |
| 구조 무결성 | 검증 완료: 누락 관계 0건, 고아 노드 0건 |
| 적재 성능 | 미측정 |
| 조회 성능 | 미측정 |
| 쿼리 비용 | 미측정 |
| 저장 효율 | 미측정 |
