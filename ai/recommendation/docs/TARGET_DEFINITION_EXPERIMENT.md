# LightFM 타겟 정의 비교 실험

실행일: 2026-07-18  
실행 환경: `ai/experiments` Docker, LightFM WARP hybrid  
코드: `target_definitions.py`, `target_experiments.py`, `Target_Definition_Experiments.ipynb`

## 결론

제안된 1~4번 타겟은 현재 데이터에 그대로 적용하지 않는 것이 좋다. 모두 positive 비율이 97% 이상이며, 2번은 warm 레시피 전체가 positive인 단일 클래스가 된다. 이 상태의 Recall@K·Precision@K는 모델의 순위 구분력보다 높은 positive prevalence를 주로 반영한다.

현재 후보 중에는 기존 `5점 리뷰 2개 이상`만 모델 선택에 사용할 최소 구분력을 유지한다. 따라서 단기적으로는 기존 타겟을 유지하되, 이것을 최종 타겟으로 확정하지는 않는다. 기존 정의 역시 선호뿐 아니라 리뷰 수·노출도를 강하게 반영하기 때문이다.

## 타겟 해석

모호성을 없애기 위해 모든 후보의 최종 label unit을 레시피로 통일했다.

| mode | 레시피 점수/조건 | positive 조건 |
|---|---|---|
| legacy | 5점 리뷰 개수 | `n(star=5) >= 2` |
| 제안 1 | 레시피의 raw 별점 평균 | `mean(star) >= 3` |
| 제안 2 | `m=3`, 전체 별점 평균 prior를 적용한 Bayesian 별점 | `bayesian_star >= 3` |
| 제안 3 | 리뷰마다 `positive-negative > 0`이면 5, 아니면 0으로 변환 후 레시피 평균 | `sentiment_binary_mean >= 3` |
| 제안 4 | 제안 2의 Bayesian 별점 + 제안 3의 감성 점수 | 합계 `>= 5` |

학습 interaction은 해당 label이 positive인 레시피에 달린 리뷰로 만들었다. 모든 mode에서 같은 item feature, seed, epoch, recipe-level split을 사용했다.

## 실험 결과

| mode | positive / warm | positive 비율 | CV | mean Recall@20 | baseline | gap | 판정 |
|---|---:|---:|---:|---:|---:|---:|---|
| legacy | 198 / 563 | 35.2% | 5-fold × 5 seeds | 0.2354 | 0.1516 | +0.0838 | 비교 가능 |
| 제안 1 | 560 / 563 | 99.5% | 3-fold × 5 seeds | 0.1068 | 0.1071 | -0.0004 | 불균형, 진단 전용 |
| 제안 2 | 563 / 563 | 100.0% | 불가 | — | — | — | 단일 클래스, 기각 |
| 제안 3 | 546 / 563 | 97.0% | 5-fold × 5 seeds | 0.1813 | 0.1813 | 0.0000 | 불균형, 진단 전용 |
| 제안 4 | 552 / 563 | 98.0% | 5-fold × 5 seeds | 0.1812 | 0.1812 | 0.0000 | 불균형, 진단 전용 |

legacy는 5개 seed 모두에서 baseline Recall@20보다 높았다. 반면 제안 1~4는 positive가 거의 전부이므로 상위 20개가 대부분 정답이 되는 천장 현상이 발생했다. 예를 들어 full-fit Precision@20은 모든 mode가 1.0이어서 타겟 선택에 아무 정보도 주지 못한다.

## 평가 설계상 주의점

현재 CV는 recipe-held-out으로 cold-item 일반화 능력을 본다. test 레시피는 train 리뷰가 전혀 없으므로 리뷰 기반 Bayesian popularity 점수도 계산할 수 없다. 따라서 baseline은 train global prior로 채워져 동점이 되며, 동점 정렬 순서에 따라 Recall이 달라진다.

즉 위 baseline gap은 기존 파이프라인과의 재현·내부 비교에는 쓸 수 있지만, “Bayesian 순위보다 실제로 더 좋다”는 강한 근거로 사용하면 안 된다. full-data Bayesian 순위와의 비교는 같은 리뷰로 타겟과 baseline을 만드는 in-sample oracle 진단이며 일반화 평가가 아니다.

## 다음 타겟 실험 권고

1. 사용자별 timestamp가 있으면 마지막 interaction을 test로 두는 temporal user holdout으로 바꾼다.
2. timestamp가 없다면 최소한 review-row holdout을 사용하고, 같은 user/recipe의 정보 누수를 검사한다.
3. 후보별 positive 비율을 비슷하게 맞춘 뒤 비교한다. 현재 별점은 5점 동률이 너무 많아 단순 threshold/quantile만으로도 충분하지 않다.
4. 감성 확률을 0/5로 이진화하지 않고 `positive-negative` 연속 relevance를 유지하는 대조군을 둔다.
5. 리뷰 수를 타겟 자체에 넣을 것인지, Bayesian confidence/표본 가중치로만 사용할 것인지 분리해서 실험한다.
6. 모델 선택은 Recall@20 단독이 아니라 Precision@20, NDCG@20, prevalence 대비 lift, seed 분산을 함께 사용한다.

## 재실행

```powershell
cd ai\experiments
docker compose run --rm jupyter python target_experiments.py
```

환경 변수 `TARGET_CV_EPOCHS`, `TARGET_FULL_EPOCHS`, `TARGET_MODES`로 실행 범위를 조정할 수 있다. 이 실험은 production `outputs/recipe_lightfm.csv`를 교체하지 않는다.

