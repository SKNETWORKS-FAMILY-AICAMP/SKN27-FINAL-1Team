"""Experiment 29: star-only WARP + R0~R3 recommendation Go charter."""

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

from config import load_experiment_config, require_docker_runtime, seed_all  # noqa: E402
from data_io import export_recipe_lightfm, load_track_b_tables, write_json_report  # noqa: E402
from evaluation import (  # noqa: E402
    PREFER_AT_K,
    PREFER_N_FOLDS,
    REC_METRICS_VERSION,
    REC_NDCG20_GO,
    REC_P20_GO,
    REC_RECALL20_GO,
    aggregate_recommend_multi_seed,
    binary_threshold_report,
    prefer_threshold_min,
    prefer_threshold_p05,
    popularity_baseline_scores,
    ranking_at_k_binary,
    seed_recommend_go_pass,
)
from preprocess import (  # noqa: E402
    build_interactions,
    build_item_features,
    build_lightfm_ids,
    build_prefer_labels,
    is_five_star_mask,
    prepare_training_frames,
    recipe_n_star5_counts,
)
from scoring import aggregate_review_for_export  # noqa: E402

SEEDS = (42, 123, 456, 789, 1024)

ARMS: dict[str, str] = {
    "baseline": "prefer_n_star5_ge2",
    "29a": "prefer_n_star5_ge2_five_star_rows",
    "29b": "five_star_reviews_only",
}


def _parse_arms() -> list[str]:
    raw = os.environ.get("ARMS", "all").strip().lower()
    if raw == "all":
        return list(ARMS.keys())
    selected = [a.strip() for a in raw.split(",") if a.strip()]
    bad = [a for a in selected if a not in ARMS]
    if bad:
        raise ValueError(f"unknown ARMS {bad}; use {list(ARMS)} or all")
    return selected


def _catalog_scores(model, dataset, item_ids, item_features, num_threads: int) -> np.ndarray:
    from config import CATALOG_USER_ID

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

        interactions, review_with_iv, sample_weight = build_interactions(
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

        if cfg.positive_mode == "prefer_n_star5_ge2":
            fit_rows = review_with_iv[review_with_iv["prefer_label"] == 1]
            non5_frac = float((~is_five_star_mask(fit_rows)).mean()) if len(fit_rows) else 0.0
        else:
            non5_frac = 0.0

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
                "non_five_star_frac_in_matrix": non5_frac,
            }
        )

    keys = [
        "roc_auc", "pr_auc", "f1", "precision", "recall", "specificity", "accuracy",
        "precision_at_k", "recall_at_k", "ndcg_at_k", "roc_auc_pop", "precision_at_k_pop",
        "t_star", "t_p05", "nnz", "non_five_star_frac_in_matrix",
    ]
    mean = _mean_dicts(fold_rows, keys)
    mean["seed"] = cfg.seed
    mean["seed_pass"] = seed_recommend_go_pass(mean)
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


def run_arm(
    arm_key: str,
    positive_mode: str,
    *,
    cfg0,
    recipe_df,
    review_df,
    dataset,
    item_ids,
    warm_item_ids,
    cold_item_ids,
    item_features,
    y_prefer,
    n_star5,
    pop_by_id,
    review_agg,
    cv_epochs: int,
    full_epochs: int,
) -> dict:
    print(
        f"\n=== arm {arm_key} ({positive_mode}) ===",
        flush=True,
    )
    seed_reports = []
    for seed in SEEDS:
        os.environ["SEED"] = str(seed)
        cfg = load_experiment_config(PROJECT_ROOT)
        cfg.positive_mode = positive_mode
        cfg.target_mode = "star_only"
        cfg.epochs = cv_epochs
        seed_all(cfg.seed)
        print(f"--- seed {seed} ---", flush=True)
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

    agg = aggregate_recommend_multi_seed([r["fold_mean"] for r in seed_reports])
    agg["metrics_version"] = REC_METRICS_VERSION
    agg["charter"] = "R0-R3"
    agg["arm"] = arm_key
    agg["positive_mode"] = positive_mode
    agg["cv_epochs"] = cv_epochs
    agg["full_epochs"] = full_epochs
    agg["threshold_rule"] = "min(train_true_s)"
    agg["target_mode_export"] = "star_only"
    agg["go_thresholds"] = {
        "p_at_20": REC_P20_GO,
        "ndcg_at_20": REC_NDCG20_GO,
        "recall_at_20": REC_RECALL20_GO,
    }

    os.environ["SEED"] = "42"
    cfg_full = load_experiment_config(PROJECT_ROOT)
    cfg_full.positive_mode = positive_mode
    cfg_full.target_mode = "star_only"
    cfg_full.epochs = full_epochs
    seed_all(42)
    export_df, t_star = full_fit_export(
        cfg_full,
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
    agg["r0_pass"] = bool(np.isfinite(s_all).all() and float(np.std(s_all)) > 1e-6)
    agg["go"] = bool(agg["go"] and agg["r0_pass"])
    agg["n_prefer"] = int((y_prefer == 1).sum())
    agg["n_warm"] = int(len(y_prefer))
    agg["n_cold"] = int(len(cold_item_ids))
    agg["t_star_full"] = float(t_star)
    agg["mean_matrix_nnz"] = float(
        np.mean([r["fold_mean"]["nnz"] for r in seed_reports])
    )

    warm = export_df[export_df["y_prefer"] >= 0]
    agg["full_warm_metrics_diagnostic"] = binary_threshold_report(
        warm["y_prefer"].to_numpy(dtype=int),
        warm["s_pref"].to_numpy(dtype=float),
        threshold=t_star,
    )

    ranked_path = cfg0.outputs_dir / f"recipe_prefer_ranked_{arm_key}.csv"
    export_recipe_lightfm(export_df, ranked_path)
    print(f"saved {ranked_path} ({len(export_df)} rows)", flush=True)

    return {
        "arm": arm_key,
        "positive_mode": positive_mode,
        "aggregate": agg,
        "seeds": seed_reports,
        "export_path": str(ranked_path),
    }


def main() -> None:
    os.environ.setdefault("TARGET_MODE", "star_only")
    cv_epochs = int(os.environ.get("EPOCHS", "10"))
    full_epochs = int(os.environ.get("FULL_EPOCHS", "30"))
    require_docker_runtime()
    arms_to_run = _parse_arms()

    cfg0 = load_experiment_config(PROJECT_ROOT)
    cfg0.target_mode = "star_only"
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
        pd.read_csv(cfg0.data_files["review"]), "star_only"
    )

    print(
        f"exp29 y*=n_star5>=2: {(y_prefer==1).sum()}/{len(y_prefer)} warm, "
        f"cold={len(cold_item_ids)}, arms={arms_to_run}, CV ep={cv_epochs}",
        flush=True,
    )

    arm_results = []
    go_arm = None
    for arm_key in arms_to_run:
        result = run_arm(
            arm_key,
            ARMS[arm_key],
            cfg0=cfg0,
            recipe_df=recipe_df,
            review_df=review_df,
            dataset=dataset,
            item_ids=item_ids,
            warm_item_ids=warm_item_ids,
            cold_item_ids=cold_item_ids,
            item_features=item_features,
            y_prefer=y_prefer,
            n_star5=n_star5,
            pop_by_id=pop_by_id,
            review_agg=review_agg,
            cv_epochs=cv_epochs,
            full_epochs=full_epochs,
        )
        arm_results.append(result)
        if result["aggregate"]["go"] and go_arm is None:
            go_arm = arm_key

    out = {
        "experiment": "29_star_only_prefer",
        "charter": "R0-R3",
        "arms": arm_results,
        "go_arm": go_arm,
    }
    report_path = cfg0.outputs_dir / "exp29_report.json"
    write_json_report(out, report_path)

    summary = {
        a["arm"]: {
            "go": a["aggregate"]["go"],
            "n_wins": a["aggregate"]["n_wins"],
            "mean_p20": a["aggregate"]["mean_precision_at_k"],
            "mean_ndcg20": a["aggregate"]["mean_ndcg_at_k"],
            "mean_recall20": a["aggregate"]["mean_recall_at_k"],
            "mean_nnz": a["aggregate"]["mean_matrix_nnz"],
        }
        for a in arm_results
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    print(f"report: {report_path}", flush=True)

    if go_arm:
        src = cfg0.outputs_dir / f"recipe_prefer_ranked_{go_arm}.csv"
        dst = cfg0.outputs_dir / "recipe_lightfm.csv"
        export_df = pd.read_csv(src)
        export_recipe_lightfm(export_df, dst)
        print(f"GO arm={go_arm} — replaced {dst}")
    else:
        print("NO-GO all arms — recipe_lightfm.csv unchanged")


if __name__ == "__main__":
    main()
