"""학습 → 모델 저장 → catalog export → 검증 출력. Docker에서 python train.py로 실행."""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
from lightfm import LightFM

from config import (
    export_recipe_lightfm,
    load_experiment_config,
    load_track_b_tables,
    require_docker_runtime,
    save_model,
    seed_all,
    write_json_report,
)
from evaluation import (
    aggregate_recommend_multi_seed,
    catalog_score_sanity,
    run_cv_evaluation,
    run_full_catalog_eval,
)
from pipeline import (
    aggregate_review_for_export,
    build_export_dataframe,
    build_interactions,
    build_item_features,
    build_lightfm_ids,
    build_prefer_labels,
    catalog_predict,
    prepare_training_frames,
    recipe_n_star5_counts,
)


def main() -> None:
    require_docker_runtime()
    project_root = Path(os.environ.get("PROJECT_ROOT", Path(__file__).resolve().parent))
    cfg = load_experiment_config(project_root)
    seed_all(cfg.seed)

    # 1. 데이터
    review_raw, recipe_raw, alias_df = load_track_b_tables(cfg.data_dir)
    recipe_df, review_df = prepare_training_frames(review_raw, recipe_raw, alias_df)
    dataset, item_ids, warm_item_ids, cold_item_ids, user_ids = build_lightfm_ids(review_df, recipe_df)
    item_features, feature_names = build_item_features(recipe_df, item_ids, dataset, cfg.excluded_recipe_columns)

    y_prefer = build_prefer_labels(review_df)
    n_star5 = recipe_n_star5_counts(review_df)
    review_agg = aggregate_review_for_export(pd.read_csv(cfg.data_files["review"]))

    # 2. 학습
    interactions = build_interactions(review_df, dataset, recipe_prefer_labels=y_prefer)
    model = LightFM(loss="warp", random_state=cfg.seed)
    model.fit(interactions, item_features=item_features, epochs=cfg.epochs, num_threads=cfg.num_threads)

    # 3. 모델 저장
    saved = save_model(cfg, model=model, item_features=item_features, dataset=dataset)

    # 4. Export
    s_pref = catalog_predict(model, dataset, item_ids, item_features, cfg.num_threads)
    export_df = build_export_dataframe(
        recipe_df=recipe_df, review_agg=review_agg, s_pref=s_pref,
        y_prefer=y_prefer, n_star5=n_star5, warm_item_ids=warm_item_ids,
    )
    export_path = cfg.outputs_dir / "recipe_lightfm.csv"
    export_recipe_lightfm(export_df, export_path)

    sanity = catalog_score_sanity(s_pref)
    assert sanity["r0_pass"], f"R0 sanity failed: {sanity}"

    # 5. 검증 — evaluation 지표 출력
    print("=" * 60)
    print("TRAIN COMPLETE — 검증 지표")
    print("=" * 60)
    print(f"export: {export_path} ({len(export_df)} rows)")
    print(f"model:  {cfg.model_dir}")
    print(f"R0 sanity: pass={sanity['r0_pass']}, coverage={sanity['coverage']:.4f}, std={sanity['score_std']:.6f}")
    print()

    # 5a. CV Go (5-seed)
    cv_epochs = int(os.environ.get("EPOCHS", "10"))
    cfg_cv = load_experiment_config(project_root)
    cfg_cv.epochs = cv_epochs

    print(f"--- CV Go (5-seed, ep={cv_epochs}) ---")
    seed_reports = run_cv_evaluation(
        cfg0=cfg_cv, review_df=review_df, dataset=dataset,
        item_ids=item_ids, item_features=item_features,
        y_prefer=y_prefer, cv_epochs=cv_epochs,
    )
    agg = aggregate_recommend_multi_seed([r["fold_mean"] for r in seed_reports])
    agg["r0_pass"] = sanity["r0_pass"]
    agg["go"] = bool(agg["go"] and sanity["r0_pass"])

    print()
    print(f"  mean Recall@20:    model={agg['mean_recall_at_k']:.4f}  pop={agg['mean_recall_at_k_pop']:.4f}")
    print(f"  mean Precision@20: model={agg['mean_precision_at_k']:.4f}  pop={agg['mean_precision_at_k_pop']:.4f}")
    print(f"  Go: {agg['go']}  (wins={agg['n_wins']}/5)")
    print()

    # 5b. Full-catalog 진단
    full_eval = run_full_catalog_eval(
        export_df, y_prefer=y_prefer, warm_item_ids=warm_item_ids,
        review_df=review_df, cold_item_ids=cold_item_ids,
    )
    print("--- Full-catalog 진단 ---")
    for k, v in full_eval["at_k"].items():
        print(f"  K={k:>3}: recall={v['warm_recall_at_k']:.3f}  precision={v['warm_precision_at_k']:.2f}  cold_share={v['cold_share_at_k']:.2f}")
    print()

    # 리포트 저장
    report = {
        "r0_pass": sanity["r0_pass"],
        "go": agg["go"],
        "mean_recall_at_k": agg["mean_recall_at_k"],
        "mean_precision_at_k": agg["mean_precision_at_k"],
        "n_wins": agg["n_wins"],
        "full_catalog_eval": full_eval,
        "model_dir": str(cfg.model_dir),
        "export_csv": str(export_path),
    }
    write_json_report(report, cfg.outputs_dir / "train_report.json")

    if agg["go"]:
        print("GO — 학습+검증 완료")
    else:
        print("NO-GO — 모델은 저장됨, 검증 미통과")


if __name__ == "__main__":
    main()
