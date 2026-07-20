# User–Recipe 데이터 구조 및 타겟 분석

분석 기준일: 2026-07-19  
분석 코드: `user_recipe_analysis.py`, `User_Recipe_Data_Analysis.ipynb`  
원천: `storage/processed/recipe/`

## 0. 결론 요약

현재 데이터는 **개인화 collaborative filtering보다 레시피 단위 catalog/content ranking에 더 적합**하다.

- 카탈로그 레시피: 3,171개
- 카탈로그와 연결되는 댓글: 255건, 126개 레시피
- 카탈로그와 연결되는 리뷰: 990건, 563개 레시피
- 관측 user–recipe pair: 1,212개
- 관측 사용자: 967명
- 2개 이상 레시피와 관계가 있는 사용자: 85명
- 3개 이상 레시피와 관계가 있는 사용자: 25명
- 전체 카탈로그 기준 matrix density: 약 0.0395%

따라서 현재 `group_id`를 활용한 개인화 holdout은 표본이 매우 작다. 우선 레시피 메타데이터로 graded recipe target을 예측하는 cold-item ranking 문제를 풀고, 서비스 사용자 행동 로그가 충분히 축적된 후 개인화 모델을 분리하는 것이 안전하다.

또한 `group_id`는 서비스 회원 ID가 아니다. 크롤링한 작성자명을 정렬해 부여한 익명 그룹 ID이므로 애플리케이션 `users.id`와 직접 조인하거나 온라인 개인화 키로 사용하면 안 된다.

---

## 1. 데이터 소스와 분석 단위

| 데이터 | 행 수 | grain | 용도 |
|---|---:|---|---|
| `recipe_fix.csv` | 3,171 | recipe | 레시피 메타데이터·조회·스크랩 |
| `recipe_ingredient_alias.csv` | 3,171 | recipe | 재료·alias 정보 |
| `recipe_review.csv` | 3,171 | recipe | 크롤링 페이지가 표시한 댓글/요리후기 수 |
| `comment_by_llm.csv` | 258 raw / 255 catalog-match | comment event | 일반 댓글과 감성점수 |
| `review_by_llm.csv` | 1,007 raw / 990 catalog-match | review event | 요리후기·별점·감성점수 |

분석 산출물은 다음 grain으로 분리했다.

1. `recipe_table.csv`: `recipe_id`당 1행
2. `user_recipe_interactions.csv`: 관측된 `(user_id, recipe_id)` pair당 1행
3. `user_table.csv`: 관측된 `user_id`당 1행
4. `recipe_comment_stats.csv`: 댓글이 있는 `recipe_id`당 1행
5. `recipe_review_stats.csv`: 리뷰가 있는 `recipe_id`당 1행
6. `user_recipe_observed_matrix.csv`: 2D inspection view

2D matrix의 빈칸은 negative가 아니라 **unknown/unobserved**다. 이를 0점이나 비선호로 채우면 노출되지 않은 레시피를 싫어한 것으로 오해하게 된다.

---

## 2. Recipe table

`recipe_table.csv`는 레시피 ID 기준으로 다음 정보를 통합한다.

### 2.1 정적 메타데이터

- 레시피명
- 조리 방법·상황·재료 분류·요리 종류
- 인분·난이도·조리 시간
- 원재료 문자열·정규화 재료·alias
- 기타/기본 재료 개수

### 2.2 인기도·노출 메타데이터

- 조회 수, 스크랩 수
- 2024/2026 조회 수와 증가량·성장률
- 크롤링 화면의 댓글/요리후기 표시 수

조회·스크랩은 선호 타겟과 분리해야 한다. 이 값은 품질뿐 아니라 검색 노출, 등록 시점, 외부 유입의 영향을 받기 때문이다. item feature나 별도 engagement task에는 사용할 수 있지만 target과 baseline 양쪽에 동시에 넣으면 누수가 된다.

### 2.3 사용자 피드백 집계

- 댓글/리뷰 횟수와 고유 사용자 수
- 댓글/리뷰 텍스트 길이 및 원문 목록
- 감성 positive/negative 평균·표준편차
- 감성 margin 평균·중앙값·표준편차·최솟값·최댓값
- 감성 positive/negative/neutral 횟수와 비율
- 별점별 1~5점 횟수
- 별점 합계·평균·중앙값·표준편차·최솟값·최댓값
- Bayesian 별점과 빈도 보정 별점

레시피명은 3,165개가 고유하며 6개는 이름이 중복된다. 따라서 이름이 아니라 `recipe_id`를 반드시 primary key로 사용한다.

---

## 3. User table과 User–Recipe matrix

### 3.1 관측 관계

카탈로그 매칭 후:

| 관계 | pair 수 |
|---|---:|
| comment only | 222 |
| review only | 984 |
| comment and review | 6 |
| 합계 | 1,212 |

댓글과 리뷰 양쪽에 나타나는 사용자가 매우 적고, 같은 user–recipe pair에서 두 행동이 함께 관측된 경우는 6개뿐이다. 두 소스를 단순히 동일 행동으로 합치기보다 서로 다른 feedback channel로 유지해야 한다.

### 3.2 사용자 활동성

- 사용자 967명 중 882명은 관측 레시피가 1개뿐이다.
- 2개 이상 레시피: 85명
- 3개 이상 레시피: 25명

대부분의 사용자는 train/test interaction을 동시에 만들 수 없다. 현재 데이터에서 전체 사용자를 대상으로 personalized Recall@K를 계산하면 많은 사용자를 제외하거나 누수를 만들게 된다.

### 3.3 권장 저장 방식

학습용 source of truth는 dense matrix가 아니라 sparse long table로 둔다.

```text
user_id | recipe_id | has_comment | has_review | star_mean | review_sentiment | comment_sentiment | ...
```

`user_recipe_observed_matrix.csv`의 코드는 확인용이다.

- 1: comment only
- 2: review only
- 3: comment and review
- blank: unknown

---

## 4. 댓글 기반 User–Recipe 분석

카탈로그와 연결되는 댓글은 255건, 126개 레시피, 161명, 228개 pair다. 같은 사용자가 같은 레시피에 여러 댓글을 남긴 pair가 있으므로 event와 pair를 구분했다.

### 4.1 댓글 감성

| 감성 margin 부호 | 댓글 수 | 비율 |
|---|---:|---:|
| positive | 185 | 72.5% |
| negative | 30 | 11.8% |
| zero | 40 | 15.7% |

- margin 평균: 0.549
- margin 중앙값: 0.840
- 댓글은 리뷰보다 negative/neutral 분산이 크다.

따라서 댓글 감성은 별점보다 변별력이 있지만 coverage가 126 / 3,171로 4.0%에 불과하다. 댓글이 없는 레시피를 negative로 보면 안 되며, 댓글 감성은 보조 task 또는 weak label로 사용하는 것이 적절하다.

### 4.2 생성 통계

`recipe_comment_stats.csv`에는 댓글 횟수, 사용자 수, 원문, 텍스트 길이, positive/negative 확률, margin, 1~5 선형 감성점수 및 각 통계량을 저장했다.

감성 1~5 변환은 다음과 같다.

\[
sentiment_{1..5}=clip(3+2(positive-negative),1,5)
\]

이는 해석 가능한 선형 projection일 뿐 calibration이 아니다. 감성 모델의 확률 보정이 검증되기 전에는 절대적인 별점으로 취급하면 안 된다.

---

## 5. 리뷰·별점 기반 User–Recipe 분석

카탈로그와 연결되는 리뷰는 990건, 563개 레시피, 821명이며 user–recipe 중복 pair는 없다.

### 5.1 별점 분포

| 별점 | 리뷰 수 | 비율 |
|---:|---:|---:|
| 1 | 5 | 0.5% |
| 2 | 1 | 0.1% |
| 3 | 4 | 0.4% |
| 4 | 26 | 2.6% |
| 5 | 954 | 96.4% |

평균은 4.942이며 강한 ceiling effect가 있다. `별점 >= 3`은 positive 560 / 563, empirical Bayesian `>=3`은 563 / 563이므로 binary target으로 사용할 수 없다.

### 5.2 리뷰 감성

- positive margin: 964 / 990, 97.4%
- negative margin: 26 / 990, 2.6%
- margin 평균: 0.880
- margin 중앙값: 0.964

리뷰 감성도 별점과 마찬가지로 긍정에 치우쳐 있다. 단순히 0/5 또는 1~5로 바꿔 threshold를 적용해도 class imbalance가 해결되지 않는다.

### 5.3 별점 빈도 보정

논의한 의도를 반영해 별점 순서를 보존하는 mid-CDF ordinal score를 계산했다.

\[
q(s)=P(S<s)+\frac{1}{2}P(S=s),\quad x(s)=2q(s)-1
\]

| 별점 | mid-CDF score |
|---:|---:|
| 1 | -0.995 |
| 2 | -0.989 |
| 3 | -0.984 |
| 4 | -0.954 |
| 5 | 0.036 |

이 변환은 흔한 5점 하나를 강한 positive로 보지 않으면서 순서를 보존한다. 그러나 0 이상으로 다시 이진화하면 529 / 563(94.0%)가 positive다. 따라서 이 점수는 threshold binary label보다 **graded relevance**로 사용하는 것이 낫다.

표본 수 보정은 변환 후 별도로 적용한다.

\[
B_r=\frac{n_r\bar{x}_r+m\cdot0}{n_r+m},\quad m=3
\]

---

## 6. User–Recipe matrix에서 사용할 수 있는 타겟

타겟은 목적에 따라 분리해야 한다.

### 6.1 Catalog ranking 타겟

grain: recipe  
목표: 히스토리 없는 사용자에게 좋은 레시피 순위 제공

후보:

1. 현재 `n(5점)>=2` binary label
2. mid-CDF 별점의 Bayesian graded score
3. 댓글 감성·리뷰 감성을 분리한 multi-task recipe score
4. 별점 분포에 대한 Bayesian/Dirichlet posterior expected utility
5. confidence lower bound를 사용한 보수적 품질 점수

현재 데이터에는 2번 graded score가 가장 직접적인 다음 실험 후보다. binary threshold를 강제하지 않고 Spearman/NDCG로 평가한다.

### 6.2 Personalized recommendation 타겟

grain: user–recipe  
목표: 특정 사용자가 특정 레시피를 선호할 확률·순위 예측

관측 가능한 signal:

- 리뷰 별점과 리뷰 감성
- 댓글 여부와 댓글 감성
- 반복 댓글 횟수

그러나 사용자별 다중 레시피 이력이 부족하고, 미관측 노출 정보가 없다. 현 시점에서는 연구용 소규모 subset 외에 production personalized target으로 사용하기 어렵다.

### 6.3 Unknown과 negative

- 1~2점 또는 명시적 negative 감성: observed negative
- 댓글/리뷰 없음: unknown
- 노출됐지만 행동 없음: exposure log가 있어야 negative 후보가 됨

현재는 impression/exposure 로그가 없으므로 0 interaction을 negative로 샘플링할 때 selection bias가 발생한다.

---

## 7. 현재 타겟과 설정 이유

현재 코드의 타겟은 다음과 같다.

```text
recipe positive = 5점 리뷰가 2개 이상
interaction positive = positive recipe에 달린 모든 리뷰
```

이 설정이 선택된 현실적인 이유는 별점·감성 threshold가 거의 모두 positive가 되는 상황에서 `2개 이상`이라는 증거량 조건이 198 positive / 365 negative로 구분력을 만들기 때문이다. 즉 품질과 신뢰도를 동시에 간단히 반영한다.

하지만 다음 문제가 있다.

1. 리뷰 수가 많은, 즉 많이 노출된 레시피가 유리하다.
2. 레시피 label이므로 사용자별 선호 차이를 표현하지 못한다.
3. positive 레시피에 달린 모든 리뷰를 positive interaction으로 바꾼다.
4. 실제로 5점이 아닌 리뷰 15건이 positive interaction에 포함된다.
5. 그중 1점·2점 리뷰도 3건 포함되어 사용자 의도와 label이 반대로 학습된다.

따라서 이 타겟은 **provisional global recipe preference target**이라고 부르는 것이 정확하며 personalized preference target으로 설명하면 안 된다.

---

## 8. 타겟·평가지표 변경 실험의 영향

기존 비교 실험 결과:

| 타겟 | positive 비율 | 결과 |
|---|---:|---|
| 5점 리뷰 2개 이상 | 35.2% | 유일하게 binary 구분력 유지 |
| raw 평균 별점 >=3 | 99.5% | 기각: 극단 불균형 |
| empirical Bayesian 별점 >=3 | 100.0% | 기각: 단일 클래스 |
| 감성 binary >=3 | 97.0% | 기각: 극단 불균형 |
| Bayesian 별점+감성 >=5 | 98.0% | 기각: 극단 불균형 |
| mid-CDF 별점 >=0 | 94.0% | binary로는 여전히 불균형 |

positive prevalence가 달라지면 raw Recall@K는 직접 비교할 수 없다. 타겟을 바꿀 때는 동일한 target prevalence를 맞추거나 graded metric을 사용해야 한다.

### 8.1 Catalog 평가

- split: recipe-held-out
- primary: graded NDCG@K, Spearman, Kendall
- secondary: Precision/Recall@K, top-decile lift, coverage
- baseline: train recipe metadata만 사용하는 모델
- 금지: test recipe 리뷰로 만든 Bayesian popularity baseline

현재 recipe-held-out test 레시피에는 train 리뷰가 없으므로 리뷰 기반 Bayesian baseline은 모두 prior 동점이다. full-data Bayesian 순위는 in-sample oracle이지 일반화 baseline이 아니다.

### 8.2 Personalized 평가

- 대상: 최소 2~3개 레시피 이력이 있는 사용자만
- split: 가능하면 temporal leave-last-one-out
- 지표: per-user NDCG@K, Recall@K, MAP@K, catalog coverage
- 보고: eligible user 수와 bootstrap confidence interval

현재 eligible user가 85명 또는 25명뿐이며 timestamp도 없다. 결과는 탐색적 지표로만 해석해야 한다.

---

## 9. 추가 방법 검토

### 우선순위 A — 현재 데이터로 가능

1. **Graded catalog learning-to-rank**  
   mid-CDF 별점, 댓글 감성, 리뷰 감성을 각각 graded relevance로 유지하고 레시피 메타데이터로 예측한다.

2. **Hierarchical ordinal/Bayesian rating model**  
   평균 별점 하나가 아니라 1~5점 count 전체를 Dirichlet-Multinomial 또는 ordinal model로 추정하고 posterior mean·credible interval을 사용한다.

3. **Confidence-aware lower bound**  
   리뷰가 적은 레시피는 posterior lower bound로 보수적으로 순위를 낮춘다. 리뷰 수를 target 값에 직접 섞는 방식보다 품질과 신뢰도를 분리할 수 있다.

4. **Multi-task recipe model**  
   별점, 리뷰 감성, 댓글 감성, engagement를 하나로 더하지 않고 별도 head로 예측한 후 서비스 목적에 맞게 조합한다.

5. **Positive–Unlabeled learning**  
   미관측을 negative로 단정하지 않고 positive/unknown 문제로 다룬다.

### 우선순위 B — 데이터 추가 후

1. 서비스 user ID와 연결된 impression/click/save/cook-complete 로그 수집
2. event timestamp 수집
3. 추천 노출 후 무반응과 명시적 skip/dislike 구분
4. 사용자별 최소 5~10개 interaction 확보
5. pairwise preference 또는 BPR/weighted implicit model 실험

### 권장 실행 순서

1. 현행 모델의 목적을 catalog ranking으로 명시
2. mid-CDF/Bayesian graded target으로 recipe-level 실험
3. metadata-only baseline과 graded metric으로 검증
4. 댓글·리뷰·engagement multi-task ablation
5. 사용자 행동 로그 축적 후 personalized track을 별도 시작

---

## 재실행

```powershell
cd etl\ml_lightfm
docker compose run --rm jupyter python user_recipe_analysis.py
```

생성된 dense matrix의 빈칸은 반드시 unknown으로 유지한다.

