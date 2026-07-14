"""Experiment 28: prefer threshold Track B — y*=n_star5≥2, t*=min(train True s)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from lightfm import LightFM
from sklearn.model_selection import StratifiedKFold

PROJECT_ROOT = Path(os.environ.get("PROJECT_ROOT", Path(__file__).resolve().parent))
sys.path.insert(0, str(PROJECT_ROOT))

from config import CATALOG_USER_ID, load_experiment_config, require_docker_runtime, seed_all  # noqa: E402
from data_io import export_recipe_lightfm, load_track_b_tables, write_json_report  # noqa: E402
from evaluation import (  # noqa: E402
    PREFER_AT_K,
    PREFER_N_FOLDS,
    aggregate_prefer_multi_seed,
    binary_threshold_report,
    prefer_threshold_min,
    prefer_threshold_p05,
    popularity_baseline_scores,
    ranking_at_k_binary,
    seed_prefer_go_pass,
)
from preprocess import (  # noqa: E402
    build_interactions,
    build_item_features,
    build_lightfm_ids,
    build_prefer_labels,
    prepare_training_frames,
    recipe_n_star5_counts,
)
from scoring import aggregate_review_for_export  # noqa: E402

SEEDS = (42, 123, 456, 789, 1024)


def _catalog_scores(model, dataset, item_ids, item_features, num_threads: int) -> np.ndarray:
    user_id_map, _, item_id_map, _ = dataset.mapping()
    catalog_user_idx = user_id_map[CATALOG_USER_ID]
    item_internal = np.array([item_id_map[i] for i in item_ids], dtype=np.int32)
    user_internal = np.full(len(item_ids), catalog_user_idx, dtype=np.int32)
    return model.predict(
        user_internal,
        item_internal,
        item_features=item_features,
        num_threads=num_threads,
    ).astype(float)


def _mean_dicts(dicts: list[dict], keys: list[str]) -> dict:
    out = {}
    for k in keys:
        vals = [float(d[k]) for d in dicts if k in d and np.isfinite(d[k])]
        out[k] = float(np.mean(vals)) if vals else float("nan")
    return out


def run_seed_cv(
    cfg,
    *,
    review_df: pd.DataFrame,
    dataset,
    item_ids: list[str],
    item_features,
    y_prefer: pd.Series,
    pop_by_id: pd.Series,
) -> dict:
    warm_ids = np.array(sorted(y_prefer.index.astype(str)), dtype=object)
    y = y_prefer.loc[warm_ids].to_numpy(dtype=int)
    skf = StratifiedKFold(n_splits=PREFER_N_FOLDS, shuffle=True, random_state=cfg.seed)
    fold_rows = []
    id_to_idx = {rid: i for i, rid in enumerate(item_ids)}
    rid_str = review_df["recipe_id"].astype(str)

    for fold_i, (tr_ix, te_ix) in enumerate(skf.split(warm_ids, y)):
        train_ids = set(warm_ids[tr_ix].tolist())
        test_ids = warm_ids[te_ix]
        train_review = review_df[rid_str.isin(train_ids)].copy()
        y_train = build_prefer_labels(train_review)

        interactions, _, sample_weight = build_interactions(
            train_review, dataset, cfg, recipe_prefer_labels=y_train
        )
        model = LightFM(loss="warp", random_state=cfg.seed + fold_i)
        fit_kw = dict(
            item_features=item_features,
            epochs=cfg.epochs,
            num_threads=cfg.num_threads,
        )
        if sample_weight is not None:
            fit_kw["sample_weight"] = sample_weight
        model.fit(interactions, **fit_kw)

        all_scores = _catalog_scores(
            model, dataset, item_ids, item_features, cfg.num_threads
        )
        train_list = list(train_ids)
        y_tr = y_prefer.loc[train_list].to_numpy(dtype=int)
        s_tr = np.array([all_scores[id_to_idx[r]] for r in train_list], dtype=float)
        true_mask = y_tr == 1
        t_star = prefer_threshold_min(s_tr[true_mask])
        t_p05 = prefer_threshold_p05(s_tr[true_mask])

        y_te = y_prefer.loc[test_ids].to_numpy(dtype=int)
        s_te = np.array([all_scores[id_to_idx[rid]] for rid in test_ids], dtype=float)
        pop_te = pop_by_id.reindex(test_ids).fillna(0.0).to_numpy(dtype=float)

        thr_rep = binary_threshold_report(y_te, s_te, threshold=t_star)
        atk = ranking_at_k_binary(y_te, s_te, k=PREFER_AT_K)
        atk_pop = ranking_at_k_binary(y_te, pop_te, k=PREFER_AT_K)
        pop_t = prefer_threshold_min(pop_te[y_te == 1]) if (y_te == 1).any() else 0.0
        pop_rep = binary_threshold_report(y_te, pop_te, threshold=pop_t)

        fold_rows.append(
            {
                "fold": fold_i,
                "t_star": t_star,
                "t_p05": t_p05,
                "roc_auc": thr_rep["roc_auc"],
                "pr_auc": thr_rep["pr_auc"],
                "f1": thr_rep["f1"],
                "precision": thr_rep["precision"],
                "recall": thr_rep["recall"],
                "specificity": thr_rep["specificity"],
                "accuracy": thr_rep["accuracy"],
                "precision_at_k": atk["precision"],
                "recall_at_k": atk["recall"],
                "ndcg_at_k": atk["ndcg"],
                "roc_auc_pop": pop_rep["roc_auc"],
                "precision_at_k_pop": atk_pop["precision"],
                "nnz": int(interactions.nnz),
            }
        )

    keys = [
        "roc_auc", "pr_auc", "f1", "precision", "recall", "specificity", "accuracy",
        "precision_at_k", "recall_at_k", "ndcg_at_k", "roc_auc_pop", "precision_at_k_pop",
        "t_star", "t_p05",
    ]
    mean = _mean_dicts(fold_rows, keys)
    mean["seed"] = cfg.seed
    mean["seed_pass"] = seed_prefer_go_pass(mean)
    return {"seed": cfg.seed, "fold_mean": mean, "folds": fold_rows}


def full_fit_export(
    cfg,
    *,
    recipe_df,
    review_df,
    dataset,
    item_ids,
    warm_item_ids,
    item_features,
    y_prefer: pd.Series,
    review_agg: pd.DataFrame,
    n_star5: pd.Series,
) -> tuple[pd.DataFrame, float]:
    interactions, _, sample_weight = build_interactions(
        review_df, dataset, cfg, recipe_prefer_labels=y_prefer
    )
    model = LightFM(loss="warp", random_state=cfg.seed)
    fit_kw = dict(
        item_features=item_features,
        epochs=cfg.epochs,
        num_threads=cfg.num_threads,
    )
    if sample_weight is not None:
        fit_kw["sample_weight"] = sample_weight
    model.fit(interactions, **fit_kw)
    s_pref = _catalog_scores(model, dataset, item_ids, item_features, cfg.num_threads)

    export_df = recipe_df[["recipe_id", "recipe_name"]].copy()
    export_df["recipe_id"] = export_df["recipe_id"].astype(str)
    export_df = export_df.merge(review_agg, on="recipe_id", how="left")
    export_df["y_hat"] = s_pref
    export_df["s_pref"] = s_pref

    warm_mask = export_df["recipe_id"].isin(warm_item_ids).to_numpy()
    from evaluation import apply_linear_calibration, fit_linear_calibration

    bar = export_df["review_rank_score"].to_numpy(dtype=float)
    slope, intercept = fit_linear_calibration(s_pref, bar, warm_mask)
    export_df["y_hat_linear"] = apply_linear_calibration(s_pref, slope, intercept)

    warm_y = (
        export_df.loc[warm_mask, "recipe_id"].map(y_prefer).fillna(0).astype(int).to_numpy()
    )
    warm_s = export_df.loc[warm_mask, "s_pref"].to_numpy(dtype=float)
    true_s = warm_s[warm_y == 1]
    t_star = prefer_threshold_min(true_s)

    export_df["t_star"] = t_star
    export_df["prefer_hat"] = (export_df["s_pref"] >= t_star).astype(int)
    export_df["y_prefer"] = export_df["recipe_id"].map(y_prefer).fillna(-1).astype(int)
    export_df["n_star5"] = (
        export_df["recipe_id"].map(n_star5).fillna(0).astype(int).to_numpy()
    )

    export_df = (
        export_df.sort_values("s_pref", ascending=False, kind="mergesort")
        .reset_index(drop=True)
    )
    export_df["prefer_rank"] = np.arange(1, len(export_df) + 1)
    return export_df, t_star


def main() -> None:
    os.environ.setdefault("POSITIVE_MODE", "prefer_n_star5_ge2")
    cv_epochs = int(os.environ.get("EPOCHS", "10"))
    full_epochs = int(os.environ.get("FULL_EPOCHS", "30"))
    require_docker_runtime()

    cfg0 = load_experiment_config(PROJECT_ROOT)
    cfg0.positive_mode = "prefer_n_star5_ge2"
    cfg0.epochs = cv_epochs

    review_raw, recipe_raw, alias_df = load_track_b_tables(cfg0.data_dir)
    recipe_df, review_df = prepare_training_frames(review_raw, recipe_raw, alias_df)
    dataset, item_ids, warm_item_ids, cold_item_ids, _ = build_lightfm_ids(
        review_df, recipe_df
    )
    item_features, _ = build_item_features(
        recipe_df, item_ids, dataset, cfg0.excluded_recipe_columns
    )

    y_prefer = build_prefer_labels(review_df)
    n_star5 = recipe_n_star5_counts(review_df)
    pop_by_id = popularity_baseline_scores(recipe_df)
    review_agg, _ = aggregate_review_for_export(
        pd.read_csv(cfg0.data_files["review"]), cfg0.target_mode
    )

    print(
        f"exp28 y*=n_star5>=2: {(y_prefer==1).sum()}/{len(y_prefer)} warm, "
        f"cold={len(cold_item_ids)}, CV ep={cv_epochs}",
        flush=True,
    )

    seed_reports = []
    for seed in SEEDS:
        os.environ["SEED"] = str(seed)
        cfg = load_experiment_config(PROJECT_ROOT)
        cfg.positive_mode = "prefer_n_star5_ge2"
        cfg.epochs = cv_epochs
        seed_all(cfg.seed)
        print(f"=== seed {seed} ===", flush=True)
        rep = run_seed_cv(
            cfg,
            review_df=review_df,
            dataset=dataset,
            item_ids=item_ids,
            item_features=item_features,
            y_prefer=y_prefer,
            pop_by_id=pop_by_id,
        )
        seed_reports.append(rep)
        print(rep["fold_mean"], flush=True)

    agg = aggregate_prefer_multi_seed([r["fold_mean"] for r in seed_reports])
    agg["cv_epochs"] = cv_epochs
    agg["full_epochs"] = full_epochs
    agg["threshold_rule"] = "min(train_true_s)"

    os.environ["SEED"] = "42"
    cfg = load_experiment_config(PROJECT_ROOT)
    cfg.positive_mode = "prefer_n_star5_ge2"
    cfg.epochs = full_epochs
    seed_all(42)
    export_df, t_star = full_fit_export(
        cfg,
        recipe_df=recipe_df,
        review_df=review_df,
        dataset=dataset,
        item_ids=item_ids,
        warm_item_ids=warm_item_ids,
        item_features=item_features,
        y_prefer=y_prefer,
        review_agg=review_agg,
        n_star5=n_star5,
    )

    s_all = export_df["s_pref"].to_numpy(dtype=float)
    agg["p0_pass"] = bool(np.isfinite(s_all).all() and float(np.std(s_all)) > 1e-6)
    agg["go"] = bool(agg["go"] and agg["p0_pass"])
    agg["n_prefer"] = int((y_prefer == 1).sum())
    agg["n_warm"] = int(len(y_prefer))
    agg["n_cold"] = int(len(cold_item_ids))
    agg["t_star_full"] = float(t_star)

    warm = export_df[export_df["y_prefer"] >= 0]
    agg["full_warm_metrics"] = binary_threshold_report(
        warm["y_prefer"].to_numpy(dtype=int),
        warm["s_pref"].to_numpy(dtype=float),
        threshold=t_star,
    )

    out = {
        "experiment": "28_prefer_threshold",
        "aggregate": agg,
        "seeds": seed_reports,
    }
    report_path = cfg0.outputs_dir / "exp28_report.json"
    write_json_report(out, report_path)
    print(json.dumps(agg, ensure_ascii=False, indent=2), flush=True)

    ranked_path = cfg0.outputs_dir / "recipe_prefer_ranked.csv"
    export_recipe_lightfm(export_df, ranked_path)
    print(f"saved {ranked_path} ({len(export_df)} rows)", flush=True)

    if agg["go"]:
        main_path = cfg0.outputs_dir / "recipe_lightfm.csv"
        export_recipe_lightfm(export_df, main_path)
        print(f"GO — replaced {main_path}")
    else:
        print("NO-GO — recipe_lightfm.csv unchanged")


if __name__ == "__main__":
    main()
