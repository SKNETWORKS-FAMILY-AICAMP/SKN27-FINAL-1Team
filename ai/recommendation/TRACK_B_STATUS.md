# Track B Base Score — 상태 보고서

**갱신:** 2026-07-14 — **동결 해제** · 실험 **28** (기준선 이진 Go) 진행.

상세 헌장 → [`METRICS.md`](METRICS.md) · 실측 → [`experiments.md`](experiments.md) §28.

---

## 1. 한 줄 결론 (신규 목표)

메타데이터 LightFM hybrid로 **전 카탈로그 점수 `s_pref`**를 내고, warm에서 **5점 리뷰 ≥2** 여부를 **기준선 `t*`**(train True의 min(s)) 위/아래로 맞춘다.  
**Spearman·bar 미세 순위는 1차 Go에서 제외.** cold 2608은 warm Go 후 동일 `s`·`prefer_hat` export.

---

## 2. 채택 설정 (실험 28)

| 항목 | 값 |
|------|-----|
| 정답 y* | `n_star5 ≥ 2` vs warm 나머지 |
| 학습 | WARP hybrid; **True 리뷰만** interaction 양성 |
| `POSITIVE_MODE` | **`prefer_n_star5_ge2`** (default) |
| features | `EXCLUDED=ingredients`; view/scrap log1p |
| epochs | CV 10 / full 30 |
| 기준선 | **`t* = min(s \| y*=1)`** on train |
| 1차 Go | **P0~P3** ([METRICS.md](METRICS.md)) |
| 실행 | `exp28_prefer_threshold.py` |

---

## 3. export (§28 실측)

| 파일 | 상태 |
|------|------|
| `outputs/exp28_report.json` | 생성됨 |
| `outputs/recipe_prefer_ranked.csv` | 3171행 (진단) |
| `outputs/recipe_lightfm.csv` | **No-Go — 미교체** (동결 export 유지) |

**§28 CV:** 0/5 seed P1~P3 통과. `min(s)` 임계 → Spec≈0.11. pop AUC·P@20 우위.

컬럼: `s_pref`, `t_star`, `prefer_hat`, `y_prefer`, `prefer_rank`, `n_star5` (+ legacy bar 컬럼).

---

## 4. 레거시 (실험 22~26, Spearman 동결 종료)

이축 dual Go·informative/v≥2/v1 슬라이스 해석은 **참고 이력**.  
새 서비스 주장: **「기준선 위 = 선호 후보」** — bar 1등 주장 없음.

---

## 5. 다음

- §28 실측 판정 후 README §1.2 갱신 (Go 시)
- Track A CF 설계 (병렬)
