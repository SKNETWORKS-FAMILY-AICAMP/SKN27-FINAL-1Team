"""Experiment 15: bar-only smoke (0~2 scale, no retrain)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from catalog_eval import spearman_rho
from score_02 import add_row_02_columns, sentiment_02, star_02_from_count

ROOT = Path(__file__).resolve().parent
REVIEW_CSV = ROOT / "review_by_llm.csv"
EXPORT_CSV = ROOT / "recipe_lightfm.csv"
FIGURES_DIR = ROOT / "figures"
RUNS_DIR = ROOT / "runs"

BAR_IDS = ("B0_legacy", "B1_sum_02", "B2_prod_avg", "B3_prod_row")
SUBSETS = ("all", "ceiling", "star_varies", "low_tail")


def build_recipe_bars(review_df: pd.DataFrame) -> pd.DataFrame:
    review = add_row_02_columns(review_df.copy())
    review["recipe_id"] = review["recipe_id"].astype(str)
    review["sentiment_row"] = (
        pd.to_numeric(review["positive"], errors="coerce")
        - pd.to_numeric(review["negative"], errors="coerce")
    )
    if "star_norm" in review.columns:
        review["star_norm_row"] = pd.to_numeric(review["star_norm"], errors="coerce")
    else:
        review["star_norm_row"] = star_02_from_count(review["star_count"]) - 1.0

    grouped = review.groupby("recipe_id", as_index=False).agg(
        star_norm_avg=("star_norm_row", "mean"),
        sentiment_avg=("sentiment_row", "mean"),
        star_02_avg=("star_02", "mean"),
        sentiment_02_avg=("sentiment_02", "mean"),
        B3_prod_row=("row_product_02", "mean"),
    )
    grouped["B0_legacy"] = grouped["star_norm_avg"] + grouped["sentiment_avg"]
    grouped["B1_sum_02"] = grouped["star_02_avg"] + grouped["sentiment_02_avg"]
    grouped["B2_prod_avg"] = grouped["star_02_avg"] * grouped["sentiment_02_avg"]
    return grouped


def _subset_masks(
    warm: pd.DataFrame, legacy_rank: np.ndarray
) -> dict[str, np.ndarray]:
    star = warm["star_norm_avg"].to_numpy(dtype=float)
    legacy = np.asarray(legacy_rank, dtype=np.float64).ravel()
    base = np.ones(len(warm), dtype=bool)
    return {
        "all": base,
        "ceiling": star >= 0.99,
        "star_varies": star < 1.0,
        "low_tail": legacy < 1.5,
    }


def _pair_correlations(y_hat: np.ndarray, y_bar: np.ndarray) -> dict:
    y_hat = np.asarray(y_hat, dtype=np.float64).ravel()
    y_bar = np.asarray(y_bar, dtype=np.float64).ravel()
    n = int(y_hat.size)
    if n < 2 or np.std(y_hat) < 1e-12 or np.std(y_bar) < 1e-12:
        return {"n": n, "spearman": "n/a", "pearson": "n/a"}
    from scipy.stats import pearsonr

    return {
        "n": n,
        "spearman": float(spearman_rho(y_hat, y_bar)),
        "pearson": float(pearsonr(y_bar, y_hat)[0]),
    }


def decomposed_bar_metrics(
    y_hat: np.ndarray,
    bar_values: np.ndarray,
    star_norm_avg: np.ndarray,
    legacy_rank: np.ndarray,
) -> list[dict]:
    masks = _subset_masks(
        pd.DataFrame({"star_norm_avg": star_norm_avg}), legacy_rank
    )
    rows: list[dict] = []
    for subset, smask in masks.items():
        row = {
            "subset": subset,
            "bar": "score",
            **_pair_correlations(y_hat[smask], bar_values[smask]),
        }
        rows.append(row)
    return rows


def ceiling_stats(bar_values: np.ndarray, star_norm_avg: np.ndarray) -> dict:
    ceiling = np.asarray(star_norm_avg, dtype=float) >= 0.99
    vals = np.asarray(bar_values, dtype=float)[ceiling]
    vals = vals[np.isfinite(vals)]
    if vals.size == 0:
        return {"n": 0, "std": "n/a", "range": "n/a", "min": "n/a", "max": "n/a"}
    return {
        "n": int(vals.size),
        "std": float(np.std(vals)),
        "range": float(vals.max() - vals.min()),
        "min": float(vals.min()),
        "max": float(vals.max()),
    }


def evaluate_exp15(
    export_csv: Path = EXPORT_CSV,
    review_csv: Path = REVIEW_CSV,
) -> dict:
    export = pd.read_csv(export_csv)
    export["recipe_id"] = export["recipe_id"].astype(str)
    bars = build_recipe_bars(pd.read_csv(review_csv))
    df = export.merge(bars, on="recipe_id", how="left", suffixes=("", "_bar"))
    if "star_norm_avg_bar" in df.columns:
        df["star_norm_avg"] = df["star_norm_avg"].fillna(df["star_norm_avg_bar"])
    if "sentiment_avg_bar" in df.columns:
        df["sentiment_avg"] = df["sentiment_avg"].fillna(df["sentiment_avg_bar"])

    warm = df.dropna(subset=["review_rank_score", "y_hat"]).copy()
    y_hat = warm["y_hat"].to_numpy(dtype=float)
    star_norm = warm["star_norm_avg"].to_numpy(dtype=float)
    legacy = warm["B0_legacy"].to_numpy(dtype=float)

    metrics_rows: list[dict] = []
    ceiling_rows: list[dict] = []
    bar_spearman_all: dict[str, float | str] = {}
    bar_spearman_ceiling: dict[str, float | str] = {}

    for bar_id in BAR_IDS:
        bar_vals = warm[bar_id].to_numpy(dtype=float)
        dec = decomposed_bar_metrics(y_hat, bar_vals, star_norm, legacy)
        for row in dec:
            metrics_rows.append({"bar_id": bar_id, **row})
        if row := next(r for r in dec if r["subset"] == "all"):
            bar_spearman_all[bar_id] = row["spearman"]
        if row := next(r for r in dec if r["subset"] == "ceiling"):
            bar_spearman_ceiling[bar_id] = row["spearman"]
        ceiling_rows.append({"bar_id": bar_id, **ceiling_stats(bar_vals, star_norm)})

    b0_ceiling_std = next(r["std"] for r in ceiling_rows if r["bar_id"] == "B0_legacy")
    b0_ceiling_rho = bar_spearman_ceiling["B0_legacy"]
    exp16_recommend = False
    for bar_id in ("B2_prod_avg", "B3_prod_row"):
        std = next(r["std"] for r in ceiling_rows if r["bar_id"] == bar_id)
        rho = bar_spearman_ceiling[bar_id]
        if (
            isinstance(b0_ceiling_std, float)
            and isinstance(std, float)
            and std > b0_ceiling_std
            and isinstance(b0_ceiling_rho, (int, float))
            and isinstance(rho, (int, float))
            and rho >= float(b0_ceiling_rho) + 0.05
        ):
            exp16_recommend = True

    low_tail_rows = [r for r in metrics_rows if r["subset"] == "low_tail"]
    low_tail_ok = all(
        r["spearman"] == "n/a"
        or (isinstance(r["spearman"], (int, float)) and r["spearman"] >= 0.35)
        for r in low_tail_rows
    )

    return {
        "experiment": "15_bar_only",
        "y_hat_source": str(export_csv),
        "review_source": str(review_csv),
        "warm_n": int(len(warm)),
        "scale": {
            "star_02": "(star_count - 1) / 2",
            "sentiment_02": "clip(sentiment + 1, 0, 2)",
        },
        "bars": list(BAR_IDS),
        "metrics": metrics_rows,
        "ceiling_stats": ceiling_rows,
        "decision": {
            "exp16_interaction_product_recommend": exp16_recommend,
            "low_tail_signal_preserved": low_tail_ok,
            "note": "bar-only; B2 Go not evaluated (fixed y_hat from exp13)",
        },
    }


def write_outputs(result: dict) -> None:
    FIGURES_DIR.mkdir(exist_ok=True)
    RUNS_DIR.mkdir(exist_ok=True)

    metrics_df = pd.DataFrame(result["metrics"])
    metrics_df.to_csv(
        FIGURES_DIR / "exp15_bar_variant_metrics.csv",
        index=False,
        encoding="utf-8-sig",
    )
    pd.DataFrame(result["ceiling_stats"]).to_csv(
        FIGURES_DIR / "exp15_bar_ceiling_stats.csv",
        index=False,
        encoding="utf-8-sig",
    )
    (RUNS_DIR / "exp15_bar_only.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _self_check() -> None:
    toy_review = pd.DataFrame(
        {
            "recipe_id": ["1", "1", "2"],
            "star_count": [5, 4, 2],
            "positive": [0.9, 0.8, 0.3],
            "negative": [0.1, 0.2, 0.7],
            "star_norm": [1.0, 0.5, -0.5],
        }
    )
    bars = build_recipe_bars(toy_review)
    assert "B3_prod_row" in bars.columns
    assert bars.loc[bars["recipe_id"] == "2", "B2_prod_avg"].iloc[0] < bars.loc[
        bars["recipe_id"] == "1", "B2_prod_avg"
    ].iloc[0]


def main() -> None:
    _self_check()
    result = evaluate_exp15()
    write_outputs(result)
    print(json.dumps(result["decision"], ensure_ascii=False, indent=2))
    print(f"saved: {FIGURES_DIR / 'exp15_bar_variant_metrics.csv'}")
    print(f"saved: {RUNS_DIR / 'exp15_bar_only.json'}")


if __name__ == "__main__":
    main()
