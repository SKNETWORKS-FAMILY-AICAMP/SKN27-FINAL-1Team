# 식재료 가이드 README

## 개요
`storage/processed/food_guide/food_guide_v1.csv` 를 Neo4j에 자동 적재하고, 웹·백엔드에서 활용하기 위한 프로젝트입니다.

## 사전 준비
1. **Requirements 업데이트**
   ```bash
   cd c:/dev/project/SKN27-FINAL-1Team/etl
   pip install -r requirements.txt
   ```
   Neo4j 관련 패키지(`neo4j`, `graphdatascience`, `python-dotenv`)가 추가되었습니다.
2. **환경 변수** `.env`에 `NEO4J_PASSWORD`(및 필요 시 `NEO4J_URI`, `NEO4J_USER`)를 정의합니다.
3. **Docker 이미지 재빌드**
   ```bash
   docker compose down
   docker compose up -d --build
   ```
   `food_guide_load` one-shot 적재 서비스가 포함됩니다.

## 자동 Neo4j 적재
- Docker Compose `food_guide_load` 서비스가 `python -m etl.food_guide.load_to_neo4j` 로 1회 적재 후 종료합니다.
- 적재 로직: `etl/food_guide/load_to_neo4j/loader.py` 의 `load_food_guide_to_neo4j`
- `backend`는 `food_guide_load`가 성공적으로 끝난 뒤 기동합니다.

## 실행 및 검증
```bash
# 적재만 다시 실행
docker compose run --rm food_guide_load

# 적재 로그 확인
docker compose logs food_guide_load

# Neo4j에 데이터가 들어갔는지 확인
docker compose exec neo4j cypher-shell -u neo4j -p "$NEO4J_PASSWORD" "MATCH (g:FoodGuide) RETURN count(g);"
```
위 쿼리 결과가 0보다 크면 정상 적재된 것입니다.

## 기타 주의사항
- CSV 스키마가 바뀔 경우 `etl/food_guide/load_to_neo4j/loader.py` 의 매핑 로직을 수정해야 합니다.
- Docker 볼륨은 읽기 전용(`./storage:/project/storage:ro`)으로 마운트됩니다.
- 개발 중에는 `requirements.txt` 를 수정하면 반드시 `pip install -r requirements.txt` 와 Docker 재빌드를 수행하세요.
