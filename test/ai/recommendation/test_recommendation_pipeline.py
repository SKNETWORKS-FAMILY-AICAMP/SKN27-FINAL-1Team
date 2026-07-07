from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ai.recommendation import data_loader, evaluator, feature_screening, imputer, model
from ai.recommendation.config import CATEGORICAL_FEATURES, TARGET_COL

# 테스트 데이터 생성
def _rows(targets: list[float | None]) -> pd.DataFrame:
    categories = ["한식", "양식", "중식", "일식"]
    rows = []
    for i, target in enumerate(targets):
        row = {
            "RCP_SNO": i + 1,
            "CKG_NM": f"recipe-{i}",
            "CKG_INBUN_NM": "2인분",
            "CKG_TIME_NM": "30분",
            "ingredients_normalized": repr([[f"ingredient-{i % 3}", "1", "개"]]),
            "others_count": 0,
            "others_items": "[]",
            "basic_count": 0,
            "basic_items": "[]",
            "INQ_CNT_LOG_CENTERED": float(i) * 0.1,
            "SRAP_CNT_LOG_CENTERED": float(i) * 0.05,
            TARGET_COL: target,
        }
        row.update({column: categories[i % len(categories)] for column in CATEGORICAL_FEATURES})
        rows.append(row)
    return pd.DataFrame(rows)

# 저장된 파이프라인이 원본 데이터와 동일하게 예측하는지 테스트
def test_saved_pipeline_predicts_raw_rows_identically(tmp_path) -> None:
    train = _rows([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    pipeline = model.fit_pipeline(model.build_pipeline(), train, train[TARGET_COL])
    before = model.predict(pipeline, train)

    path = tmp_path / "pipeline.joblib"
    model.save_pipeline(pipeline, path)
    loaded = __import__("joblib").load(path)

    np.testing.assert_allclose(model.predict(loaded, train), before)
    assert loaded.training_row_count_ == len(train)
    assert "ingredient-0" in loaded.named_steps["feature_builder"].commonness_lookup_._counts

# 예측값이 클리핑되고 평가에 사용되는지 테스트
def test_predictions_are_clipped_and_evaluation_uses_them() -> None:
    train = _rows([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    pipeline = model.fit_pipeline(model.build_pipeline(), train, train[TARGET_COL])
    raw = np.asarray(model.predict(pipeline, train, clip=False))
    clipped = np.asarray(model.predict(pipeline, train))

    assert clipped.min() >= pipeline.clip_low_
    assert clipped.max() <= pipeline.clip_high_
    report = evaluator.evaluate(
        train[TARGET_COL],
        clipped,
        train_row_count=len(train),
        test_row_count=len(train),
        model_type="test",
    )
    expected_rmse = float(np.sqrt(np.mean((train[TARGET_COL].to_numpy() - clipped) ** 2)))
    assert report["RMSE"] == pytest.approx(expected_rmse)
    assert raw.shape == clipped.shape

# 예측값이 라벨링되지 않은 데이터만 예측하고 순서를 유지하는지 테스트
def test_scored_output_predicts_only_unlabeled_and_preserves_order(monkeypatch) -> None:
    full = _rows([1.0, None, 3.0, None])
    calls: list[list[int]] = []

    def fake_predict(_pipeline, rows, **_kwargs):
        calls.append(rows["RCP_SNO"].tolist())
        return np.array([2.5, 3.5])

    monkeypatch.setattr(imputer, "predict", fake_predict)
    scored = imputer.build_scored_output(
        full, object(), labeled_mask=full[TARGET_COL].notna()
    )

    assert calls == [[2, 4]]
    assert scored["RCP_SNO"].tolist() == [1, 2, 3, 4]
    assert scored["recommend_score_source"].tolist() == ["rule", "ml_imputed", "rule", "ml_imputed"]
    assert scored.loc[[0, 2], "ml_predicted_recommend_score"].isna().all()
    pop = imputer.popularity_base_score(full)
    quality = np.where(
        full[TARGET_COL].notna().to_numpy(),
        full[TARGET_COL].to_numpy(dtype=float),
        scored["ml_predicted_recommend_score"].to_numpy(dtype=float),
    )
    np.testing.assert_allclose(scored["final_recommend_score"], quality + pop)


def test_popularity_base_score_sums_centered_columns() -> None:
    df = pd.DataFrame(
        {
            "INQ_CNT_LOG_CENTERED": [1.0, np.nan],
            "SRAP_CNT_LOG_CENTERED": [0.5, 2.0],
        }
    )
    np.testing.assert_allclose(imputer.popularity_base_score(df), [1.5, 2.0])

# 별칭 파일이 없으면 기본값으로 돌아가지만 잘못된 파일은 예외를 발생시키는지 테스트
def test_alias_missing_falls_back_but_invalid_file_fails(tmp_path, monkeypatch) -> None:
    recipe_path = tmp_path / "recipe.csv"
    alias_path = tmp_path / "alias.csv"
    _rows([1.0, None]).to_csv(recipe_path, index=False)
    monkeypatch.setattr(data_loader, "RECIPE_FIX_CSV", recipe_path)
    monkeypatch.setattr(data_loader, "INGREDIENT_ALIAS_CSV", alias_path)

    fallback = data_loader.load_and_merge()
    assert fallback["ingredients_normalized"].eq("[]").all()

    alias_path.write_text("wrong,column\n1,value\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing required columns"):
        data_loader.load_and_merge()

    alias_path.write_text("", encoding="utf-8")
    with pytest.raises(pd.errors.EmptyDataError):
        data_loader.load_and_merge()

# 중복된 레시피 ID가 있으면 예외를 발생시키는지 테스트
def test_duplicate_recipe_ids_fail(tmp_path, monkeypatch) -> None:
    recipe_path = tmp_path / "recipe.csv"
    alias_path = tmp_path / "missing.csv"
    duplicated = _rows([1.0, 2.0])
    duplicated["RCP_SNO"] = [1, 1]
    duplicated.to_csv(recipe_path, index=False)
    monkeypatch.setattr(data_loader, "RECIPE_FIX_CSV", recipe_path)
    monkeypatch.setattr(data_loader, "INGREDIENT_ALIAS_CSV", alias_path)

    with pytest.raises(ValueError, match="duplicate RCP_SNO"):
        data_loader.load_and_merge()


def test_build_pipeline_exclude_drops_features() -> None:
    from ai.recommendation.config import feature_columns

    exclude = frozenset({"unique_ingredient_count", "alias_match_ratio"})
    train = _rows([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    pipeline = model.build_pipeline(exclude=exclude)
    preprocessor = pipeline.named_steps["preprocessor"]
    used: set[str] = set()
    for _, _, cols in preprocessor.transformers:
        used.update(cols)
    expected = set(feature_columns(exclude))
    assert used == expected
    assert "unique_ingredient_count" not in used
    assert "alias_match_ratio" not in used
    fitted = model.fit_pipeline(pipeline, train, train[TARGET_COL])
    pred = model.predict(fitted, train.iloc[:2])
    assert len(pred) == 2


def test_high_correlation_pairs_detects_inq_srap_correlation() -> None:
    df = pd.DataFrame(
        {
            "ingredients_normalized": ['[["a","1","t"],["b","1","t"],["c","1","t"],["d","1","t"]]'] * 4,
            "others_count": [0, 1, 2, 3],
            "others_items": ["[]"] * 4,
            "CKG_INBUN_NM": ["2인분"] * 4,
            "CKG_TIME_NM": ["30분"] * 4,
            "CKG_KND_ACTO_NM": ["한식"] * 4,
            "CKG_MTH_ACTO_NM": ["볶기"] * 4,
            "CKG_MTRL_ACTO_NM": ["채소"] * 4,
            "INQ_CNT_LOG_CENTERED": [0.1, 0.2, 0.3, 0.4],
            "SRAP_CNT_LOG_CENTERED": [0.0, 0.1, 0.2, 0.3],
        }
    )
    pairs = feature_screening.high_correlation_pairs(df, df.iloc[:2], threshold=0.7)
    match = next(
        (p for p in pairs if {p["a"], p["b"]} == {"INQ_CNT_LOG_CENTERED", "SRAP_CNT_LOG_CENTERED"}),
        None,
    )
    assert match is not None
    assert match["pearson"] > 0.7
