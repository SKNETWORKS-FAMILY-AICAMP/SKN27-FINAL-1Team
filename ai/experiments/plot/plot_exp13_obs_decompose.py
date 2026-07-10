"""Exp13 warm: decompose observed y axis vs y_hat.

Run from ai/experiments:
  python plot/plot_exp13_obs_decompose.py
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from charts import save_figure, scatter_obs_vs_pred
from paths import FIGURES_DIR, RECIPE_LIGHTFM_CSV

OUT_PNG = FIGURES_DIR / "exp13_obs_y_decompose_scatter.png"
OUT_SUMMARY = FIGURES_DIR / "exp13_obs_y_decompose_metrics.txt"


def _subset_metrics(warm: pd.DataFrame, mask: pd.Series, name: str) -> list[str]:
    sub = warm.loc[mask]
    lines = [f"[{name}] n={len(sub)}"]
    if len(sub) < 2:
        lines.append("  (too few for correlation)")
        return lines
    for ylab in ("star_norm_avg", "sentiment_avg", "review_rank_score"):
        yv = sub[ylab].to_numpy()
        xv = sub["y_hat"].to_numpy()
        if np.std(yv) < 1e-12 or np.std(xv) < 1e-12:
            lines.append(f"  Spearman(y_hat, {ylab}) = n/a (constant)")
            continue
        rho = spearmanr(yv, xv).statistic
        lines.append(f"  Spearman(y_hat, {ylab}) = {rho:.4f}")
    return lines


def main() -> None:
    df = pd.read_csv(RECIPE_LIGHTFM_CSV)
    warm = df.dropna(subset=["review_rank_score"]).copy()
    if warm.empty:
        raise SystemExit("no warm rows")

    if "sentiment_avg" not in warm.columns:
        warm["sentiment_avg"] = (
            warm["positive_avg"].astype(float) - warm["negative_avg"].astype(float)
        )

    star_ceiling = warm["star_norm_avg"] >= 0.99
    star_below = warm["star_norm_avg"] < 1.0
    low_review = warm["review_rank_score"] < 1.5

    fig, axes = plt.subplots(2, 3, figsize=(14, 9), dpi=120)

    scatter_obs_vs_pred(
        axes[0, 0],
        warm["y_hat"].to_numpy(),
        warm["star_norm_avg"].to_numpy(),
        xlabel="y_hat (predict)",
        ylabel="star_norm_avg (observed)",
        title="A. star component",
        color="#0d9488",
    )
    scatter_obs_vs_pred(
        axes[0, 1],
        warm["y_hat"].to_numpy(),
        warm["sentiment_avg"].to_numpy(),
        xlabel="y_hat (predict)",
        ylabel="sentiment_avg (observed)",
        title="B. sentiment component",
        color="#7c3aed",
    )
    scatter_obs_vs_pred(
        axes[0, 2],
        warm["y_hat"].to_numpy(),
        warm["review_rank_score"].to_numpy(),
        xlabel="y_hat (predict)",
        ylabel="review_rank_score (observed)",
        title="C. combined (star + sentiment)",
        color="#2563eb",
    )
    scatter_obs_vs_pred(
        axes[1, 0],
        warm.loc[star_ceiling, "y_hat"].to_numpy(),
        warm.loc[star_ceiling, "review_rank_score"].to_numpy(),
        xlabel="y_hat (predict)",
        ylabel="review_rank_score",
        title="D. star_norm >= 0.99 (ceiling band)",
        color="#ea580c",
    )
    scatter_obs_vs_pred(
        axes[1, 1],
        warm.loc[star_below, "y_hat"].to_numpy(),
        warm.loc[star_below, "review_rank_score"].to_numpy(),
        xlabel="y_hat (predict)",
        ylabel="review_rank_score",
        title="E. star_norm < 1.0 (star varies)",
        color="#16a34a",
    )
    scatter_obs_vs_pred(
        axes[1, 2],
        warm.loc[low_review, "y_hat"].to_numpy(),
        warm.loc[low_review, "review_rank_score"].to_numpy(),
        xlabel="y_hat (predict)",
        ylabel="review_rank_score",
        title="F. review_rank_score < 1.5 (low tail)",
        color="#dc2626",
    )

    fig.suptitle(
        "Experiment 13 — observed (y) axis decomposition vs y_hat (warm only)",
        fontsize=13,
        y=1.01,
    )
    fig.text(
        0.5,
        0.01,
        "Rows: full components (top) | subsets: star ceiling / star<1 / low review (bottom). "
        "Dashed = y=x (comparable scale only).",
        ha="center",
        fontsize=9,
        color="#475569",
    )
    fig.tight_layout(rect=(0, 0.03, 1, 0.98))

    save_figure(fig, OUT_PNG, bbox_inches="tight")
    plt.close(fig)

    summary_lines = [
        "Experiment 13 - y-axis decomposition metrics (warm)",
        f"total warm n = {len(warm)}",
        "",
        *_subset_metrics(warm, pd.Series(True, index=warm.index), "ALL warm"),
        "",
        *_subset_metrics(warm, star_ceiling, "star_norm >= 0.99"),
        "",
        *_subset_metrics(warm, star_below, "star_norm < 1.0"),
        "",
        *_subset_metrics(warm, low_review, "review_rank_score < 1.5"),
        "",
        "star_norm_avg == 1.0 count:",
        f"  {(warm['star_norm_avg'] == 1.0).sum()} / {len(warm)}",
    ]
    OUT_SUMMARY.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    print(f"saved: {OUT_PNG}")
    print(f"saved: {OUT_SUMMARY}")
    print("\n".join(summary_lines))


if __name__ == "__main__":
    main()
