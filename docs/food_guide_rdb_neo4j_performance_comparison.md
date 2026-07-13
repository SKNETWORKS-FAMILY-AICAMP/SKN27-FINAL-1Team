# Food Guide 주요 조회 유형별 PostgreSQL RDB vs Neo4j 성능 비교

## 1. 비교 목적

동일한 식재료 및 레시피 연결 데이터를 PostgreSQL 정규화 테이블과 Neo4j 그래프 모델에 각각 적재한 뒤, 단순 식별자 조회부터 다단계 관계 탐색까지 서비스의 주요 조회 유형별 성능을 비교하였다. 이를 통해 조회 유형에 따른 각 저장소의 적합성과 프로젝트의 데이터 분리 구조를 검증하고자 하였다.

핵심 비교 시나리오인 별칭 기반 레시피 조회의 질문은 다음과 같다.

```text
입력 별칭을 기준으로 표준 식재료를 찾고,
해당 표준 식재료의 전체 별칭으로 연결된 레시피 Top 20을 조회한다.
```

이 시나리오는 단순 별칭 1개 조회가 아니라 다음 다단계 관계 확장 흐름을 측정한다.

```text
입력 별칭 -> 표준 식재료 -> 전체 별칭 -> 레시피
```

## 2. 비교 대상 데이터

| 항목 | 건수 |
| --- | ---: |
| 식재료 | 698 |
| 별칭 | 1,617 |
| 레시피 | 3,171 |
| 식재료-별칭 연결 | 2,689 |
| 레시피-별칭 연결 | 23,440 |

원천 데이터는 다음 파일을 사용하였다.

```text
storage/processed/food_guide/nodes_ingredient.csv
storage/processed/food_guide/nodes_alias.csv
storage/processed/food_guide/rel_ingredient_has_alias.csv
storage/processed/recipe/recipe_fix.csv
storage/processed/recipe/recipe_ingredient_alias.csv
```

## 3. 비교 모델

### PostgreSQL 비교 모델

기존 서비스 테이블과 충돌하지 않도록 `bench_` prefix를 붙인 비교용 테이블에 적재하였다.

```text
bench_ingredients
bench_aliases
bench_recipes
bench_ingredient_aliases
bench_recipe_aliases
```

조회 흐름은 다음과 같다.

```text
bench_aliases
  -> bench_ingredient_aliases
  -> bench_ingredients
  -> bench_ingredient_aliases
  -> bench_recipe_aliases
  -> bench_recipes
```

### Neo4j 비교 모델

기존 그래프 구조를 그대로 사용하였다.

```text
(:Alias)<-[:HAS_ALIAS]-(:Ingredient)-[:HAS_ALIAS]->(:Alias)<-[:USES_ALIAS]-(:Recipe)
```

## 4. 측정 조건

| 조건 | 내용 |
| --- | --- |
| 실행 환경 | 동일 로컬 Docker 환경 |
| 측정 방식 | Python DB driver 내부 실행 시간 측정 |
| 반복 횟수 | 별칭별 워밍업 10회 후 측정 100회 |
| 별칭당 총 실행 횟수 | 110회 |
| 전체 측정 횟수 | 10개 별칭 x 100회 = 1,000회 |
| 결과 지표 | 평균, 중앙값, 전체 p95, 별칭별 p95, 최소, 최대 |
| 제외 항목 | `docker exec`, `psql`, `cypher-shell`, HTTP, 직렬화, 프론트엔드 렌더링 시간 |

측정값은 애플리케이션 전체 응답 시간이 아니라, **Python 애플리케이션 내부에서 쿼리 실행 직전부터 결과 수신 완료 시점까지의 시간**이다.

테스트 별칭은 레시피 연결 수가 충분한 상위 별칭 10개를 사용하였다.

```text
마늘, 설탕, 대파, 양파, 소금, 참기름, 후추, 고춧가루, 간장, 통깨
```

대표 조회 유형별 테스트 입력은 다음과 같다.

| 조회 유형 | 테스트 입력 | 측정 횟수 |
| --- | --- | --- |
| PK 기반 단순 조회 | 실제 서비스 데이터에서 선정한 식재료 ID 10개 | 10개 입력 x 100회 = 1,000회 |
| 별칭 정규화 조회 | 상위 별칭 10개 | 10개 입력 x 100회 = 1,000회 |
| 다단계 관계 조회 | 상위 별칭 10개 | 10개 입력 x 100회 = 1,000회 |
| 복수 식재료 공통 레시피 조회 | 3개 식재료 조합 5개 | 5개 입력 x 100회 = 500회 |

각 입력은 워밍업 10회를 먼저 수행한 뒤, 측정 대상 쿼리를 100회 반복 실행하였다.

복수 식재료 공통 레시피 조회에 사용한 조합은 다음과 같다.

```text
마늘 + 양파 + 대파
마늘 + 양파 + 고추
마늘 + 간장 + 참기름
소금 + 후추 + 마늘
고춧가루 + 간장 + 마늘
```

## 5. 인덱스 조건

PostgreSQL은 다음 인덱스를 적용하였다.

| 테이블 | 인덱스 |
| --- | --- |
| `bench_aliases` | `PRIMARY KEY(alias_id)`, `INDEX(name)` |
| `bench_ingredients` | `PRIMARY KEY(ingredient_id)` |
| `bench_recipes` | `PRIMARY KEY(recipe_id)`, `INDEX(review_rank_score DESC)` |
| `bench_ingredient_aliases` | `PRIMARY KEY(ingredient_id, alias_id)`, `INDEX(alias_id)`, `INDEX(ingredient_id)` |
| `bench_recipe_aliases` | `PRIMARY KEY(recipe_id, alias_id)`, `INDEX(alias_id)`, `INDEX(recipe_id)` |

Neo4j는 다음 인덱스를 사용하였다.

| 라벨 | 인덱스 |
| --- | --- |
| `Alias` | `id`, `name` |
| `Recipe` | `recipeId`, `reviewRankScore` |

PostgreSQL `EXPLAIN (ANALYZE, BUFFERS)` 기준으로 `bench_aliases.name`, `bench_ingredient_aliases.alias_id`, `bench_ingredient_aliases(ingredient_id, alias_id)`, `bench_recipe_aliases.alias_id`, `bench_recipes.recipe_id` 인덱스가 사용되었다.

Neo4j `PROFILE` 기준으로 `Alias.name` 인덱스 탐색 후 관계 순회를 수행하였다.

## 6. 대표 쿼리

### PostgreSQL

```sql
SELECT i.ingredient_id, i.name AS ingredient_name,
       r.recipe_id, r.name AS recipe_name, r.review_rank_score
FROM bench_aliases input_alias
JOIN bench_ingredient_aliases input_ia ON input_ia.alias_id = input_alias.alias_id
JOIN bench_ingredients i ON i.ingredient_id = input_ia.ingredient_id
JOIN bench_ingredient_aliases all_ia ON all_ia.ingredient_id = i.ingredient_id
JOIN bench_recipe_aliases ra ON ra.alias_id = all_ia.alias_id
JOIN bench_recipes r ON r.recipe_id = ra.recipe_id
WHERE input_alias.name = :alias
GROUP BY i.ingredient_id, i.name, r.recipe_id, r.name, r.review_rank_score
ORDER BY r.review_rank_score DESC NULLS LAST, r.recipe_id DESC
LIMIT 20;
```

### Neo4j

```cypher
MATCH (input:Alias {name: $alias})<-[:HAS_ALIAS]-(i:Ingredient)
MATCH (i)-[:HAS_ALIAS]->(:Alias)<-[:USES_ALIAS]-(r:Recipe)
RETURN DISTINCT
       i.id AS ingredient_id,
       i.name AS ingredient_name,
       r.recipeId AS recipe_id,
       r.name AS recipe_name,
       r.reviewRankScore AS review_rank_score
ORDER BY CASE WHEN review_rank_score IS NULL THEN 1 ELSE 0 END,
         review_rank_score DESC,
         recipe_id DESC
LIMIT 20
```

Neo4j 쿼리는 PostgreSQL의 `GROUP BY` 및 `NULLS LAST`와 결과 의미를 맞추기 위해 `DISTINCT`와 null 정렬 조건을 명시하였다.

## 7. 결과 동일성 검증

측정 전후 다음 항목이 PostgreSQL과 Neo4j에서 동일한지 검증하였다.

| 조회 유형 | 검증 기준 | 결과 |
| --- | --- | --- |
| PK 기반 단순 조회 | 식재료 ID 동일 | 통과 |
| 별칭 정규화 조회 | 표준 식재료 ID 동일 | 통과 |
| 다단계 관계 조회 | 식재료 ID, 레시피 ID 목록, 정렬 순서 동일 | 통과 |
| 복수 식재료 공통 레시피 조회 | 공통 레시피 ID 목록, 정렬 순서 동일 | 통과 |

4개 조회 유형 모두 PostgreSQL과 Neo4j의 반환 건수, 핵심 ID, 정렬 순서를 비교하였으며 동일성 검증을 통과하였다.

검증 결과:

```text
validation: ok
```

## 8. 다단계 관계 조회 실행 계획 요약

| 항목 | PostgreSQL | Neo4j |
| --- | --- | --- |
| 주요 처리 | 다중 JOIN, HashAggregate 중복 제거, Top-N 정렬 | `Alias.name` 인덱스 탐색, 관계 순회, DISTINCT, 정렬 |
| 대표 별칭 | 마늘 | 마늘 |
| 최종 반환 행 수 | 20 | 20 |
| 저장소 접근 지표 | Buffers shared hit=4,405 | DbHits 7,094 |
| 실행 계획 측정 시간 | Execution Time 8.479 ms | PROFILE Time 269 ms |
| 참고 | `EXPLAIN ANALYZE` 수행 | `PROFILE` 오버헤드 포함 |

Neo4j `PROFILE`은 실행 계획 수집과 각 연산자의 통계 기록으로 인해 일반 쿼리 실행보다 큰 오버헤드가 발생하므로, PostgreSQL의 `EXPLAIN ANALYZE` 시간과 절대값을 직접 비교하지 않았다. 실행 계획 시간은 성능 결론의 근거가 아니라 인덱스 사용 여부와 주요 연산 방식을 확인하기 위한 참고 지표로 사용하였다. 실제 성능 비교에는 동일한 Python 드라이버 측정값을 사용하였다.

## 9. 대표 조회 유형별 측정 결과

Neo4j에 유리한 질의만 선택했다는 편향을 줄이기 위해, 서비스에서 사용하는 조회를 4가지 유형으로 나누어 추가 측정하였다.

| 조회 유형 | 조회 시나리오 | PostgreSQL 평균(ms) | PostgreSQL p95(ms) | Neo4j 평균(ms) | Neo4j p95(ms) | 검증 |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| PK 기반 단순 조회 | `ingredient_id -> 식재료 정보` | 0.522 | 0.967 | 2.970 | 4.544 | 통과 |
| 별칭 정규화 조회 | `별칭 -> 표준 식재료` | 1.565 | 3.620 | 3.380 | 5.638 | 통과 |
| 다단계 관계 조회 | `별칭 -> 식재료 -> 전체 별칭 -> 레시피 Top 20` | 11.911 | 22.268 | 7.120 | 12.076 | 통과 |
| 복수 식재료 공통 레시피 조회 | `여러 식재료를 모두 포함하는 레시피 Top 20` | 14.011 | 25.543 | 9.630 | 15.824 | 통과 |

측정 결과 단순 식별자 기반 조회와 1단계 별칭 정규화 조회에서는 PostgreSQL이 더 낮은 응답 시간을 기록하였다. 반면 별칭에서 표준 식재료를 찾고 전체 별칭으로 확장해 레시피를 조회하는 다단계 관계 조회와, 여러 식재료를 공통으로 포함하는 레시피를 찾는 복합 관계 조회에서는 Neo4j가 더 낮은 평균 및 p95 응답 시간을 기록하였다.

따라서 본 프로젝트의 저장소 역할 분리는 다음과 같이 해석할 수 있다.

```text
PostgreSQL: 사용자, 냉장고, 영수증, 저장 레시피 등 CRUD 및 단순 조회 중심 데이터
Neo4j: 식재료, 별칭, 가이드, 영양, 제철, 레시피처럼 관계 확장이 중요한 데이터
```

## 10. 다단계 관계 조회 상세 결과

| 별칭 | PostgreSQL 평균(ms) | PostgreSQL p95(ms) | Neo4j 평균(ms) | Neo4j p95(ms) |
| --- | ---: | ---: | ---: | ---: |
| 마늘 | 13.629 | 23.258 | 7.120 | 11.685 |
| 설탕 | 9.104 | 13.134 | 5.974 | 8.860 |
| 대파 | 11.823 | 20.030 | 6.877 | 10.036 |
| 양파 | 13.977 | 22.151 | 7.382 | 12.506 |
| 소금 | 12.295 | 24.777 | 7.629 | 13.494 |
| 참기름 | 9.270 | 14.539 | 6.202 | 11.401 |
| 후추 | 16.242 | 29.841 | 8.917 | 12.622 |
| 고춧가루 | 9.170 | 11.699 | 5.655 | 8.122 |
| 간장 | 11.411 | 16.061 | 8.479 | 12.395 |
| 통깨 | 12.192 | 19.995 | 6.969 | 9.271 |

전체 1,000회 측정값을 합산해 계산한 결과는 다음과 같다.

| 구분 | 전체 평균(ms) | 전체 중앙값(ms) | 전체 p95(ms) | 최소(ms) | 최대(ms) |
| --- | ---: | ---: | ---: | ---: | ---: |
| PostgreSQL | 11.911 | 10.488 | 22.268 | 6.399 | 43.473 |
| Neo4j | 7.120 | 6.512 | 12.076 | 3.106 | 24.492 |

전체 평균 기준 Neo4j는 PostgreSQL보다 약 40.2% 낮은 응답 시간을 기록하였다.

```text
(11.911 - 7.120) / 11.911 * 100 = 약 40.2%
```

Neo4j는 다단계 관계 조회에서 전체 평균과 p95 모두 더 낮은 응답 시간을 기록하였다. 이번 재측정에서는 Neo4j 최대 응답 시간도 24.492ms로 측정되어 이전 단일 측정에서 확인된 일시적 지연보다 안정적인 범위에 있었다.

## 11. 결과 해석

동일한 식재료·별칭·레시피 데이터를 PostgreSQL 정규화 모델과 Neo4j 그래프 모델에 각각 적재하고, 대표 조회 유형 4가지를 비교하였다. PK 기반 단순 조회와 별칭 정규화 조회에서는 PostgreSQL이 더 낮은 응답 시간을 기록하였다. 반면 입력 별칭에서 표준 식재료를 찾은 뒤 해당 식재료의 전체 별칭으로 연결된 레시피 Top 20을 조회하는 다단계 관계 조회에서는 Neo4j의 평균 응답 시간이 7.120ms로 PostgreSQL의 11.911ms보다 약 40.2% 낮았으며, 전체 p95도 Neo4j 12.076ms, PostgreSQL 22.268ms로 측정되었다. 복수 식재료 공통 레시피 조회에서도 Neo4j가 더 낮은 평균 및 p95 응답 시간을 기록하였다.

따라서 본 결과는 모든 조회에서 Neo4j가 우세하다는 의미가 아니라, 조회 유형에 따라 적합한 저장소가 다르다는 점을 보여준다. 단순 속성 및 식별자 기반 조회는 PostgreSQL이 적합하고, 별칭-식재료-레시피처럼 관계 확장 단계가 증가하는 조회는 Neo4j 그래프 모델이 효과적일 수 있다. 본 결과는 사용자·냉장고·영수증 등 트랜잭션성 데이터는 PostgreSQL에 저장하고, 식재료 가이드·별칭·레시피 연결처럼 관계 중심 탐색이 빈번한 데이터는 Neo4j에 저장한 현재 구조를 뒷받침한다.

측정 결과 PK 기반 단순 조회와 별칭 정규화 조회에서는 PostgreSQL이 더 낮은 평균 및 p95 응답 시간을 기록하였다. 반면 다단계 관계 조회에서는 Neo4j의 평균 응답 시간이 PostgreSQL보다 약 40.2% 낮았으며, 복수 식재료 공통 레시피 조회에서도 Neo4j가 더 낮은 평균 및 p95를 기록하였다. 이를 통해 사용자·냉장고·영수증과 같은 CRUD 및 트랜잭션 중심 데이터는 PostgreSQL에 저장하고, 식재료·별칭·레시피처럼 관계 확장 탐색이 빈번한 데이터는 Neo4j에 저장한 현재 구조의 선택 근거를 성능 측면에서 확인하였다.

## 12. 재실행 명령

비교용 PostgreSQL 테이블을 다시 적재하고 4개 대표 시나리오를 모두 측정하려면 다음 명령을 사용한다.

```powershell
docker exec bobbeori_backend python /project/app/backend/scripts/benchmark_food_guide_rdb_vs_neo4j.py --setup --scenario all --runs 100 --warmup 10 --limit 10
```

이미 적재된 `bench_` 테이블을 유지하고 다단계 관계 조회만 다시 수행하려면 다음 명령을 사용한다.

```powershell
docker exec bobbeori_backend python /project/app/backend/scripts/benchmark_food_guide_rdb_vs_neo4j.py --scenario expanded --runs 100 --warmup 10 --limit 10
```
