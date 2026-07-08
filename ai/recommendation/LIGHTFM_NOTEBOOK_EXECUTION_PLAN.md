# LightFM 노트북 실행·운영 계획서

본 문서는 `ai/experiments/ML Based Collaborative Filtering with LightFM.ipynb`를 기준으로,
LightFM 추천 엔진 구축/성능평가를 **문서 기반으로 통제**하기 위한 실행 기준이다.

## 1) 문서 목적과 범위

### 목적
- 노트북 기반 실험/평가를 재현 가능한 절차로 표준화한다.
- 작업을 사용자 관점의 작은 Todo로 분해하고, 질의 기반으로 지속 보강한다.
- LLM으로 구현 시 결과물 방향이 흔들리지 않도록 단일 기준 문서를 제공한다.

### 범위(In Scope)
- 노트북 실행 절차 정의 (데이터 로드 → matrix 생성 → 학습 → 평가 → 결과 기록)
- 성능 평가 기준(Go/No-Go) 정의
- Todo 템플릿/상태 전이/세분화 규칙 정의
- 초기 백로그 작성 및 이후 보강 프로토콜 정의

### 비범위(Out of Scope)
- 서비스 코드 직접 구현
- 프로덕션 배포/스케줄링/서빙 파이프라인 구현
- DB 스키마 변경 및 API 연동 구현

---

## 2) 입력 데이터 계약

### 입력 원천
- `storage/processed/recipe/review_by_llm.csv`
  - 핵심 컬럼: `recipe_id`, `group_id`, `star_count`, `star_norm`, `positive`, `negative`
- `storage/processed/recipe/recipe_fix.csv`
  - 레시피 메타 및 item feature 생성 원천

### 데이터 계약 규칙
- 학습 interaction의 user 키: `group_id` (Phase 0 proxy user)
- 학습 interaction의 item 키: `recipe_id`
- interaction 값(`interaction_value`)은 실험 단위로 아래 중 하나를 택해 고정:
  - Binary(1), `star_norm`, `positive-negative`, hybrid 조합
- 리뷰 없는 레시피는 interaction 없이 item feature만으로 예측 대상에 포함

---

## 3) 노트북 표준 실행 단계(셀 의존성 기준)

`ML Based Collaborative Filtering with LightFM.ipynb`는 아래 순서로만 실행한다.

1. **환경/라이브러리 셀**
   - `Dataset`, `LightFM`, `random_train_test_split`, `precision_at_k`, `recall_at_k` import
2. **데이터 로드 셀**
   - `review_by_llm.csv` 로드, 핵심 컬럼 정합성 확인
3. **ID 세트 구성 셀**
   - `user_ids = group_id unique`, `item_ids = recipe_id unique`
4. **LightFM Dataset fit/build 셀**
   - `dataset.fit(users=user_ids, items=item_ids)`
   - interaction matrix 생성
5. **train/test 분할 셀**
   - `random_train_test_split(..., test_percentage=0.2, random_state=42)` 기준
6. **모델 학습 셀**
   - 기본 loss=`warp`, epoch 고정 후 학습
7. **평가 셀**
   - `precision_at_k`, `recall_at_k` 계산
   - 필요 시 epoch별 추이(학습 곡선) 확인
8. **결과 기록 셀**
   - 실험 설정/지표/해석을 문서용 포맷으로 정리

### 셀 실행 원칙
- 위 단계 순서를 바꾸지 않는다.
- 중간 셀만 재실행할 경우, matrix/분할/모델 상태가 섞이지 않도록 반드시 초기화 셀부터 다시 실행한다.
- MovieLens 예시 문맥은 참고로만 두고, 프로젝트 데이터 흐름(`review_by_llm`, `group_id`, `recipe_id`)을 우선한다.

---

## 4) 성능 평가 게이트(Go / No-Go)

본 단계는 “모델 우열 확정”이 아니라 “다음 구현 단계를 진행해도 되는지”를 판정한다.

### 필수 리포트
- `precision@k` (k=5, 10)
- `recall@k` (k=5, 10)
- interaction sparsity(유저 수/아이템 수/interaction 수/density)
- split/seed/interaction_target/loss 설정값

### 기준선(Baseline)
- 인기 기반 baseline(조회/스크랩 또는 단순 인기 순위)과 비교
- LightFM 결과가 baseline 대비 열위면 No-Go

### Go 조건(초안)
- Precision@10, Recall@10이 baseline 대비 개선 또는 최소 동등
- seed 변경 시(최소 3회) 핵심 지표 급변이 없을 것
- 실험 설정과 결과 해석이 문서 템플릿에 누락 없이 기록될 것

### No-Go 조건(초안)
- baseline 대비 지속 열위
- seed/분할 변경 시 지표 변동이 과도하여 결론 재현 불가
- 데이터 계약 위반(필수 컬럼 누락/키 불일치) 발생

---

## 5) Todo 운영 템플릿 및 상태 규칙

## 5.1 Todo 템플릿 (고정)

아래 형식을 모든 Todo에 강제한다.

```markdown
- [상태] 작업명
  - Why: 이 작업이 필요한 이유
  - What: 입력/출력(산출물) 정의
  - Check: 검증 방법(어떤 값/화면/로그를 확인하는지)
  - DoD: 완료 판정 기준(언제 done인지)
```

### 상태값
- `todo`: 시작 전
- `doing`: 진행 중
- `blocked`: 외부 의존/결정 필요
- `done`: DoD 충족

### 세분화 규칙
- 1개 Todo는 30~90분 내 완료 가능한 단위로 유지
- 90분 이상 예상되면 즉시 하위 Todo로 분할
- 분할 시 상위 Todo는 `doing` 유지, 하위 Todo 완료 후 상위 `done`

---

## 6) 초기 백로그(Epic → Task)

## E1. 데이터 준비 및 정합성 검증
- [todo] `review_by_llm.csv` 필수 컬럼 정합성 체크
- [todo] `group_id`, `recipe_id` 유니크/분포 요약
- [todo] interaction sparsity 기본 리포트 생성

## E2. Interaction/Feature 매트릭스 구성 문서화
- [todo] interaction target 정의(Binary/star_norm/sentiment/hybrid)
- [todo] `Dataset.fit/build_interactions` 절차 고정
- [todo] item feature 포함/미포함 실험 경로 정의

## E3. LightFM 학습 파이프라인(노트북) 표준화
- [todo] 기본 하이퍼파라미터(loss, epochs, threads) 표준값 고정
- [todo] 학습 셀 실행 순서와 재실행 규칙 문서화

## E4. 오프라인 평가
- [todo] Precision@K/Recall@K 계산 셀 표준화
- [todo] baseline 비교 절차 문서화
- [todo] seed 반복(최소 3회) 결과 요약 템플릿 작성

## E5. 리포트/재현성
- [todo] 실험 기록 템플릿(설정/결과/해석/의사결정) 정의
- [todo] Go/No-Go 판정 섹션 작성

## E6. 다음 단계 준비(링크만)
- [todo] 구현 문서로 넘길 입력 항목 목록화
- [todo] 범위 밖 항목(서비스 연동/배포) 별도 분리

---

## 7) 질의 기반 보강 프로토콜

사용자와의 대화로 문서를 계속 보강할 때, 아래 절차를 고정한다.

1. **질문 수신**
   - 질문이 어느 Epic/Task에 해당하는지 먼저 라벨링
2. **세분화**
   - 해당 Todo를 더 작은 하위 Todo로 분해(30~90분 단위)
3. **문서 반영**
   - 상태 업데이트(`todo/doing/blocked/done`)
   - 변경 이유와 결정 근거 1~2줄 기록
4. **검증 정의**
   - 새로 분해한 Todo마다 Check/DoD를 즉시 채움
5. **다음 최소 작업 지정**
   - 항상 다음에 시작할 1개 작업을 명시

### 변경 이력 규칙
- 문서 하단에 날짜 단위 변경 로그를 유지한다.
- 로그에는 최소 3개를 기록한다:
  - 무엇을 바꿨는지
  - 왜 바꿨는지
  - 다음 액션이 무엇인지

---

## 8) 문서 업데이트 체크리스트

문서를 갱신할 때마다 아래를 점검한다.

- [ ] 범위 밖 구현 내용이 섞이지 않았는가
- [ ] 새 Todo가 템플릿(Why/What/Check/DoD)을 모두 포함하는가
- [ ] 상태값이 4단계 규칙을 지키는가
- [ ] 기준선/평가 게이트 변경 시 근거를 남겼는가
- [ ] 다음 최소 작업이 1개 이상 지정되었는가

---

## 9) 현재 시점의 다음 최소 작업

1. E1의 첫 작업(`review_by_llm.csv` 필수 컬럼 정합성 체크)을 `doing`으로 전환
2. 정합성 체크 결과를 Check/DoD 형식으로 기록
3. 결과에 따라 E1 하위 작업을 추가 분해

