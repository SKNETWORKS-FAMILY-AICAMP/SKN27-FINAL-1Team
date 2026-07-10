"""Exp13 warm: review_rank_score vs y_hat scatter.

Run from ai/experiments:
  python plot/plot_exp13_scatter.py
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import pandas as pd
from scipy.stats import pearsonr, spearmanr

from paths import FIGURES_DIR, RECIPE_LIGHTFM_CSV
from charts import save_figure

OUT_PNG = FIGURES_DIR / "exp13_obs_vs_pred_scatter.png"


def main() -> None:
    df = pd.read_csv(RECIPE_LIGHTFM_CSV)
    warm = df.dropna(subset=["review_rank_score"]).copy()
    if warm.empty:
        raise SystemExit("no warm rows with review_rank_score")

    x_raw = warm["y_hat"].to_numpy()
    x_lin = warm["y_hat_linear"].to_numpy()
    y = warm["review_rank_score"].to_numpy()

    rho_raw = spearmanr(y, x_raw).statistic
    rho_lin = spearmanr(y, x_lin).statistic
    r_raw = pearsonr(y, x_raw).statistic

    fig, axes = plt.subplots(1, 2, figsize=(12, 5.5), dpi=120)

    for ax, x, title, rho in [
        (axes[0], x_raw, "y_hat (raw predict)", rho_raw),
        (axes[1], x_lin, "y_hat_linear (warm OLS scale)", rho_lin),
    ]:
        ax.scatter(x, y, alpha=0.45, s=22, edgecolors="none", c="#2563eb")
        lo = min(x.min(), y.min())
        hi = max(x.max(), y.max())
        ax.plot([lo, hi], [lo, hi], ls="--", c="#94a3b8", lw=1, label="y=x")
        ax.set_xlabel(title)
        ax.set_ylabel("review_rank_score (observed)")
        ax.set_title(f"warm n={len(warm)}  Spearman={rho:.3f}")
        ax.legend(loc="lower right", fontsize=8)
        ax.grid(True, alpha=0.25)

    fig.suptitle(
        "Experiment 13 — observed vs predicted review score (warm only)",
        fontsize=12,
        y=1.02,
    )
    fig.text(
        0.5,
        -0.02,
        f"Pearson(y_hat, obs)={r_raw:.3f}  |  linear: review_rank_score ~= 0.149*y_hat + 1.800",
        ha="center",
        fontsize=9,
        color="#475569",
    )
    fig.tight_layout()

    save_figure(fig, OUT_PNG, bbox_inches="tight")
    plt.close(fig)
    print(f"saved: {OUT_PNG}")


if __name__ == "__main__":
    main()
