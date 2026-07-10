"""6-panel y-axis decompose scatter + metrics txt.

Run from ai/experiments:
  python plot/plot_decompose.py --tag exp14_star_sentiment_sum --csv recipe_lightfm_exp14_star_sentiment_sum.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from charts import save_figure, scatter_obs_vs_pred
from metrics import decomposed_metrics_from_csv, format_metrics_txt, subset_masks, warm_frame
from paths import EXPERIMENTS_ROOT, FIGURES_DIR


def plot_decompose(
    csv_path: Path,
    out_prefix: str,
    title: str,
    *,
    out_png: Path | None = None,
    out_txt: Path | None = None,
) -> tuple[Path, Path]:
    warm = warm_frame(pd.read_csv(csv_path))
    masks = subset_masks(warm)

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
        warm.loc[masks["ceiling"], "y_hat"].to_numpy(),
        warm.loc[masks["ceiling"], "review_rank_score"].to_numpy(),
        xlabel="y_hat (predict)",
        ylabel="review_rank_score",
        title="D. star_norm >= 0.99 (ceiling band)",
        color="#ea580c",
    )
    scatter_obs_vs_pred(
        axes[1, 1],
        warm.loc[masks["star_varies"], "y_hat"].to_numpy(),
        warm.loc[masks["star_varies"], "review_rank_score"].to_numpy(),
        xlabel="y_hat (predict)",
        ylabel="review_rank_score",
        title="E. star_norm < 1.0 (star varies)",
        color="#16a34a",
    )
    scatter_obs_vs_pred(
        axes[1, 2],
        warm.loc[masks["low_tail"], "y_hat"].to_numpy(),
        warm.loc[masks["low_tail"], "review_rank_score"].to_numpy(),
        xlabel="y_hat (predict)",
        ylabel="review_rank_score",
        title="F. review_rank_score < 1.5 (low tail)",
        color="#dc2626",
    )

    fig.suptitle(title, fontsize=13, y=1.01)
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

    out_png = out_png or FIGURES_DIR / f"{out_prefix}_decompose.png"
    out_txt = out_txt or FIGURES_DIR / f"{out_prefix}_decompose_metrics.txt"
    save_figure(fig, out_png, bbox_inches="tight")
    plt.close(fig)

    rows = decomposed_metrics_from_csv(csv_path)
    out_txt.write_text(
        format_metrics_txt(f"{title} metrics (warm)", rows, len(warm)),
        encoding="utf-8",
    )
    return out_png, out_txt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True, help="output prefix, e.g. exp14_sentiment_only")
    parser.add_argument("--csv", required=True, help="recipe_lightfm export csv path")
    parser.add_argument("--title", default=None, help="figure suptitle")
    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.is_absolute():
        csv_path = EXPERIMENTS_ROOT / csv_path
    title = args.title or f"{args.tag} — observed (y) axis decomposition vs y_hat (warm only)"

    out_png, out_txt = plot_decompose(csv_path, args.tag, title)
    print(f"saved: {out_png}")
    print(f"saved: {out_txt}")


if __name__ == "__main__":
    main()
