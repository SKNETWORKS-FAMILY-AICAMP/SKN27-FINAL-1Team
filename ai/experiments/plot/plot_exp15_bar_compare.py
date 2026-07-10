"""Experiment 15: bar variant x subset Spearman + ceiling std."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from charts import save_figure
from paths import FIGURES_DIR

BAR_ORDER = ("B0_legacy", "B1_sum_02", "B2_prod_avg", "B3_prod_row")
BAR_LABELS = {
    "B0_legacy": "legacy sum",
    "B1_sum_02": "sum 0~2",
    "B2_prod_avg": "prod avg",
    "B3_prod_row": "prod row",
}
SUBSET_ORDER = ("all", "ceiling", "star_varies", "low_tail")
SUBSET_LABELS = {
    "all": "all",
    "ceiling": "ceiling",
    "star_varies": "star<1",
    "low_tail": "low<1.5",
}


def main() -> None:
    metrics_path = FIGURES_DIR / "exp15_bar_variant_metrics.csv"
    ceiling_path = FIGURES_DIR / "exp15_bar_ceiling_stats.csv"
    if not metrics_path.exists():
        raise SystemExit(f"missing {metrics_path}; run bar_eval.py first")

    df = pd.read_csv(metrics_path)
    review = df[df["bar"] == "score"].copy()
    review["spearman"] = pd.to_numeric(review["spearman"], errors="coerce")

    pivot = review.pivot(index="subset", columns="bar_id", values="spearman")
    pivot = pivot.reindex(SUBSET_ORDER)
    pivot = pivot.reindex(columns=list(BAR_ORDER))

    fig, ax = plt.subplots(figsize=(10, 5), dpi=120)
    x = range(len(SUBSET_ORDER))
    width = 0.18
    colors = ["#64748b", "#2563eb", "#7c3aed", "#0d9488"]
    for i, bar_id in enumerate(BAR_ORDER):
        if bar_id not in pivot.columns:
            continue
        offsets = [xi + (i - 1.5) * width for xi in x]
        ax.bar(
            offsets,
            pivot[bar_id].to_numpy(),
            width=width,
            label=BAR_LABELS[bar_id],
            color=colors[i % len(colors)],
        )

    ax.axhline(0, color="#94a3b8", linewidth=0.8)
    ax.set_xticks(list(x))
    ax.set_xticklabels([SUBSET_LABELS[s] for s in SUBSET_ORDER])
    ax.set_ylabel("Spearman(y_hat, bar)")
    ax.set_title("Experiment 15 — bar variant x subset (fixed y_hat, bar-only)")
    ax.legend(title="bar", fontsize=8)
    fig.tight_layout()
    out_png = FIGURES_DIR / "exp15_bar_variant_compare.png"
    save_figure(fig, out_png)
    plt.close(fig)

    if ceiling_path.exists():
        cdf = pd.read_csv(ceiling_path)
        cdf["std"] = pd.to_numeric(cdf["std"], errors="coerce")
        cdf = cdf.set_index("bar_id").reindex(BAR_ORDER)
        fig2, ax2 = plt.subplots(figsize=(6, 4), dpi=120)
        ax2.bar(
            [BAR_LABELS.get(b, b) for b in BAR_ORDER],
            cdf["std"].to_numpy(),
            color=colors,
        )
        ax2.set_ylabel("std (ceiling subset)")
        ax2.set_title("Experiment 15 — ceiling bar spread")
        fig2.tight_layout()
        out_std = FIGURES_DIR / "exp15_bar_ceiling_std.png"
        save_figure(fig2, out_std)
        plt.close(fig2)
        print(f"saved: {out_std}")

    print(f"saved: {out_png}")
    print(pivot.round(4).to_string())


if __name__ == "__main__":
    main()
