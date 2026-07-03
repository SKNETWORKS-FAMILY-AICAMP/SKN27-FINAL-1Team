# 식재료 가이드 README

> 업데이트: 2026-07-01

## 개요

식재료 가이드 분할 CSV를 Neo4j에 적재하고 웹·백엔드에서 활용하기 위한 프로젝트입니다.
현재 기준 데이터는 `storage/processed/food_guide`의 노드 8개·관계 8개 CSV입니다.

JY-3.1의 범위는 Graph DB 무결성 검증과 추천 연동 경계 확정입니다. 식재료 가이드는
Neo4j, 추천 레시피는 PostgreSQL/API가 담당하며 세부 완료 기준은 `docs/guide_neo4j.md`에 정리합니다.

## 기준 CSV 경로

기본 경로는 `storage/processed/food_guide`이며 단일 통합 CSV는 사용하지 않습니다.

## 사전 준비

1. **Requirements 업데이트**
   ```bash
   cd c:/dev/project/SKN27-FINAL-1Team/etl
   pip install -r requirements.txt
   ```
   Neo4j 관련 패키지(`neo4j`, `python-dotenv`)가 추가되었습니다.
2. **환경 변수** `.env`에 `NEO4J_PASSWORD`와 필요 시 `NEO4J_URI`, `NEO4J_USER`를 정의합니다.
3. **Docker 이미지 재빌드**
   ```bash
   docker compose build neo4j_load
   ```
   적재 코드나 Python 의존성을 변경했을 때만 필요합니다. CSV 내용만 바뀐 경우에는 재빌드하지 않아도 됩니다.

## 데이터 초기화 및 재적재

프로젝트 루트에서 다음 명령을 실행합니다.

```bash
docker compose up -d neo4j
docker compose run --rm --no-deps neo4j_load \
  python -m etl.food_guide.load_to_neo4j \
  --split-dir /project/storage/processed/food_guide --clear
```

`--split-dir`는 노드 CSV 8개를 먼저 적재하고 관계 CSV 8개를 ID로 연결합니다. 파일 누락, ID 중복, 잘못된 참조를 적재 전에 검사합니다. `--clear`는 식재료 가이드가 관리하는 그래프만 삭제하며 레시피 등 다른 데이터는 삭제하지 않습니다.

`docker compose up`을 실행하면 `neo4j_load`가 분할 CSV와 레시피 그래프를 초기화·적재한 뒤 종료합니다.

## 실행 및 검증

분할 로더가 적재 전에 필수 파일, ID 중복, 관계 중복과 잘못된 참조를 자동 검사합니다.

Neo4j 적재 후 노드 개수, 필수 관계 누락, 고아 노드를 검증합니다.

```bash
docker compose run --rm --no-deps neo4j_load \
  python -m etl.food_guide.validate_neo4j
```

누락 관계나 고아 노드가 하나라도 있으면 종료 코드 1을 반환합니다.

## 사용자 가이드 제보 검토

가이드 상세 화면에서 정보가 없는 항목을 회원이 제보하면 PostgreSQL의
`food_guide_suggestions`에 `pending` 상태로 저장됩니다. 제보 수가 많아도 자동으로
Neo4j에 반영하지 않으며, 개발자가 다음 쿼리로 서로 다른 사용자 제보를 확인합니다.

기존 PostgreSQL 볼륨을 사용하는 환경에서는 최초 1회 테이블을 생성합니다.

```bash
docker compose exec backend python -c \
  "from app.backend.db.models import FoodGuideSuggestion; from app.backend.db.session import engine; FoodGuideSuggestion.__table__.create(bind=engine, checkfirst=True)"
```

```sql
SELECT
    ingredient_code,
    ingredient_name,
    guide_type,
    LOWER(REGEXP_REPLACE(TRIM(content), '\s+', ' ', 'g')) AS normalized_content,
    COUNT(*) AS suggestion_count,
    COUNT(DISTINCT user_id) AS unique_user_count,
    MIN(created_at) AS first_suggested_at,
    MAX(created_at) AS last_suggested_at
FROM food_guide_suggestions
WHERE status = 'pending'
GROUP BY ingredient_code, ingredient_name, guide_type, normalized_content
HAVING COUNT(DISTINCT user_id) >= 3
ORDER BY unique_user_count DESC, last_suggested_at DESC;
```

내용과 출처를 확인한 뒤 승인·반려 상태를 기록합니다.

```sql
UPDATE food_guide_suggestions
SET status = 'approved',
    review_note = '출처 및 내용 확인 완료',
    reviewed_at = NOW()
WHERE id = :suggestion_id;
```

승인된 내용은 분할 CSV에 반영한 뒤 기존 Neo4j 재적재·검증 절차를 실행합니다.

```bash
# 적재 로그 확인
docker compose logs neo4j_load

# Ingredient 개수 확인
docker compose exec neo4j sh -lc \
  'cypher-shell -u neo4j -p "${NEO4J_AUTH#neo4j/}" \
  "MATCH (g:Ingredient) RETURN count(g) AS ingredients;"'

# 분류 단계별 개수 확인
docker compose exec neo4j sh -lc \
  'cypher-shell -u neo4j -p "${NEO4J_AUTH#neo4j/}" \
  "MATCH (n) WHERE n:MajorCategory OR n:MiddleCategory \
   RETURN labels(n)[0] AS label, count(n) AS count ORDER BY label;"'
```

현재 분할 CSV는 Neo4j에 다음과 같이 적재됩니다.

```text
MajorCategory: 4
MiddleCategory: 26
Ingredient: 389
Guide: 892
Source: 187
Alias: 913
SeasonMonth: 12
Nutrition: 388
```

## 품질·준법 검수 요약

### 자동 검수

- 검사 항목: 필수값, 출처, URL, 분류 경로·식품코드 중복, 제철 월 범위
- 현재 결과: 오류 0건, 경고 21건(코드 누락 1건, 중복 행 20건)
- URL 526건을 정상 형식으로 교정했고, 출처 근거가 없는 닭가슴살·닭날개 제철 월 값은 제거했다.
- Neo4j 결과: 노드 개수·필수 관계·고아 노드 검사 문제 0건

### 수동 표본 검수

- 4개 대분류에서 고정 시드로 12건을 추출했다.
- 결과: 적합 5건, 조건부 3건, 보완 필요 4건
- 우선 보완: 브로콜리 보관 문구, 굴 출처 URL, 소고기 손질 문구, 우유 신선도 기준
- 추가 확인: 월계수잎 형태 구분, 은행 섭취 안전, 미꾸라지 개별 기준

### 법적·윤리적 기준

- 공공데이터는 공식 제공본과 이용조건·공공누리 유형을 확인하고 출처를 표시한다.
- 민간 사이트 문장은 이용허락 없이 장문 복제하지 않고 필요한 사실만 독자적으로 요약한다.
- 개인정보·댓글·작성자 계정 정보는 수집하지 않으며 목적에 필요한 최소 데이터만 유지한다.
- LLM 문장은 초안임을 표시하고, 육류·수산물·유제품 등 안전 민감 항목은 사람이 검수한다.
- 광고·인증 문구를 신선도나 안전 기준으로 오인하게 표시하지 않는다.

참고: [공공데이터법](https://www.law.go.kr/LSW/lsInfoP.do?lsId=011895),
[공공데이터포털 이용정책](https://www.data.go.kr/ugs/selectPortalPolicyView.do),
[공공누리 이용조건](https://www.kogl.or.kr/etc/allMenu.do),
[개인정보 보호법 제16조](https://www.law.go.kr/LSW/lsLawLinkInfo.do?chrClsCd=010202&lsJoLnkSeq=900079387)

### 배포 전 확인

- [x] 분할 CSV 참조 무결성 오류 0건
- [ ] 보완 필요 표본의 문장·출처 수정
- [ ] 민간 자료 이용조건과 개인정보 포함 여부 확인
- [ ] LLM 초안 담당자 검수
- [x] Neo4j 누락 관계·고아 노드 0건
- [x] JY-3.1 Graph DB 검증 및 추천 연동 경계 확정

## 기타 주의사항

- CSV 스키마가 바뀔 경우 `etl/food_guide/load_to_neo4j/loader.py`의 매핑 로직을 수정해야 합니다.
- Docker 볼륨은 읽기 전용(`./storage:/project/storage:ro`)으로 마운트됩니다.
- 개발 중에는 `requirements.txt` 를 수정하면 반드시 `pip install -r requirements.txt` 와 Docker 재빌드를 수행하세요.


## 데이터 보완 과정

기존 통합 데이터를 기준으로 식재료 가이드 데이터를 보완했다.
현재 기준 파일의 대상은 전체 389개 식재료이며, 주요 보완 필드는 `보관`, `손질`, `세척`, `신선도체크`이다.

### 1. 원본 데이터 분석

먼저 원본 CSV에서 4개 가이드 필드의 누락 여부를 확인했다.

```text
검수 필드:
- 보관
- 손질
- 세척
- 신선도체크
```

기존에 값이 있는 셀은 유지하고, 비어 있는 셀만 보완 대상으로 분리했다.

### 2. 보완 방식 구분

누락 데이터는 식재료 분류에 따라 처리 방식을 나눴다.

```text
기존 가이드 참고:
- 소고기
- 돼지고기
- 닭고기
- 해물류
- 건어물류

카테고리 템플릿 + LLM 초안:
- 조미료/양념
- 가공식품류
- 면/빵/떡
- 곡류/전분
- 콩/견과류

추가 크롤링 데이터 참고:
- 달걀/유제품

LLM 자동생성 초안:
- 세척 기준이 없는 항목
- 특수 식재료
- 잘못된 유사 식재료 문장 교정
```

### 3. 추가 크롤링 데이터 적용

달걀/유제품은 별도 수집 데이터인 `dairy_guide_final.csv`를 참고했다.

`dairy_guide_final.csv`에는 다음 컬럼이 포함되어 있었다.

```text
대분류
중분류
식재료
보관법
손질법
신선도_확인법
출처명
출처_URL
```

적용 대상은 달걀/유제품 20개이다.

```text
가염버터, 그라다파다노치즈, 달걀, 리코타치즈, 마스카포네치즈,
메추리알, 모짜렐라치즈, 무염버터, 사워크림, 생크림,
슈레드피자치즈, 스트링치즈, 연유, 요구르트, 우유,
체다치즈, 크림치즈, 파마산치즈, 플레인요구르트, 휘핑크림
```

적용 방식은 다음과 같다.

```text
보관 → dairy_guide_final의 보관법 참고
손질 → dairy_guide_final의 손질법 참고
신선도체크 → dairy_guide_final의 신선도_확인법 참고
세척 → LLM 초안으로 유형별 문장 생성
```

유제품 세척 기준은 다음처럼 정리했다.

```text
버터류 / 치즈류 / 크림류 / 우유·발효유류:
세척하지 않는다.

달걀류:
사용 직전 오염물이 있을 경우에만 가볍게 닦거나 세척하고,
세척 후에는 바로 사용한다.
```

### 4. LLM 생성 셀

최종 CSV 기준 LLM이 적용된 가이드 셀은 총 664개이다.

```text
보관: 155개
손질: 155개
세척: 199개
신선도체크: 155개
```

LLM은 두 방식으로 사용했다.

첫째, 반복 패턴이 있는 분류에는 `카테고리 템플릿 + LLM 초안`을 적용했다.

```text
적용 분류:
- 조미료/양념
- 가공식품류
- 면/빵/떡
- 곡류/전분
- 콩/견과류
```

예를 들어 가루류는 습기와 직사광선을 피해 밀폐 보관하고 세척하지 않는 방식으로, 소스류는 제품 표시 기준에 따라 보관하고 세척하지 않는 방식으로 정리했다.

둘째, 기존 데이터나 크롤링 데이터로 직접 채우기 어려운 항목은 `LLM 자동생성 초안`으로 보완했다.

```text
주요 적용 대상:
- 달걀/유제품 세척
- 육류 세척
- 오리/훈제오리
- 날치알
- 훈제연어
- 잘못된 유사 식재료 문장 교정
- 장아찌류 세척 문장 교정
```

LLM으로 생성한 셀은 출처명을 `LLM 자동생성 초안`으로 표시하고, 출처URL은 빈 값으로 두었다.

### 5. 기존 유사 분류 가이드 참고

같은 분류 안에 이미 작성된 가이드가 있는 경우에는 기존 가이드를 우선 참고했다.

```text
소고기 부위 → 소고기 기존 가이드 참고
돼지고기 부위 → 돼지고기 기존 가이드 참고
닭고기 부위 → 닭고기 기존 가이드 참고
해물류 → 기존 해물류 가이드 참고
건어물류 → 기존 건어물류 가이드 참고
```

이때 기존 값은 덮어쓰지 않고, 빈 셀만 채웠다.
출처명에는 `기존 가이드 유형 확장` 또는 `분류 기존 가이드 참고`로 표시했다.

### 6. 민감 분류 별도 처리

육류, 수산물, 유제품은 보관과 세척 기준이 민감하므로 별도로 처리했다.

육류는 생고기 기준으로 보관, 손질, 세척, 신선도체크를 정리했다.
세척은 물에 씻는 방식이 아니라, 표면 수분을 키친타월로 제거하는 방향으로 처리했다.

수산물은 생선류, 고둥류, 알류, 가공수산물, 건어물류로 나누어 처리했다.
날치알과 훈제연어처럼 일반 생선류와 다른 항목은 LLM 초안으로 별도 문장을 작성했다.

유제품은 버터류, 치즈류, 크림류, 우유·발효유류, 달걀류로 나누어 처리했다.

### 7. 오류 문장 교정

자동 매칭 과정에서 잘못된 유사 식재료 문장이 남은 항목을 수정했다.

```text
수정 대상:
- 할라피뇨
- 망고
- 매실
- 바나나
- 아보카도
- 파인애플
- 당근
```

문제 예시는 다음과 같다.

```text
망고/매실/바나나/파인애플 → 귤 문장 잔여
아보카도 → 포도 문장 잔여
당근 → 연근 문장 잔여
할라피뇨 → 도라지 문장 잔여
```

해당 항목은 식재료별 특성에 맞는 문장으로 다시 작성했다.
이 교정 문장은 LLM 초안으로 처리하고, 출처명은 `LLM 자동생성 초안`으로 표시했다.

### 8. 가공식품 세척 문장 교정

가공식품류 중 일부 장아찌류에 일반 채소 세척 문장이 들어간 항목을 수정했다.

```text
수정 대상:
고추장아찌, 깻잎장아찌, 단무지, 더덕장아찌, 마늘장아찌,
마늘쫑장아찌, 매실장아찌, 무장아찌, 양파장아찌, 오이장아찌, 유자청
```

수정 기준은 다음과 같다.

```text
장아찌류:
일반적으로 세척하지 않는다.
염분을 줄이거나 양념을 덜어낼 경우에만 가볍게 헹군다.

유자청:
세척하지 않는다.
```

해당 세척 문장은 LLM 초안으로 처리하고, 출처명은 `LLM 자동생성 초안`으로 표시했다.

### 9. 출처 관리

가이드 필드별로 출처 컬럼을 따로 관리했다.

```text
보관 → 보관출처명 / 보관출처URL
손질 → 손질출처명 / 손질출처URL
세척 → 세척출처명 / 세척출처URL
신선도체크 → 신선도출처명 / 신선도출처URL
```

출처 처리 기준은 다음과 같다.

```text
공공데이터/크롤링 데이터 사용:
실제 출처명과 URL 유지

기존 가이드 참고:
기존 가이드 유형 확장 또는 분류 기존 가이드 참고 표시

LLM 생성:
LLM 자동생성 초안 표시
출처URL은 빈 값
```

### 10. 최종 검수 결과

최종 데이터는 다음 기준으로 검수했다.

```text
가이드 빈 값 여부
출처명 누락 여부
URL 형식 오류 여부
잘못된 유사 식재료 문장 잔여 여부
가공식품 세척 문구 적합성
육류/수산물 보관 문장 적합성
```

최종 결과는 다음과 같다.

```text
전체 식재료 수: 389개
보관 빈 값: 0개
손질 빈 값: 0개
세척 빈 값: 0개
신선도체크 빈 값: 0개
가이드 출처명 누락: 0개
제철 출처명 누락: 0개
URL 형식 오류: 0개
식품코드 경고: 21개 (누락 1개, 중복 행 20개)
```

최종 분할 CSV는 식재료 가이드 웹페이지와 Neo4j 조회에 사용하는 형태로 정리했다.
