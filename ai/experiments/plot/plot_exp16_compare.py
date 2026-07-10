"""Grouped bar chart: exp16 T0 vs T1 subset Spearman vs review_rank_score."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from charts import save_figure
from metrics import decomposed_metrics_from_csv
from paths import EXPERIMENTS_ROOT, FIGURES_DIR

RUNS = (
    ("star_sentiment_sum", "T0 legacy"),
    ("product_02_row", "T1 product"),
)
SUBSET_ORDER = ("all", "ceiling", "star_varies", "low_tail")
SUBSET_LABELS = {
    "all": "all",
    "ceiling": "ceiling",
    "star_varies": "star<1",
    "low_tail": "low<1.5",
}


def collect_long_metrics() -> pd.DataFrame:
    rows: list[dict] = []
    for target, label in RUNS:
        csv_path = EXPERIMENTS_ROOT / f"recipe_lightfm_exp16_{target}.csv"
        json_path = EXPERIMENTS_ROOT / "runs" / f"exp16_{target}.json"
        if json_path.exists():
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            dec = payload.get("track_b_eval", {}).get("decomposed")
            if dec:
                for row in dec:
                    rows.append({"target": target, "run": label, **row})
                continue
        if not csv_path.exists():
            continue
        for row in decomposed_metrics_from_csv(csv_path):
            rows.append({"target": target, "run": label, **row})
    if not rows:
        raise SystemExit("no exp16 metrics found (run training + plot_decompose first)")
    return pd.DataFrame(rows)


def main() -> None:
    df = collect_long_metrics()
    review = df[df["bar"] == "review_rank_score"].copy()
    review["spearman"] = pd.to_numeric(review["spearman"], errors="coerce")

    out_csv = FIGURES_DIR / "exp16_baseline_vs_product_metrics.csv"
    review.to_csv(out_csv, index=False, encoding="utf-8-sig")

    pivot = review.pivot(index="subset", columns="target", values="spearman")
    pivot = pivot.reindex(SUBSET_ORDER)
    pivot = pivot.reindex(columns=[t for t, _ in RUNS])

    fig, ax = plt.subplots(figsize=(8, 5), dpi=120)
    x = range(len(SUBSET_ORDER))
    width = 0.35
    colors = ["#2563eb", "#ea580c"]
    for i, (target, label) in enumerate(RUNS):
        if target not in pivot.columns:
            continue
        offsets = [xi + (i - 0.5) * width for xi in x]
        ax.bar(
            offsets,
            pivot[target].to_numpy(),
            width=width,
            label=label,
            color=colors[i % len(colors)],
        )

    ax.axhline(0, color="#94a3b8", linewidth=0.8)
    ax.set_xticks(list(x))
    ax.set_xticklabels([SUBSET_LABELS[s] for s in SUBSET_ORDER])
    ax.set_ylabel("Spearman(y_hat, review_rank_score)")
    ax.set_title("Experiment 16 — T0 legacy vs T1 product (B3 bar)")
    ax.legend(title="run", fontsize=8)
    fig.tight_layout()

    out_png = FIGURES_DIR / "exp16_baseline_vs_product_compare.png"
    save_figure(fig, out_png)
    plt.close(fig)

    print(f"saved: {out_csv}")
    print(f"saved: {out_png}")
    print(pivot.round(4).to_string())


if __name__ == "__main__":
    main()
