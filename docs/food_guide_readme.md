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
   새 `cron_loader` 스크립트가 포함됩니다.

## 자동 Neo4j 적재
- `etl/load_to_neo4j/cron_loader.py` 가 60초마다 `food_guide_v1.csv` 의 수정 시간을 확인합니다.
- 변경이 감지되면 `upload.py` 를 호출해 CSV 데이터를 Neo4j에 `MERGE` 합니다.
- 로그에 `파일 변경 감지`와 `Neo4j upload completed` 가 출력됩니다.

## 실행 및 검증
```bash
# 컨테이너 로그 확인
docker compose logs -f etl

# Neo4j에 데이터가 들어갔는지 확인
docker compose exec neo4j cypher-shell -u neo4j -p "$NEO4J_PASSWORD" "MATCH (i:Ingredient) RETURN count(i);"
```
위 쿼리 결과가 0보다 크면 정상 적재된 것입니다.

## 기타 주의사항
- CSV 스키마가 바뀔 경우 `upload.py` 의 매핑 로직을 수정해야 합니다.
- Docker 볼륨은 읽기 전용(`./storage:/project/storage:ro`)으로 마운트됩니다.
- 개발 중에는 `requirements.txt` 를 수정하면 반드시 `pip install -r requirements.txt` 와 Docker 재빌드를 수행하세요.
