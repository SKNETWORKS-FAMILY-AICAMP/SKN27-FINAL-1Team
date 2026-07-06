# 01. 조회·스크랩 분리 실험 기록

`REVIEW_RANK_SCORE`에서 인기(조회·스크랩) 항을 빼 잔차 타깃으로 학습하고, 동일 컬럼을 feature로 넣었을 때 지표가 어떻게 변하는지 확인한 실험입니다.

**상태:** 실험 코드는 확인 후 **베이스라인으로 되돌림**. 본 문서만 실험 기록을 보존합니다.

---

## 1. 실험 일지

| 순서 | 일시 (KST) | 일시 (UTC) | 내용 |
|------|------------|------------|------|
| 1 | 2026-07-06 17:37:21 | 2026-07-06 08:37:21 | 베이스라인 실행 (`extra_trees`, 전체 타깃, feature 13개). `evaluation_report.json` 생성 |
| 2 | 2026-07-06 18:44~18:46 | — | `MODEL_NAME=lightgbm` 교체 시도. 패키지 미설치 후 설치·재실행. RMSE 2.14, Spearman 0.10으로 베이스라인 대비 하락 |
| 3 | 2026-07-06 23:09:57 | 2026-07-06 14:09:57 | 잔차 타깃 + 인기 feature 실험 실행. RMSE 0.38, Spearman 0.098. 테스트 6건 통과 |
| 4 | 2026-07-06 23:10~ | — | 순위 지표 개선 미미 판단. 실험 코드 되돌림, 본 문서(`EXPERIMENT.md`)에 기록 보존 |

---

## 2. 배경

### 2.1. 기존 `REVIEW_RANK_SCORE` (ETL 규칙)

```
REVIEW_RANK_SCORE
  = REVIEW_STAR_NORM_AVG
  + REVIEW_SENTIMENT_AVG
  + INQ_CNT_LOG_CENTERED
  + SRAP_CNT_LOG_CENTERED
```

- 라벨 있음(563건): `final_recommend_score` = 규칙 점수 (`rule`)
- 라벨 없음(2,608건): ML impute (`ml_imputed`)

### 2.2. 베이스라인 ML 설정

- `MODEL_NAME`: `extra_trees`
- `random_state`: 42, `test_size`: 0.2 (train 450 / test 113)
- feature 13개: 카테고리 5 + 인분·조리시간 2 + 재료 파생 6
- 인기 컬럼(`INQ_CNT_LOG_CENTERED`, `SRAP_CNT_LOG_CENTERED`)은 **feature에 미포함**

### 2.3. 실험 동기

타깃에 이미 들어 있는 조회·스크랩 신호를 feature로도 쓰면 평가가 부풀어 오를 수 있어, **타깃에서 인기 항을 빼고(잔차)** feature로 넣는 방식을 시험했습니다. 성능이 괜찮으면 ETL 공식 변경을 검토할 예정이었습니다.

---

## 3. 실험 설계

### 3.1. 학습 타깃 (잔차)

```
train_target = REVIEW_RANK_SCORE - INQ_CNT_LOG_CENTERED - SRAP_CNT_LOG_CENTERED
             ≈ REVIEW_STAR_NORM_AVG + REVIEW_SENTIMENT_AVG
```

### 3.2. 추가 feature

- `INQ_CNT_LOG_CENTERED`
- `SRAP_CNT_LOG_CENTERED`

(`NUMERIC_FEATURES`에 포함, 모델 입력 15개)

### 3.3. impute 시 최종 점수 복원

```
base_score = INQ_CNT_LOG_CENTERED + SRAP_CNT_LOG_CENTERED
final_recommend_score (unlabeled) = base_score + ml_predicted_residual
```

라벨 있는 행은 기존과 동일하게 `REVIEW_RANK_SCORE`(규칙 점수) 유지.

### 3.4. 변경 파일 (실험 시)

| 파일 | 변경 내용 |
|------|-----------|
| `config.py` | `POPULARITY_BASE_COLS`, `TARGET_FORMULA`, 인기 컬럼을 `NUMERIC_FEATURES`에 추가 |
| `main.py` | `y_train`/`y_test`/재학습 타깃을 `residual_target()`으로 변경 |
| `imputer.py` | `residual_target()`, `popularity_base_score()`, impute 시 `base + residual` |
| `evaluator.py` | `evaluation_report.json`에 `target_formula` 기록 |
| `test_recommendation_pipeline.py` | 잔차·복원 테스트 추가 |

---

## 4. 결과

동일 데이터·동일 `extra_trees`·동일 split 기준.

| 지표 | 베이스라인 (전체 타깃) | 실험 (잔차 타깃 + 인기 feature) |
|------|------------------------|----------------------------------|
| RMSE | 2.023 | 0.377 |
| MAE | 1.594 | 0.160 |
| R² | -0.208 | -0.196 |
| Spearman | **0.131** | 0.098 |
| Hit@10 | 0.20 | 0.20 |
| Hit@20 | **0.25** | 0.20 |
| Hit@50 | 0.50 | **0.52** |

실험 실행 시 터미널 출력 (2026-07-06 23:09:57 KST): `RMSE=0.3767  Spearman=0.0985`

### 4.1. 해석

1. **RMSE/MAE는 타깃 스케일이 달라져 직접 비교 불가**  
   잔차 타깃(별점+감성 근사)은 분산이 작아 절대 오차가 자연스럽게 줄어듭니다.

2. **순위 지표(우선 비교 대상)**  
   - Spearman: 0.131 → 0.098 (소폭 하락)  
   - Hit@10: 동일  
   - Hit@20: 0.25 → 0.20 (하락)  
   - Hit@50: 0.50 → 0.52 (소폭 상승)

3. **R²**는 여전히 음수 — 잔차(리뷰 품질)를 메타+인기로 맞추는 것도 쉽지 않음.

4. **부가 실험 (일지 #2):** `lightgbm`으로 모델만 교체 시 RMSE 2.14, Spearman 0.10으로 `extra_trees` 베이스라인보다 나빠짐 (소량 데이터 한계).

### 4.2. 결론 (당시 판단)

- 잔차 분리 + 인기 feature 추가만으로 **순위 품질이 뚜렷이 개선되지 않음**.
- ETL `REVIEW_RANK_SCORE` 공식 변경은 **보류**. 코드는 베이스라인으로 복원.
- 이후 검토: 인기 파생 feature 추가(`INQ_CNT_RATE` 등), 별점·감성은 impute 불가하므로 최후 순위.

---

## 5. 재현 방법

1. 위 「3.4. 변경 파일」 내용을 임시 적용 (또는 실험 커밋이 있으면 해당 브랜치/커밋 체크아웃).
2. 프로젝트 루트에서 실행:

```bash
python ai/recommendation/main.py
```

3. `ai/recommendation/artifacts/evaluation_report.json`에서 `target_formula`, feature 목록, 지표 확인.
4. 비교 후 `git checkout` 등으로 베이스라인 복원.

---

## 6. 참고

- 베이스라인 `evaluation_report.json`: 2026-07-06 17:37:21 KST (08:37:21 UTC), feature 13개.
- 실험 `evaluation_report.json`: 2026-07-06 23:09:57 KST (14:09:57 UTC), feature 15개, `target_formula` 포함.
- 파이프라인 사용법·입출력: [README.md](README.md)
