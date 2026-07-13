# Neo4j 식재료-레시피 전체 흐름

이 문서는 현재 코드 기준으로 Neo4j에 적재되는 식재료 가이드 그래프와 레시피 그래프가 어떻게 연결되는지 한눈에 보기 위해 정리한 문서입니다.

## 1. 전체 요약

현재 Neo4j는 두 그래프를 함께 담습니다.

```text
식재료 가이드 그래프
대분류 → 중분류 → 식재료 → 별칭/가이드/제철/영양/출처

레시피 그래프
레시피 → 별칭
리뷰어 → 레시피
```

두 그래프의 연결점은 `Alias`입니다.

```text
Ingredient -[:HAS_ALIAS]-> Alias <-[:USES_ALIAS]- Recipe
```

즉, 레시피는 식재료 원재료명에 직접 연결되지 않고, 레시피 재료명을 정규화한 `Alias`를 통해 식재료와 간접 연결됩니다.

## 2. 식재료 가이드 그래프

적재 코드:

```text
etl/food_guide/load_to_neo4j/loader.py
```

기준 CSV:

```text
storage/processed/food_guide
```

노드 CSV 8개:

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

관계 CSV 8개:

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

구조:

```text
(:MajorCategory)-[:HAS_MIDDLE]->(:MiddleCategory)
(:MiddleCategory)-[:HAS_INGREDIENT]->(:Ingredient)

(:Ingredient)-[:HAS_ALIAS]->(:Alias)
(:Ingredient)-[:HAS_GUIDE]->(:Guide)
(:Guide)-[:SOURCED_FROM]->(:Source)

(:Ingredient)-[:IN_SEASON]->(:SeasonMonth)

(:Ingredient)-[:HAS_NUTRITION]->(:Nutrition)
(:Nutrition)-[:SOURCED_FROM]->(:Source)
```

역할:

| 노드 | 의미 |
| --- | --- |
| `MajorCategory` | 대분류 |
| `MiddleCategory` | 중분류 |
| `Ingredient` | 표준 식재료명 |
| `Alias` | 사용자 입력명, 만개의레시피 재료명, 기존 표시명 |
| `Guide` | 보관/손질/세척/신선도 가이드 |
| `SeasonMonth` | 제철 월 |
| `Nutrition` | Neo4j에 적재된 기본 영양성분 |
| `Source` | 가이드/영양 출처 |

적재 후 `Ingredient`에는 기존 Guide API 호환을 위해 `FoodGuide` 라벨과 조회용 속성도 함께 부여됩니다.

예:

```text
Ingredient: 파
 ├─ Alias: 대파
 ├─ Alias: 실파
 ├─ Alias: 쪽파
 ├─ Guide: 보관
 ├─ SeasonMonth: 1월
 └─ Nutrition
```

## 3. 레시피 그래프

적재 코드:

```text
etl/recipe/load_to_neo4j/loader.py
```

기준 CSV:

```text
storage/processed/recipe/recipe_fix.csv
storage/processed/recipe/review_by_llm.csv
storage/processed/recipe/comment_by_llm.csv
storage/processed/recipe/recipe_ingredient_alias.csv
```

구조:

```text
(:Recipe)
(:Reviewer)

(:Reviewer)-[:WROTE_REVIEW]->(:Recipe)
(:Reviewer)-[:WROTE_COMMENT]->(:Recipe)

(:Recipe)-[:USES_ALIAS]->(:Alias)
```

역할:

| 노드/관계 | 의미 |
| --- | --- |
| `Recipe` | 레시피 |
| `Reviewer` | 리뷰/댓글 작성자 |
| `WROTE_REVIEW` | 리뷰 작성 관계, 별점/감성 점수 포함 |
| `WROTE_COMMENT` | 댓글 작성 관계, 감성 점수 포함 |
| `USES_ALIAS` | 레시피가 사용하는 재료 Alias 연결 |

`Recipe` 노드에는 추천/랭킹에 필요한 집계 속성이 들어갑니다.

```text
inqCnt
inqCntRate
inqCntLogCentered
srapCnt
srapCntLogCentered
reviewStarNormAvg
reviewSentimentAvg
reviewRankScore
ingredientsNormalized
othersItems
```

## 4. 식재료와 레시피의 연결 방식

레시피 원문 재료명은 바로 `Ingredient`에 연결하지 않습니다.

먼저 레시피 재료명을 `recipe_ingredient_alias.csv`에서 정규화하고, 매칭된 alias id를 기준으로 Neo4j의 `Alias` 노드에 연결합니다.

```text
recipe_ingredient_alias.csv
 → aliases_matched
 → alias_id
 → (:Recipe)-[:USES_ALIAS]->(:Alias)
```

최종 연결 흐름:

```text
(:Recipe)
  -[:USES_ALIAS]->
(:Alias)
  <-[:HAS_ALIAS]-
(:Ingredient)
  <-[:HAS_INGREDIENT]-
(:MiddleCategory)
  <-[:HAS_MIDDLE]-
(:MajorCategory)
```

예:

```text
Recipe: 파김치 레시피
 └─ USES_ALIAS → Alias: 대파
                  ↑
              HAS_ALIAS
                  │
              Ingredient: 파
                  ↑
              HAS_INGREDIENT
                  │
              MiddleCategory: 채소류
                  ↑
              HAS_MIDDLE
                  │
              MajorCategory: 농산물
```

## 5. 주요 조회 시나리오

### 5.1 식재료 기준 관련 레시피 조회

```cypher
MATCH (ingredient:Ingredient {name: $name})-[:HAS_ALIAS]->(alias:Alias)<-[:USES_ALIAS]-(recipe:Recipe)
RETURN recipe
```

예:

```text
파 → 대파/쪽파/실파 Alias → 해당 Alias를 쓰는 Recipe 조회
```

### 5.2 레시피 기준 표준 식재료 조회

```cypher
MATCH (recipe:Recipe {recipeId: $recipeId})-[:USES_ALIAS]->(alias:Alias)<-[:HAS_ALIAS]-(ingredient:Ingredient)
RETURN ingredient, alias
```

예:

```text
레시피 원문: 대파
Alias: 대파
표준 식재료: 파
```

### 5.3 식재료 가이드와 레시피 함께 조회

```cypher
MATCH (ingredient:Ingredient {name: $name})
OPTIONAL MATCH (ingredient)-[:HAS_GUIDE]->(guide:Guide)
OPTIONAL MATCH (ingredient)-[:HAS_ALIAS]->(alias:Alias)<-[:USES_ALIAS]-(recipe:Recipe)
RETURN ingredient, collect(DISTINCT guide) AS guides, collect(DISTINCT recipe) AS recipes
```

예:

```text
마늘
 ├─ 보관/손질/세척/신선도 가이드
 ├─ 영양성분
 └─ 마늘 Alias를 쓰는 레시피 목록
```

### 5.4 리뷰 점수 기반 레시피 추천

```cypher
MATCH (ingredient:Ingredient {name: $name})-[:HAS_ALIAS]->(:Alias)<-[:USES_ALIAS]-(recipe:Recipe)
RETURN recipe
ORDER BY recipe.reviewRankScore DESC
LIMIT 10
```

## 6. 적재 순서

Docker 기준:

```text
neo4j
 → neo4j_load
    1. 식재료 가이드 그래프 적재
    2. 레시피/리뷰 그래프 적재
    3. Recipe -[:USES_ALIAS]-> Alias 연결
```

수동 실행:

```bash
python -m etl.food_guide.load_to_neo4j --split-dir storage/processed/food_guide --clear
python -m etl.recipe.load_to_neo4j
```

주의:

- `Alias`는 식재료 가이드 그래프에서 먼저 생성되어야 합니다.
- 레시피 그래프는 기존 `Alias` 노드를 찾아 `USES_ALIAS` 관계를 만듭니다.
- 따라서 레시피 그래프만 먼저 적재하면 `USES_ALIAS` 연결이 누락될 수 있습니다.

## 7. 현재 설계의 핵심

```text
Ingredient는 표준 식재료명
Alias는 사용자 표현과 레시피 원문 재료명
Recipe는 Alias를 통해 Ingredient와 연결
Guide/Nutrition/Season은 Ingredient 기준으로 조회
Review/Comment는 Recipe 기준으로 추천 점수에 활용
```

한 줄 요약:

```text
Neo4j 전체 구조는 식재료 표준화 그래프와 레시피 활용 그래프가 Alias를 중심으로 만나는 구조입니다.
```

## 8. 설명용 예시

발표나 팀 공유에서는 `파` 예시가 가장 이해하기 쉽습니다.

### 8.1 표준 식재료와 별칭

현재 식재료 가이드 데이터에서 `대파`는 별도 표준 식재료가 아니라, 표준 식재료 `파`의 Alias로 연결됩니다.

```text
Ingredient: 파
 ├─ Alias: 파
 ├─ Alias: 대파
 ├─ Alias: 실파
 ├─ Alias: 쪽파
 └─ Alias: 대파뿌리
```

이 구조 덕분에 사용자가 `대파`, `쪽파`, `실파`처럼 입력해도 내부 기준 식재료 `파`로 묶어서 조회할 수 있습니다.

### 8.2 레시피와 연결되는 방식

레시피 원문 재료에 `대파`가 등장하면 레시피는 `Ingredient: 파`에 바로 붙지 않고 `Alias: 대파`에 연결됩니다.

```text
Recipe: 대파가 들어간 레시피
  └─ USES_ALIAS
      ↓
Alias: 대파
  ↑
HAS_ALIAS
  │
Ingredient: 파
```

즉, 실제 연결 경로는 다음과 같습니다.

```text
Recipe -[:USES_ALIAS]-> Alias: 대파 <-[:HAS_ALIAS]- Ingredient: 파
```

### 8.3 이 구조로 가능한 질문

```text
대파 보관법 알려줘
```

처리 흐름:

```text
대파
→ Alias: 대파
→ Ingredient: 파
→ 파의 보관/손질/세척/신선도 가이드 조회
```

```text
대파 들어가는 레시피 추천해줘
```

처리 흐름:

```text
Ingredient: 파
→ 연결된 Alias 목록 조회
→ 파/대파/실파/쪽파 Alias를 쓰는 Recipe 조회
→ 리뷰 점수나 추천 점수 기준 정렬
```

### 8.4 설명용 한 문장

```text
사용자와 레시피는 '대파'라고 말하지만, 시스템은 Alias를 통해 표준 식재료 '파'로 연결해서 가이드와 레시피를 함께 조회합니다.
```

### 8.5 추가 예시: 마늘

`마늘`은 표준 식재료로 존재하고, 마늘 관련 가공/부위 표현은 별도 식재료 또는 Alias로 관리됩니다.

```text
Ingredient: 마늘
 └─ Alias: 마늘

별도 Ingredient:
 ├─ 마늘장아찌
 ├─ 마늘쫑장아찌
 ├─ 마늘가루
 ├─ 마늘종
 └─ 풋마늘
```

이 예시는 통합과 분리 기준을 설명할 때 좋습니다.

```text
대파/쪽파/실파는 '파'의 표현 차이로 묶고,
마늘장아찌/마늘가루/마늘종은 사용 맥락이 달라 별도 식재료로 둡니다.
```
