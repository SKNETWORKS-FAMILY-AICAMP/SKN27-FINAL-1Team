"""Prefer recommendation CV metrics (R0~R2) and Docker entrypoint."""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold

METRICS_VERSION = "prefer-recall-vs-star-pop"
REC_SEED_WINS_REQUIRED = 4
CV_N_FOLDS = 5
AT_K = 20
CV_SEEDS = (42, 123, 456, 789, 1024)
FULL_CATALOG_K = (20, 50, 100)


def ndcg_at_k(scores: np.ndarray, relevance: np.ndarray, k: int = AT_K) -> float:
    scores = np.asarray(scores, dtype=np.float64).ravel()
    relevance = np.asarray(relevance, dtype=np.float64).ravel()
    if scores.size == 0:
        return 0.0
    k = min(k, scores.size)
    order = np.argsort(-scores, kind="stable")[:k]
    gains = np.maximum(relevance[order], 0.0)
    discounts = np.log2(np.arange(2, k + 2, dtype=np.float64))
    dcg = float(np.sum(gains / discounts))
    ideal = np.argsort(-relevance, kind="stable")[:k]
    idcg = float(np.sum(np.maximum(relevance[ideal], 0.0) / discounts))
    return dcg / idcg if idcg > 0.0 else 0.0


def ranking_at_k_binary(y_true: np.ndarray, scores: np.ndarray, *, k: int = AT_K) -> dict[str, float]:
    y = np.asarray(y_true, dtype=np.float64).ravel()
    s = np.asarray(scores, dtype=np.float64).ravel()
    k = min(int(k), s.size)
    order = np.argsort(-s, kind="stable")[:k]
    hits = float(y[order].sum())
    return {
        "precision_at_k": hits / k if k else 0.0,
        "recall_at_k": hits / float(y.sum()) if y.sum() > 0 else 0.0,
        "ndcg_at_k": ndcg_at_k(s, y, k=k),
    }


def catalog_score_sanity(scores: np.ndarray) -> dict[str, float | bool]:
    s = np.asarray(scores, dtype=np.float64).ravel()
    finite = np.isfinite(s)
    coverage = float(finite.sum() / s.size) if s.size else 0.0
    score_std = float(np.std(s[finite])) if finite.any() else 0.0
    return {"coverage": coverage, "score_std": score_std, "r0_pass": coverage == 1.0 and score_std > 1e-6}


def seed_recommend_go_pass(seed_mean: dict) -> bool:
    return float(seed_mean.get("recall_at_k", 0.0)) > float(seed_mean.get("recall_at_k_pop", 0.0))


def aggregate_recommend_multi_seed(seed_means: list[dict]) -> dict:
    n = len(seed_means)
    wins = sum(1 for m in seed_means if seed_recommend_go_pass(m))

    def _mean(k: str) -> float:
        vals = [float(m[k]) for m in seed_means if k in m and np.isfinite(m[k])]
        return float(np.mean(vals)) if vals else float("nan")

    return {
        "n_seeds": n, "n_wins": wins, "pop_wins": wins,
        "go": wins >= REC_SEED_WINS_REQUIRED and n >= REC_SEED_WINS_REQUIRED,
        "mean_recall_at_k": _mean("recall_at_k"),
        "mean_recall_at_k_pop": _mean("recall_at_k_pop"),
        "mean_precision_at_k": _mean("precision_at_k"),
        "mean_precision_at_k_pop": _mean("precision_at_k_pop"),
        "mean_ndcg_at_k": _mean("ndcg_at_k"),
        "mean_ndcg_at_k_pop": _mean("ndcg_at_k_pop"),
        "mean_matrix_nnz": _mean("matrix_nnz"),
        "metrics_version": METRICS_VERSION,
    }


def _mean_dicts(dicts: list[dict], keys: list[str]) -> dict:
    out = {}
    for k in keys:
        vals = [float(d[k]) for d in dicts if k in d and np.isfinite(d[k])]
        out[k] = float(np.mean(vals)) if vals else float("nan")
    return out


def run_prefer_cv(cfg, *, review_df, dataset, item_ids, item_features, y_prefer) -> dict:
    from lightfm import LightFM

    from pipeline import build_interactions, build_prefer_labels, catalog_predict, star_popularity_scores

    warm_ids = np.array(sorted(y_prefer.index.astype(str)), dtype=object)
    y = y_prefer.loc[warm_ids].to_numpy(dtype=int)
    skf = StratifiedKFold(n_splits=CV_N_FOLDS, shuffle=True, random_state=cfg.seed)
    fold_rows = []
    id_to_idx = {rid: i for i, rid in enumerate(item_ids)}
    rid_str = review_df["recipe_id"].astype(str)

    for fold_i, (tr_ix, te_ix) in enumerate(skf.split(warm_ids, y)):
        train_ids = set(warm_ids[tr_ix].tolist())
        test_ids = warm_ids[te_ix]
        train_review = review_df[rid_str.isin(train_ids)].copy()
        y_train = build_prefer_labels(train_review)

        interactions = build_interactions(train_review, dataset, recipe_prefer_labels=y_train)
        model = LightFM(loss="warp", random_state=cfg.seed + fold_i)
        model.fit(interactions, item_features=item_features, epochs=cfg.epochs, num_threads=cfg.num_threads)
        all_scores = catalog_predict(model, dataset, item_ids, item_features, cfg.num_threads)
        y_te = y_prefer.loc[test_ids].to_numpy(dtype=int)
        s_te = np.array([all_scores[id_to_idx[rid]] for rid in test_ids], dtype=float)

        pop_scores, pop_C = star_popularity_scores(train_review)
        pop_te = pop_scores.reindex(test_ids).fillna(pop_C).to_numpy(dtype=float)

        atk = ranking_at_k_binary(y_te, s_te, k=AT_K)
        atk_pop = ranking_at_k_binary(y_te, pop_te, k=AT_K)
        fold_rows.append({
            "fold": fold_i,
            "recall_at_k": atk["recall_at_k"], "recall_at_k_pop": atk_pop["recall_at_k"],
            "precision_at_k": atk["precision_at_k"], "precision_at_k_pop": atk_pop["precision_at_k"],
            "ndcg_at_k": atk["ndcg_at_k"], "ndcg_at_k_pop": atk_pop["ndcg_at_k"],
            "matrix_nnz": float(interactions.nnz), "pop_C_train": float(pop_C),
        })

    keys = ["recall_at_k", "recall_at_k_pop", "precision_at_k", "precision_at_k_pop", "ndcg_at_k", "ndcg_at_k_pop", "matrix_nnz"]
    mean = _mean_dicts(fold_rows, keys)
    mean["seed"] = cfg.seed
    mean["seed_pass"] = seed_recommend_go_pass(mean)
    return {"seed": cfg.seed, "fold_mean": mean, "folds": fold_rows}


def run_cv_evaluation(*, cfg0, review_df, dataset, item_ids, item_features, y_prefer, cv_epochs) -> list[dict]:
    from config import load_experiment_config, seed_all

    project_root = cfg0.project_root
    seed_reports = []
    for seed in CV_SEEDS:
        os.environ["SEED"] = str(seed)
        cfg = load_experiment_config(project_root)
        cfg.epochs = cv_epochs
        seed_all(cfg.seed)
        print(f"--- seed {seed} ---", flush=True)
        rep = run_prefer_cv(cfg, review_df=review_df, dataset=dataset, item_ids=item_ids, item_features=item_features, y_prefer=y_prefer)
        seed_reports.append(rep)
        print(rep["fold_mean"], flush=True)
    return seed_reports


def run_full_catalog_eval(export_df, *, y_prefer, warm_item_ids, review_df, cold_item_ids) -> dict:
    from pipeline import star_popularity_scores

    y = (export_df["y_prefer"] == 1).astype(int).to_numpy()
    s_model = export_df["s_pref"].to_numpy(dtype=float)
    is_warm = export_df["is_warm"].to_numpy(dtype=int)

    pop_scores, pop_C = star_popularity_scores(review_df)
    rid = export_df["recipe_id"].astype(str)
    s_pop = pop_scores.reindex(rid).fillna(pop_C).to_numpy(dtype=float)

    at_k: dict[str, dict] = {}
    for k in FULL_CATALOG_K:
        atk_m = ranking_at_k_binary(y, s_model, k=k)
        atk_p = ranking_at_k_binary(y, s_pop, k=k)
        kk = min(int(k), s_model.size)
        order = np.argsort(-s_model, kind="stable")[:kk]
        cold_share = float((is_warm[order] == 0).sum()) / kk if kk else 0.0
        at_k[str(k)] = {
            "warm_recall_at_k": atk_m["recall_at_k"], "warm_recall_at_k_pop": atk_p["recall_at_k"],
            "warm_precision_at_k": atk_m["precision_at_k"], "warm_precision_at_k_pop": atk_p["precision_at_k"],
            "cold_share_at_k": cold_share,
            "recall_gap_vs_pop": atk_m["recall_at_k"] - atk_p["recall_at_k"],
            "precision_gap_vs_pop": atk_m["precision_at_k"] - atk_p["precision_at_k"],
        }

    return {
        "n_total": int(len(export_df)), "n_warm": int(len(warm_item_ids)),
        "n_cold": int(len(cold_item_ids)), "n_prefer": int((y_prefer == 1).sum()),
        "pop_formula": "Bayesian WR on n_star5/review_n; m=3; full review", "at_k": at_k,
    }


def main() -> None:
    from lightfm import LightFM

    from config import load_experiment_config, require_docker_runtime, seed_all, export_recipe_lightfm, load_track_b_tables, write_json_report
    from pipeline import (
        aggregate_review_for_export, build_export_dataframe, build_interactions,
        build_item_features, build_lightfm_ids, build_prefer_labels,
        catalog_predict, prepare_training_frames, recipe_n_star5_counts,
    )

    project_root = Path(os.environ.get("PROJECT_ROOT", Path(__file__).resolve().parent))
    cv_epochs = int(os.environ.get("EPOCHS", "10"))
    full_epochs = int(os.environ.get("FULL_EPOCHS", "30"))
    require_docker_runtime()

    cfg0 = load_experiment_config(project_root)
    cfg0.epochs = cv_epochs

    review_raw, recipe_raw, alias_df = load_track_b_tables(cfg0.data_dir)
    recipe_df, review_df = prepare_training_frames(review_raw, recipe_raw, alias_df)
    dataset, item_ids, warm_item_ids, cold_item_ids, _ = build_lightfm_ids(review_df, recipe_df)
    item_features, _ = build_item_features(recipe_df, item_ids, dataset, cfg0.excluded_recipe_columns)

    y_prefer = build_prefer_labels(review_df)
    n_star5 = recipe_n_star5_counts(review_df)
    review_agg = aggregate_review_for_export(pd.read_csv(cfg0.data_files["review"]))

    print(f"y*=n_star5>=2: {(y_prefer==1).sum()}/{len(y_prefer)} warm, mode=prefer_n_star5_ge2, CV ep={cv_epochs}", flush=True)

    seed_reports = run_cv_evaluation(
        cfg0=cfg0, review_df=review_df, dataset=dataset,
        item_ids=item_ids, item_features=item_features, y_prefer=y_prefer, cv_epochs=cv_epochs,
    )
    agg = aggregate_recommend_multi_seed([r["fold_mean"] for r in seed_reports])
    agg["charter"] = "R0-R2"
    agg["positive_mode"] = "prefer_n_star5_ge2"
    agg["cv_epochs"] = cv_epochs
    agg["full_epochs"] = full_epochs
    agg["pop_formula"] = "Bayesian WR on n_star5/review_n; m=3; train-fold only"
    agg["go_rule"] = "Recall@20(model) > Recall@20(star_pop) per seed, >=4/5"

    # Full-fit for export (inlined full_fit_export)
    os.environ["SEED"] = "42"
    cfg_full = load_experiment_config(project_root)
    cfg_full.epochs = full_epochs
    seed_all(42)

    interactions = build_interactions(review_df, dataset, recipe_prefer_labels=y_prefer)
    model = LightFM(loss="warp", random_state=cfg_full.seed)
    model.fit(interactions, item_features=item_features, epochs=cfg_full.epochs, num_threads=cfg_full.num_threads)
    s_pref = catalog_predict(model, dataset, item_ids, item_features, cfg_full.num_threads)
    export_df = build_export_dataframe(
        recipe_df=recipe_df, review_agg=review_agg, s_pref=s_pref,
        y_prefer=y_prefer, n_star5=n_star5, warm_item_ids=warm_item_ids,
    )

    sanity = catalog_score_sanity(export_df["s_pref"].to_numpy(dtype=float))
    agg["r0_pass"] = bool(sanity["r0_pass"])
    agg["go"] = bool(agg["go"] and agg["r0_pass"])
    agg["n_prefer"] = int((y_prefer == 1).sum())
    agg["n_warm"] = int(len(y_prefer))
    agg["n_cold"] = int(len(cold_item_ids))

    full_catalog_eval = run_full_catalog_eval(
        export_df, y_prefer=y_prefer, warm_item_ids=warm_item_ids,
        review_df=review_df, cold_item_ids=cold_item_ids,
    )
    print("full_catalog_eval:", json.dumps(full_catalog_eval, ensure_ascii=False), flush=True)

    ranked_path = cfg0.outputs_dir / "recipe_prefer_ranked.csv"
    export_recipe_lightfm(export_df, ranked_path)
    report_path = cfg0.outputs_dir / "prefer_eval_report.json"
    out = {
        "charter": "R0-R2", "positive_mode": "prefer_n_star5_ge2",
        "aggregate": agg, "full_catalog_eval": full_catalog_eval,
        "seeds": seed_reports, "export_path": str(ranked_path),
    }
    write_json_report(out, report_path)

    print(json.dumps(agg, ensure_ascii=False, indent=2), flush=True)
    print(f"report: {report_path}", flush=True)

    if agg["go"]:
        main_path = cfg0.outputs_dir / "recipe_lightfm.csv"
        export_recipe_lightfm(export_df, main_path)
        print(f"GO — replaced {main_path}")
    else:
        print("NO-GO — recipe_lightfm.csv unchanged")


if __name__ == "__main__":
    y = np.array([1, 1, 0, 0, 0], dtype=int)
    s_model = np.array([0.9, 0.8, 0.1, 0.2, 0.0])
    s_pop = np.array([0.5, 0.4, 0.7, 0.6, 0.3])
    atk_m = ranking_at_k_binary(y, s_model, k=3)
    atk_p = ranking_at_k_binary(y, s_pop, k=3)
    assert atk_m["recall_at_k"] > atk_p["recall_at_k"]
    assert catalog_score_sanity(s_model)["r0_pass"]
    print("evaluation self-check ok", atk_m["recall_at_k"], atk_p["recall_at_k"], flush=True)
    main()
